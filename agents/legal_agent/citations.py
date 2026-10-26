"""Citation grounding and conservative independent support checks; no registry storage."""
import hashlib
import json
import re
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, create_model, ValidationError
if __package__ and __package__.startswith('agents.legal_agent'):
    from .models.schemas import AuthorityId,Finding,ResearchDraft,LegalConclusion,EvidenceId,EvidenceKind,MemoryId
else:
    from models.schemas import AuthorityId,Finding,ResearchDraft,LegalConclusion,EvidenceId,EvidenceKind,MemoryId


def selection_schema(authorities,evidence_ids=(),max_observations=3):
    """Only canonical IDs/quotes leave the model. Metadata is runtime owned."""
    ids=tuple(dict.fromkeys(s['id'] for s in authorities))
    selected=Literal.__getitem__(ids) if ids else AuthorityId
    citation=create_model('AuthoritySelection',__config__=ConfigDict(extra='forbid'),
        authority_id=(selected,Field(description='Select an exact retrieved authority ID')),
        supporting_quote=(str,Field(description='Exact contiguous text from the provided excerpt, including qualifications')))
    claim=create_model('SelectedLegalClaim',__config__=ConfigDict(extra='forbid'),
        statement=(str,Field(default='',description='For current_guidance or statute_text leave empty: runtime formats your selected quote with explicit attribution. Do not duplicate quotation text. Provide a statement only for an interpretation; historical application remains independently unverified.')),claim_scope=(Literal['current_guidance','statute_text','historical_application'],...),
        citations=(list[citation],Field(min_length=1)))
    evidence_ids=tuple(dict.fromkeys(evidence_ids))
    evidence_type=Literal.__getitem__(evidence_ids) if evidence_ids else EvidenceId
    evidence_field=lambda:Field(default_factory=list,**({'max_length':0} if not evidence_ids else {}))
    finding=create_model('SelectedFinding',finding_id=(str,...),issue=(str,...),summary=(str,...),
        evidence_ids=(list[evidence_type],evidence_field()),contradictory_evidence_ids=(list[evidence_type],evidence_field()),
        evidence_kinds=(list[EvidenceKind],Field(default_factory=list)),memory_ids=(list[MemoryId],Field(default_factory=list)),
        missing_information=(list[str],Field(default_factory=list)),
        sufficiency=(Literal['sufficient','partial','insufficient'],'partial'),
        legal_conclusions=(list[claim],Field(default_factory=list,**({'max_length':0} if not ids else {}))))
    return create_model('CanonicalResearchDraft',task_id=(str,...),plan_revision=(int,0),findings=(list[finding],Field(max_length=max_observations)),
        evidence_ids_used=(list[evidence_type],evidence_field()),caveats=(list[str],Field(default_factory=list)))


