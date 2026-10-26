"""Conservative NYC identity resolution. No remote calls or invented identifiers."""
import json
import re
from pathlib import Path
from typing import Protocol
if __package__ and __package__.startswith("agents.legal_agent"):
    from .models.identity import IdentityCandidate, IdentityResult, RecordMatch
else:
    from models.identity import IdentityCandidate, IdentityResult, RecordMatch


def normalize_address(address: str) -> tuple[str, str | None]:
    value = re.sub(r'\s+', ' ', address.strip().upper())
    parts = re.split(r'\s+(?:APT\.?|APARTMENT|UNIT|#)\s*', value, maxsplit=1)
    unit = parts[1].split(',')[0].strip() if len(parts) > 1 else None
    value = parts[0].replace('.', '')
    value = re.sub(r',.*$', '', value)
    for full, short in [('EAST','E'), ('WEST','W'), ('NORTH','N'), ('SOUTH','S'), ('STREET','ST'), ('AVENUE','AVE'), ('BOULEVARD','BLVD'), ('ROAD','RD'), ('PLACE','PL')]:
        value = re.sub(r'\b' + full + r'\b', short, value)
    # Street ordinals, never the house number or apartment identifier.
    pieces=value.split()
    ordinals={'FIRST':'1','SECOND':'2','THIRD':'3','FOURTH':'4','FIFTH':'5','SIXTH':'6','SEVENTH':'7','EIGHTH':'8','NINTH':'9','TENTH':'10'}
    value=' '.join([pieces[0],*[ordinals.get(p,re.sub(r'^(\d+)(ST|ND|RD|TH)$',r'\1',p)) for p in pieces[1:]]]) if pieces else ''
    return value.strip(), unit


class IdentityAdapter(Protocol):
    def candidates(self, address: str) -> list[IdentityCandidate]: ...


class MappedIdentityAdapter:
    """Inject a read-only loader mapping GeoSearch/HPD/Zetaris rows to our contract.

    No live connector is shipped. Loader execution belongs to the team's bounded
    data layer; don't pass an untrusted callable from HTTP JSON.
    """
    def __init__(self, loader):
        self.loader = loader

    def candidates(self, address):
        return [IdentityCandidate.model_validate(row) for row in self.loader(address)]


class GeoSearchAdapter(MappedIdentityAdapter):
    pass


class HPDAdapter(MappedIdentityAdapter):
    pass


class ZetarisAdapter(MappedIdentityAdapter):
    pass


def sample_candidates():
    return json.loads((Path(__file__).parent / 'data' / 'identity_samples.json').read_text())


def resolve_building_identity(address, context=None):
    """JSON API. Candidate provenance is supplied by trusted upstream adapters.

    context: {unit?, borough?, candidates?: IdentityCandidate[]}. Omitted candidates
    use explicitly fictional fixtures, never real address verification.
    """
    context = context or {}
    canonical, inline_unit = normalize_address(address)
    result = IdentityResult(canonical_address=canonical, unit=context.get('unit') or inline_unit,
                            borough=context.get('borough'))
    candidates = [IdentityCandidate.model_validate(c) for c in context.get('candidates', sample_candidates())]
    for c in candidates:
        addresses = [normalize_address(a)[0] for a in [c.address, *c.aliases]]
        if canonical in addresses and (not result.borough or not c.borough or c.borough.lower() == result.borough.lower()):
            result.candidates.append(c)
        else:
            result.rejected_candidates.append(c.candidate_id)
    if not result.candidates:
        result.ambiguities.append('No candidate matched; upstream address verification required.')
    elif len(result.candidates) != 1:
        result.verification_status = 'ambiguous'
        result.ambiguities.append('Multiple candidate buildings; BBL alone cannot select a building.')
    else:
        candidate = result.candidates[0]
        result.canonical_address = normalize_address(candidate.address)[0]
        result.borough = candidate.borough
        result.match_method = 'canonical_or_alias'
        groups = {}
        for item in candidate.identifiers:
            groups.setdefault(item.kind, set()).add(item.value)
        conflicts = [kind for kind, values in groups.items() if len(values) > 1]
        if conflicts:
            result.verification_status = 'ambiguous'
            result.ambiguities.append('Conflicting identifiers: ' + ', '.join(conflicts))
        else:
            usable = [i for i in candidate.identifiers if i.authoritative or i.fictional]
            result.identifiers = {i.kind: i.value for i in usable}
            result.verified_identifiers = [i for i in usable if i.authoritative and not i.fictional]
            result.verification_status = ('sample' if usable and all(i.fictional for i in usable)
                                          else 'verified' if result.verified_identifiers else 'unverified')
            result.confidence = .95 if usable else .6
            if not usable:
                result.ambiguities.append('Address match lacks authoritative identifiers.')
    return result.model_dump(mode='json')


def match_record(record, identity):
    identity = IdentityResult.model_validate(identity) if isinstance(identity, dict) else identity
    meta = record.metadata
    scope = meta.get('scope', 'building')
    def decision(value, method, confidence, reason):
        return RecordMatch(evidence_id=record.evidence_id, decision=value, method=method,
                           scope=scope, confidence=confidence, reason=reason)
    if identity.verification_status in {'missing', 'ambiguous'}:
        return decision('quarantined', 'unresolved_identity', 0, 'Building identity unresolved.')
    if scope == 'entity':
        return decision('quarantined', 'entity_only', .1, 'Entity litigation needs independent property linkage.')
    if scope == 'unit' and (not identity.unit or not meta.get('unit') or str(meta['unit']).upper() != identity.unit.upper()):
        return decision('quarantined', 'unit_mismatch', .2, 'Unit cannot be attributed to requested apartment.')
    ids = identity.identifiers
    for kind in ('bin', 'hpd_building_id', 'bbl'):
        if meta.get(kind) and ids.get(kind) and str(meta[kind]) != ids[kind]:
            return decision('rejected', 'identifier_conflict', 1, f'Conflicting {kind}.')
    for kind in ('bin', 'hpd_building_id'):
        if meta.get(kind) and ids.get(kind) == str(meta[kind]):
            return decision('accepted', kind, .99, 'Building identifier matches; supplied provenance remains unverified.')
    if meta.get('bbl') and ids.get('bbl') == str(meta['bbl']):
        if scope == 'property':
            return decision('accepted', 'bbl_property', .95, 'Tax-lot record; cannot establish building or unit conditions.')
        return decision('quarantined', 'bbl_only', .4, 'A tax lot can contain multiple buildings.')
    addr = normalize_address(record.building_address or '')[0]
    aliases = {identity.canonical_address}
    for c in identity.candidates:
        aliases.update(normalize_address(a)[0] for a in [c.address, *c.aliases])
    if addr and addr in aliases:
        return decision('accepted', 'address_or_alias', .7, 'Address match only; identifiers not independently checked.')
    return decision('rejected' if addr else 'quarantined', 'address_mismatch', .9 if addr else 0,
                    'Unrelated address.' if addr else 'No attributable address or building identifier.')
