"""Deterministic renter verdict from accepted records and source coverage.

Pure function: no model calls, no network, no randomness. Time windows are measured
back from the investigation date. The verdict is a record-based flag summary, never a
statement that a building is safe.
"""
from datetime import date, datetime
import re

if __package__ and __package__.startswith("agents.legal_agent"):
    from .tools.risk_mapping import normalize_agency_status
else:
    from tools.risk_mapping import normalize_agency_status

NOT_ENOUGH_DATA = "NOT ENOUGH DATA"
WALK_AWAY = "WALK AWAY"
CAUTION = "CAUTION"
NO_FLAGS = "NO FLAGS FOUND"

# Socrata dataset id -> registry source key (data/source_registry.json). A finding carries
# `dataset`; the source key is only on the evidence_audit record's metadata.
DATASET_SOURCES = {"wvxf-dwi5": "hpd_violations", "ygpa-z7cr": "hpd_complaints", "hcir-3275": "hpd_aep",
                   "59kj-x8nc": "hpd_litigation", "6z8x-wfk4": "executed_evictions"}
REQUIRED_SOURCES = ("hpd_violations", "hpd_complaints")
USABLE_COVERAGE = {"retrieved", "no_records"}
VERIFIED_IDENTITY = {"verified", "sample"}
# NO FLAGS FOUND needs at least this share of machine-readable sources checked (manual-only
# and config-disabled sources are excluded). WALK AWAY / CAUTION still fire on partial data.
MIN_MACHINE_COVERAGE = 0.5
NOT_MACHINE_READABLE = {"manual_only", "disabled_by_config"}
RULES_CHECKED = ["W1", "W2", "C1", "C2", "C3", "C4"]
DISCLAIMER = ("This is not a safety guarantee. It is based only on recorded agency data retrieved for the "
              "stated filters; records may be incomplete, outdated or unit-specific. Unavailable or "
              "incomplete sources are listed in the basis and were not checked.")