def validate_observations(wire_schema,content,trace=None):
    """Discard whole invalid observations, never repair citations or partial JSON.

    Envelope errors, missing required fields and array-limit errors remain fatal.
    Every survivor is validated again with the original retrieved-ID schema.
    Only rejection indexes, hashes and error locations/types enter activity logs.
    """
    def emit(event,**data):
        if trace:trace.emit(event,**data)
    try:
        value=wire_schema.model_validate_json(content)
    except ValidationError as error:
        errors=error.errors(include_input=False,include_url=False)
        if not errors or any(len(e['loc'])<2 or e['loc'][0]!='findings' or not isinstance(e['loc'][1],int) for e in errors):
            raise
        raw=json.loads(content)
        # Validate the entire envelope unchanged before isolating any observation.
        limit=next(m.max_length for m in wire_schema.model_fields['findings'].metadata if hasattr(m,'max_length'))
        if len(raw['findings'])>limit:raise error
        envelope=wire_schema.model_validate({**raw,'findings':[]})
        observation_type=wire_schema.model_fields['findings'].annotation.__args__[0]
        valid=[];rejected=0
        ids=[f.get('finding_id') for f in raw['findings'] if isinstance(f,dict) and isinstance(f.get('finding_id'),str)]
        if len(ids)!=len(set(ids)):
            raise ValueError('Ambiguous duplicate observation IDs')
        for index,observation in enumerate(raw['findings']):
            try:
                checked=observation_type.model_validate(observation)
                valid.append(checked.model_dump(mode='json'))
            except ValidationError as issue:
                rejected+=1
                identifier=observation.get('finding_id') if isinstance(observation,dict) else None
                identifier=identifier if isinstance(identifier,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',identifier) else None
                emit('research.observation_rejected',index=index,finding_id=identifier,
                    content_sha256=hashlib.sha256(json.dumps(observation,sort_keys=True).encode()).hexdigest(),
                    validation=[{'path':[str(p) for p in e['loc']],'type':e['type']} for e in issue.errors(include_input=False,include_url=False)][:12],
                    accepted_as_claim=False)
        emit('research.observations_validated',valid_count=len(valid),rejected_count=rejected)
        if not valid:
            emit('legal.review_unavailable',reason='all_observations_rejected')
            if __package__ and __package__.startswith('agents.legal_agent'):
                from .tools.execution import ExecutionStopped
            else:
                from tools.execution import ExecutionStopped
            raise ExecutionStopped('Legal review unavailable: all Researcher observations failed validation')
        envelope.findings=[]
        repaired={**envelope.model_dump(mode='json'),'findings':valid}
        repaired['caveats'].append(f'{rejected} invalid Researcher observation(s) discarded in full; remaining observations require independent legal review.')
        return wire_schema.model_validate(repaired)
    emit('research.observations_validated',valid_count=len(value.findings),rejected_count=0)
    return value


def selected_draft(value):
    data=value.model_dump(mode='json')
    for finding in data['findings']:
        for index,claim in enumerate(finding['legal_conclusions']):
            selections=claim.pop('citations')
            if not claim['statement'] and claim['claim_scope'] in {'current_guidance','statute_text'}:
                prefix='Current official guidance states: ' if claim['claim_scope']=='current_guidance' else 'The provided statutory excerpt states: '
                claim['statement']=prefix+selections[0]['supporting_quote']
            finding['legal_conclusions'][index]={**claim,'source_ids':list(dict.fromkeys(c['authority_id'] for c in selections)),
                'support_quotes':{c['authority_id']:c['supporting_quote'] for c in selections}}
    return ResearchDraft.model_validate(data)


def _normal(text):return re.sub(r'\s+',' ',text).strip()


def assess_claim(claim,registry,*,as_of=None):
    """Recompute from retrieved originals. A source ID never proves entailment.

    Only exact, attributed source-text statements can be verified automatically.
    Paraphrases/interpretations remain unverified for independent review. Historical
    applications never gain approval from current guidance or a retrieval timestamp.
    """
    errors=[];sources=[]
    if not claim.source_ids:errors.append('missing_authority')
    for sid in claim.source_ids:
        source=registry.get(sid)
        if source is None:errors.append('unretrieved_authority');continue
        sources.append(source)
    identity_valid=bool(claim.source_ids) and len(sources)==len(claim.source_ids)
    valid_quotes=[]
    for source in sources:
        quote=_normal(claim.support_quotes.get(source.id,''))
        excerpt=_normal(source.excerpt or '')
        proof=source.excerpt_provenance
        integrity=bool(source.excerpt and proof.get('excerpt_sha256')==hashlib.sha256(source.excerpt.encode()).hexdigest())
        if not integrity or not quote or len(quote)<40 or quote not in excerpt:
            errors.append('unverified_support_quote')
        else:valid_quotes.append(quote)
    text=_normal(claim.statement)
    topic=text.lower()
    for source in sources:
        if source.id=='hpd-heat-hot-water' and re.search(r'\b(litigation|court|lawsuit|adjudicat\w*|jurisdiction)\b',topic):
            errors.append('wrong_topic_source')
        if source.id=='dob-boilers' and re.search(r'\b(permit\w*|demolition|construction)\b',topic) and not re.search(r'\bboiler\w*\b',topic):
            errors.append('wrong_topic_source')
    if claim.claim_scope=='current_guidance':
        if not sources or any(s.authority_type!='agency_guidance' for s in sources):errors.append('authority_type_mismatch')
        prefix=re.match(r'^Current (?:official|HPD|DOB|agency) guidance states:\s*',text,re.I)
        if not prefix:errors.append('claim_not_narrowly_attributed')
        body=text[prefix.end():].strip(' "“”') if prefix else text
    elif claim.claim_scope=='statute_text':
        if not sources or any(s.authority_type!='statute' for s in sources):errors.append('authority_type_mismatch')
        prefix=re.match(r'^The provided statutory excerpt states:\s*',text,re.I)
        if not prefix:errors.append('claim_not_narrowly_attributed')
        body=text[prefix.end():].strip(' "“”') if prefix else text
    else:
        body=text
        if any(s.authority_type=='agency_guidance' or not s.excerpt_provenance.get('historical_version_verified') for s in sources):
            errors.append('historical_applicability_unverified')
        # Even verified historical identity cannot prove property-specific liability.
        errors.append('interpretation_requires_independent_verification')
    if claim.claim_scope!='historical_application' and as_of and any(s.checked_on is None or s.checked_on>as_of for s in sources):
        errors.append('source_observation_date_unverified')
    if not valid_quotes or len(valid_quotes)!=len(sources) or any(body!=quote for quote in valid_quotes):errors.append('claim_not_entailed_by_exact_excerpt')
    return {'source_identity_valid':identity_valid,'claim_support_verified':identity_valid and not errors,
            'errors':list(dict.fromkeys(errors)),'historical_version_verified':bool(sources) and all(s.excerpt_provenance.get('historical_version_verified',False) for s in sources)}


def canonical_metadata(claim,registry):
    return [{'authority_id':sid,'identifier':registry[sid].identifier,'title':registry[sid].title,
        'source_url':registry[sid].url,'jurisdiction':registry[sid].jurisdiction,'authority_type':registry[sid].authority_type,
        'provenance':dict(registry[sid].excerpt_provenance),'supporting_quote':claim.support_quotes.get(sid,'')}
        for sid in dict.fromkeys(claim.source_ids) if sid in registry]


def ground_draft(draft,registry,*,as_of=None):
    """Overwrite all generated citation metadata. Unknown IDs retain only diagnostics."""
    for finding in draft.findings:
        for claim in finding.legal_conclusions:
            claim.citations=canonical_metadata(claim,registry)
            claim.identifiers=[citation['identifier'] for citation in claim.citations]
            claim.grounding_version='registry-v1'
            assessment=assess_claim(claim,registry,as_of=as_of)
            claim.grounding_errors=assessment['errors']
            claim.supported=assessment['claim_support_verified']
    return draft


def audit_claims(findings,registry,accepted_ids,*,as_of=None):
    rows=[]
    for finding in findings:
        for index,claim in enumerate(finding.legal_conclusions):
            assessment=assess_claim(claim,registry,as_of=as_of)
            metadata_ok=claim.citations==canonical_metadata(claim,registry) and bool(claim.grounding_version)
            for sid in claim.source_ids:
                source=registry.get(sid)
                rows.append({'claim_id':finding.finding_id+':'+str(index),'finding_id':finding.finding_id,'authority_id':sid,
                    'source_identity_valid':assessment['source_identity_valid'] and metadata_ok,
                    'claim_support_verified':assessment['claim_support_verified'] and metadata_ok,
                    'support_errors':assessment['errors'],'claim_scope':claim.claim_scope,
                    'retrieved':source is not None,'identifier_matches':bool(source and source.identifier in claim.identifiers),
                    'official_excerpt_available':bool(source and source.excerpt and source.excerpt_provenance),
                    'evidence_ids_accepted':bool(finding.evidence_ids) and set(finding.evidence_ids)<=accepted_ids,
                    'finding_valid':finding.valid,'source_url':source.url if source else None,
                    'historical_version_verified':assessment['historical_version_verified']})
    groups={}
    for row in rows:groups.setdefault(row['claim_id'],[]).append(row)
    metrics={'cited_claims':len(groups),
        'claims_with_valid_source_identity':sum(all(r['source_identity_valid'] for r in group) for group in groups.values()),
        'claims_with_verified_support':sum(all(r['claim_support_verified'] for r in group) for group in groups.values())}
    return rows,metrics