def _years_back(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # Feb 29
        return day.replace(year=day.year - years, day=28)


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _unit_key(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _dated(finding):
    return _to_date(finding.get("event_date"))


def compute_verdict(report: dict, investigation_date, unit: str | None) -> dict:
    today = _to_date(investigation_date)
    if today is None:
        raise ValueError("investigation_date must be a date or ISO date string")
    since_12m, since_2y = _years_back(today, 1), _years_back(today, 2)
    audit = {r.get("evidence_id"): r.get("metadata") or {} for r in report.get("evidence_audit") or []}
    audit_rows = {r.get("evidence_id"): r for r in report.get("evidence_audit") or []}
    wanted_unit = _unit_key(unit)

    def in_window(finding, start):
        day = _dated(finding)
        return day is not None and start <= day <= today

    coverage = {c.get("source"): c.get("status") for c in report.get("coverage") or []}
    identity_status = (report.get("identity") or {}).get("verification_status")
    # Live runs mark court/HCR sources status=manual_only; the replay provider reports them as
    # "unavailable" but keeps match_field="manual". Either way they are not machine-readable.
    manual = {c.get("source") for c in report.get("coverage") or [] if c.get("match_field") == "manual"}
    machine = [k for k, st in coverage.items() if st not in NOT_MACHINE_READABLE and k not in manual]
    checked = [k for k in machine if coverage[k] in USABLE_COVERAGE]
    sources_checked = sorted(k for k, s in coverage.items() if s in USABLE_COVERAGE)
    sources_unavailable = sorted(k for k, s in coverage.items() if s not in USABLE_COVERAGE | {"not_selected", "disabled_by_config"})

    # Count accepted building/property records, plus unit records only for the supplied unit.
    by_source, ignored = {}, {"entity_scope": 0, "unit_scope": 0, "undated_in_window_rules": 0}
    for finding in report.get("factual_findings") or []:
        eids = finding.get("evidence_ids") or []
        meta = audit.get(eids[0], {}) if eids else {}
        source = meta.get("source_key") or DATASET_SOURCES.get(finding.get("dataset"))
        if source is None:
            continue
        scope = finding.get("scope")
        if scope == "entity":
            ignored["entity_scope"] += 1
            continue
        if scope == "unit":
            finding_unit = _unit_key(finding.get("unit") or meta.get("unit"))
            if not wanted_unit or finding_unit != wanted_unit:
                ignored["unit_scope"] += 1
                continue
        elif scope not in ("building", "property"):
            continue
        status = meta.get("normalized_status") or normalize_agency_status(finding.get("recorded_status"))
        by_source.setdefault(source, []).append((finding, status))

    # Apartment-level violations the Critic holds (R8, unit_mismatch) when no unit was requested.
    # The hold stays; the verdict still counts them, labelled separately. Fields used:
    # record_decisions[].decision/rule, evidence_audit[].metadata.match_method/source_key/
    # hpd_building_id/bin/bbl/normalized_status/source_url/raw_record, evidence_audit[].violation_class/date,
    # identity.identifiers. A record whose own identifiers conflict with the building's is never counted.
    decisions = {d.get("record_id"): d for d in report.get("record_decisions") or []}
    identifiers = (report.get("identity") or {}).get("identifiers") or {}
    counted = {e for items in by_source.values() for f, _ in items for e in (f.get("evidence_ids") or [])}
    apartment = []
    for eid, meta in audit.items():
        decision = decisions.get(eid) or {}
        if (meta.get("source_key") != "hpd_violations" or decision.get("decision") != "quarantine" or decision.get("rule") != "R8"
                or meta.get("match_method") != "unit_mismatch" or eid in counted):
            continue
        pairs = [(identifiers.get(k), meta.get(m)) for k, m in (("hpd_building_id", "hpd_building_id"), ("bin", "bin"), ("bbl", "bbl"))]
        pairs = [(a, b) for a, b in pairs if a and b]
        if not pairs or any(str(a) != str(b) for a, b in pairs):
            continue
        raw = meta.get("raw_record") or {}
        row = audit_rows.get(eid) or {}
        status = meta.get("normalized_status") or normalize_agency_status(row.get("status"), raw=raw)
        day = str(row.get("date") or raw.get("inspectiondate") or "")[:10] or None
        apartment.append(({"evidence_ids": [eid], "source_url": meta.get("source_url"), "scope": "unit", "event_date": day,
                           "severity": row.get("violation_class") or raw.get("class"), "apartment": raw.get("apartment"),
                           "recorded_status": row.get("status")}, status))

    def ids(items):
        return list(dict.fromkeys(e for f, _ in items for e in (f.get("evidence_ids") or [])))

    def urls(items):
        seen, out = set(), []
        for f, _ in items:
            for e in f.get("evidence_ids") or []:
                if e not in seen:
                    seen.add(e)
                    out.append(f.get("source_url"))
        return out

    violations = by_source.get("hpd_violations", [])

    def open_class(items, letter):
        return [(f, s) for f, s in items if s == "open" and str(f.get("severity") or "").upper() == letter]

    open_c_building, open_c_apartment = open_class(violations, "C"), open_class(apartment, "C")
    open_b_building, open_b_apartment = open_class(violations, "B"), open_class(apartment, "B")
    open_c = open_c_building + open_c_apartment
    open_b = open_b_building + open_b_apartment
    open_b_12m = [(f, s) for f, s in open_b if in_window(f, since_12m)]
    violations_12m = [(f, s) for f, s in violations if in_window(f, since_12m)]
    complaints_12m = [(f, s) for f, s in by_source.get("hpd_complaints", []) if in_window(f, since_12m)]
    # hcir-3275 carries `current_status` and `discharge_date` (source_registry.json). A building
    # discharged from the program no longer "appears in" AEP, so it does not fire W2. Exact
    # current_status wording was not observed in any fixture or live row, hence the substring match.
    def discharged(finding, status):
        meta = audit.get((finding.get("evidence_ids") or [None])[0], {})
        raw = meta.get("raw_record") or {}
        gone = _to_date(finding.get("discharge_date") or raw.get("discharge_date"))
        return (gone is not None and gone <= today) or "DISCHARG" in str(finding.get("recorded_status") or raw.get("current_status") or "").upper()

    aep = [(f, s) for f, s in by_source.get("hpd_aep", []) if not discharged(f, s)]
    aep_discharged = len(by_source.get("hpd_aep", [])) - len(aep)
    litigation_2y = [(f, s) for f, s in by_source.get("hpd_litigation", []) if in_window(f, since_2y)]
    evictions_2y = [(f, s) for f, s in by_source.get("executed_evictions", []) if in_window(f, since_2y)]
    ignored["undated_in_window_rules"] = sum(
        1 for src in ("hpd_violations", "hpd_complaints", "hpd_litigation", "executed_evictions")
        for f, _ in by_source.get(src, []) if _dated(f) is None)

    counts = {"open_class_c_violations": len(open_c), "open_class_c_building": len(open_c_building),
              "open_class_c_apartment": len(open_c_apartment), "open_class_b_violations": len(open_b),
              "open_class_b_building": len(open_b_building), "open_class_b_apartment": len(open_b_apartment),
              "open_class_b_violations_12m": len(open_b_12m),
              "hpd_complaints_12m": len(complaints_12m), "hpd_violations_12m": len(violations_12m),
              "hpd_aep_records": len(aep), "hpd_aep_discharged_ignored": aep_discharged, "hpd_litigation_2y": len(litigation_2y),
              "executed_evictions_2y": len(evictions_2y), "ignored": ignored}
    basis = {"counts": counts,
             "windows": {"investigation_date": today.isoformat(), "last_12_months_from": since_12m.isoformat(),
                         "last_2_years_from": since_2y.isoformat()},
             "coverage": {"checked": len(checked), "machine_readable": len(machine),
                          "fraction": round(len(checked) / len(machine), 3) if machine else 0.0,
                          "minimum_for_no_flags": MIN_MACHINE_COVERAGE},
             "apartment_level": {"open_class_c": len(open_c_apartment), "open_class_b": len(open_b_apartment),
                                 "records": [{"evidence_id": f["evidence_ids"][0], "inspection_date": f["event_date"], "class": f["severity"],
                                              "status": f["recorded_status"], "apartment": f["apartment"], "source_url": f["source_url"]}
                                             for f, st in (open_c_apartment + open_b_apartment)[:50]]},
             "unit_considered": unit if wanted_unit else None,
             "sources_checked": sources_checked, "sources_unavailable": sources_unavailable}

    # A bounded (page-capped) source returned only part of its records: its counts are lower bounds,
    # which is still valid for a rule that fires but cannot support "nothing found".
    bounded = {k for k, st in coverage.items() if st == "bounded"}
    basis["partial_sources"] = sorted(bounded)

    def split(building, apt):
        years = sorted({d.year for f, _ in building + apt if (d := _dated(f))})
        span = "" if not years else f"; inspected {years[0]}" + (f"-{years[-1]}" if years[-1] != years[0] else "")
        return f"{len(building)} for the building, {len(apt)} for individual apartments{span}."

    # Facts below every threshold, so NO FLAGS FOUND never hides them.
    also = []
    c2_fires = len(open_b_12m) >= 5
    c3_fires = len(complaints_12m) >= 5 and not violations_12m and "hpd_violations" not in bounded
    if open_b and not c2_fires:
        # Same window as C2 (open_b_12m): the reason Class B does not trigger CAUTION is the date window, not the count.
        many_b = len(open_b) != 1
        line = (f"{len(open_b)} open Class B HPD violation{'s' if many_b else ''} on record "
                f"({split(open_b_building, open_b_apartment).rstrip('.')}). ")
        if open_b_12m:
            line += f"{len(open_b_12m)} of them inspected in the last 12 months (CAUTION needs 5)."
        else:
            line += f"None {'were' if many_b else 'was'} inspected in the last 12 months, so {'they do' if many_b else 'it does'} not trigger CAUTION."
        also.append(line)
    if complaints_12m and not c3_fires:
        also.append(f"{len(complaints_12m)} HPD complaint{'s' if len(complaints_12m) != 1 else ''} in the last 12 months")
    if violations_12m and not (open_c or c2_fires):
        also.append(f"{len(violations_12m)} HPD violation{'s' if len(violations_12m) != 1 else ''} dated in the last 12 months, none open Class C")
    if aep_discharged:
        also.append(f"{aep_discharged} discharged HPD AEP record{'s' if aep_discharged != 1 else ''} (not counted)")
    if ignored["unit_scope"]:
        also.append(f"{ignored['unit_scope']} record{'s' if ignored['unit_scope'] != 1 else ''} for individual units not counted (no matching unit requested)")
    if ignored["undated_in_window_rules"]:
        also.append(f"{ignored['undated_in_window_rules']} record{'s' if ignored['undated_in_window_rules'] != 1 else ''} without a usable date, ignored by the time-window rules")
    basis["also_on_record"] = also[:6]

    gaps = []
    if identity_status not in VERIFIED_IDENTITY:
        gaps.append(f"Building identity is not verified ({identity_status or 'unknown'}).")
        basis["not_enough_data_reasons"] = gaps  # nothing can be attributed to an unverified building
        return {"verdict": NOT_ENOUGH_DATA, "rules_fired": [], "rules_checked": ["identity_gate"],
                "basis": basis, "disclaimer": _disclaimer(sources_unavailable)}
    for source in REQUIRED_SOURCES:
        if coverage.get(source) not in USABLE_COVERAGE:
            gaps.append(f"Required source {source} was not fully checked (status: {coverage.get(source) or 'not reported'}).")

    fired = []

    def fire(rule_id, level, summary, items, sources=()):
        hit = sorted(bounded & set(sources))
        if hit:  # a lower bound: say so, and never imply the count is final
            hpd = all(k.startswith("hpd_") for k in hit)
            summary = ("at least " if summary[:1].isdigit() else "") + summary.rstrip()
            stop = "." if summary.endswith(".") else ""  # the note is a clause before the full stop
            summary = summary[:-1] if stop else summary
            summary += f" ({'HPD results' if hpd else 'Results'} were truncated; the real number may be higher){stop}"
        fired.append({"rule_id": rule_id, "level": level, "summary": summary,
                      "evidence_ids": ids(items), "source_urls": urls(items)})

    if len(open_c) >= 3:
        fire("W1", WALK_AWAY, f"{len(open_c)} open Class C HPD violations (threshold 3): {split(open_c_building, open_c_apartment)}", open_c, ["hpd_violations"])
    if aep:
        fire("W2", WALK_AWAY, "The building appears in the HPD Alternative Enforcement Program.", aep, ["hpd_aep"])
    if open_c:
        fire("C1", CAUTION, f"{len(open_c)} open Class C HPD violation(s): {split(open_c_building, open_c_apartment)}", open_c, ["hpd_violations"])
    if c2_fires:
        fire("C2", CAUTION, f"{len(open_b_12m)} open Class B HPD violations dated in the last 12 months (threshold 5): "
             f"{split([x for x in open_b_12m if x in open_b_building], [x for x in open_b_12m if x in open_b_apartment])}", open_b_12m, ["hpd_violations"])
    if c3_fires:  # "no violations" cannot be confirmed from a truncated violations slice
        fire("C3", CAUTION, f"{len(complaints_12m)} HPD complaints in the last 12 months and no HPD violations in that window.", complaints_12m, ["hpd_complaints"])
    if litigation_2y or evictions_2y:
        fire("C4", CAUTION, f"{len(litigation_2y)} HPD litigation and {len(evictions_2y)} executed eviction record(s) in the last 2 years.",
             litigation_2y + evictions_2y, ["hpd_litigation", "executed_evictions"])

    if not fired and (not machine or len(checked) / len(machine) < MIN_MACHINE_COVERAGE):
        # Good news needs coverage: an absence of flags on a mostly unchecked building is not a result.
        gaps.append(f"coverage below {MIN_MACHINE_COVERAGE:.0%} of machine-readable sources ({len(checked)} of {len(machine)} checked)")
    if fired and gaps:
        basis["data_gaps"] = gaps  # rules fired on partial data; the gaps are listed, not hidden
    if not fired and gaps:
        # Only "nothing found" needs complete required sources; bad news from partial data stands.
        basis["not_enough_data_reasons"] = gaps
        return {"verdict": NOT_ENOUGH_DATA, "rules_fired": [], "rules_checked": list(RULES_CHECKED),
                "basis": basis, "disclaimer": _disclaimer(sources_unavailable)}

    verdict = WALK_AWAY if any(r["level"] == WALK_AWAY for r in fired) else CAUTION if fired else NO_FLAGS
    return {"verdict": verdict, "rules_fired": fired, "rules_checked": list(RULES_CHECKED),
            "basis": basis, "disclaimer": _disclaimer(sources_unavailable)}


def _disclaimer(unavailable):
    note = (" Sources not checked: " + ", ".join(unavailable) + ".") if unavailable else ""
    return DISCLAIMER + note
