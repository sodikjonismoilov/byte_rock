import json
import re
from datetime import date
from pathlib import Path

import pytest

from verdict import (CAUTION, DATASET_SOURCES, MIN_MACHINE_COVERAGE, NO_FLAGS, NOT_ENOUGH_DATA, WALK_AWAY,
                     compute_verdict)

TODAY = date(2026, 10, 26)
DATASETS = {v: k for k, v in DATASET_SOURCES.items()}


def finding(source, n, *, severity=None, status="open", day="2026-09-01", scope="building", unit=None):
    dataset = DATASETS[source]
    return {"finding_id": f"fact-{dataset}:{n}", "evidence_ids": [f"{dataset}:{n}"], "dataset": dataset,
            "kind": "confirmed_violation", "severity": severity, "event_date": day, "recorded_status": status,
            "scope": scope, "unit": unit, "source_url": f"https://data.cityofnewyork.us/resource/{dataset}.json?id={n}"}


def make_report(findings=(), *, identity="verified", coverage=None):
    cov = {"hpd_violations": "retrieved", "hpd_complaints": "no_records", "hpd_aep": "no_records",
           "hpd_litigation": "no_records", "executed_evictions": "no_records"}
    cov.update(coverage or {})
    return {"identity": {"verification_status": identity},
            "coverage": [{"source": k, "status": v} for k, v in cov.items()],
            "factual_findings": list(findings), "evidence_audit": []}


def many(source, count, **kw):
    return [finding(source, i, **kw) for i in range(count)]


def run(report, unit=None, day=TODAY):
    return compute_verdict(report, day, unit)


def rule_ids(result):
    return [r["rule_id"] for r in result["rules_fired"]]


# (case id, findings, expected verdict, expected rule ids)
THRESHOLDS = [
    ("clean", [], NO_FLAGS, []),
    ("2 open class C: caution only", many("hpd_violations", 2, severity="C"), CAUTION, ["C1"]),
    ("3 open class C: walk away", many("hpd_violations", 3, severity="C"), WALK_AWAY, ["W1", "C1"]),
    ("closed class C ignored", many("hpd_violations", 3, severity="C", status="Violation Closed"), NO_FLAGS, []),
    ("open class A ignored", many("hpd_violations", 6, severity="A"), NO_FLAGS, []),
    ("4 open class B in 12m: clean", many("hpd_violations", 4, severity="B"), NO_FLAGS, []),
    ("5 open class B in 12m: caution", many("hpd_violations", 5, severity="B"), CAUTION, ["C2"]),
    ("5 open class B but one older than 12m", many("hpd_violations", 4, severity="B") + [finding("hpd_violations", 9, severity="B", day="2025-10-25")], NO_FLAGS, []),
    ("5 open class B incl. exactly 12m ago", many("hpd_violations", 4, severity="B") + [finding("hpd_violations", 9, severity="B", day="2025-10-26")], CAUTION, ["C2"]),
    ("4 complaints no violations: clean", many("hpd_complaints", 4), NO_FLAGS, []),
    ("5 complaints no violations: caution", many("hpd_complaints", 5), CAUTION, ["C3"]),
    ("5 complaints but a violation in window", many("hpd_complaints", 5) + [finding("hpd_violations", 1, severity="A", status="Closed")], NO_FLAGS, []),
    ("5 complaints, only an old violation", many("hpd_complaints", 5) + [finding("hpd_violations", 1, severity="A", day="2024-01-01")], CAUTION, ["C3"]),
    ("5 complaints, one older than 12m", many("hpd_complaints", 4) + [finding("hpd_complaints", 9, day="2025-10-25")], NO_FLAGS, []),
    ("AEP alone: walk away", [finding("hpd_aep", 1, day="2020-01-01")], WALK_AWAY, ["W2"]),
    ("litigation 1 year ago: caution", [finding("hpd_litigation", 1, day="2025-11-01")], CAUTION, ["C4"]),
    ("litigation exactly 2 years ago: caution", [finding("hpd_litigation", 1, day="2024-10-26")], CAUTION, ["C4"]),
    ("litigation just over 2 years ago: clean", [finding("hpd_litigation", 1, day="2024-10-25")], NO_FLAGS, []),
    ("eviction 3 months ago: caution", [finding("executed_evictions", 1, day="2026-07-01")], CAUTION, ["C4"]),
    ("eviction 3 years ago: clean", [finding("executed_evictions", 1, day="2023-07-01")], NO_FLAGS, []),
    ("future-dated record ignored in windows", [finding("hpd_litigation", 1, day="2027-01-01")], NO_FLAGS, []),
    ("undated record ignored in windows", [finding("hpd_litigation", 1, day=None)], NO_FLAGS, []),
    ("walk away outranks caution", many("hpd_violations", 3, severity="C") + [finding("hpd_litigation", 1)], WALK_AWAY, ["W1", "C1", "C4"]),
]


@pytest.mark.parametrize("name,findings,verdict,rules", THRESHOLDS, ids=[t[0] for t in THRESHOLDS])
def test_rule_thresholds(name, findings, verdict, rules):
    result = run(make_report(findings))
    assert result["verdict"] == verdict
    assert rule_ids(result) == rules


def test_windows_are_measured_from_the_investigation_date_not_today():
    report = make_report([finding("hpd_litigation", 1, day="2022-06-01")])
    assert run(report, day=date(2023, 1, 1))["verdict"] == CAUTION  # 7 months earlier
    assert run(report, day=date(2026, 10, 26))["verdict"] == NO_FLAGS  # 4+ years earlier
    assert run(report, day="2023-01-01")["basis"]["windows"]["last_2_years_from"] == "2021-01-01"
    twelve = make_report(many("hpd_violations", 5, severity="B", day="2025-12-01"))
    assert run(twelve, day=date(2026, 10, 26))["verdict"] == CAUTION
    assert run(twelve, day=date(2026, 10, 26))["verdict"] == CAUTION
    assert run(twelve, day=date(2027, 1, 1))["verdict"] == NO_FLAGS


def test_unit_scope_excluded_without_a_unit_and_included_when_it_matches():
    unit_findings = many("hpd_violations", 3, severity="C", scope="unit", unit="4B")
    report = make_report(unit_findings)
    assert run(report, unit=None)["verdict"] == NO_FLAGS
    assert run(report, unit="5A")["verdict"] == NO_FLAGS
    assert run(report, unit="Apt 4B")["verdict"] == NO_FLAGS  # "APT4B" is not "4B"
    assert run(report, unit="4b")["verdict"] == WALK_AWAY
    assert run(report, unit=None)["basis"]["counts"]["ignored"]["unit_scope"] == 3


def test_property_scope_counts_and_entity_scope_is_ignored():
    assert run(make_report(many("hpd_violations", 1, severity="C", scope="property")))["verdict"] == CAUTION
    entity = make_report(many("hpd_violations", 3, severity="C", scope="entity"))
    assert run(entity)["verdict"] == NO_FLAGS
    assert run(entity)["basis"]["counts"]["ignored"]["entity_scope"] == 3


def test_source_key_and_open_status_come_from_evidence_audit_when_present():
    f = finding("hpd_violations", 1, severity="C", status="NOV SENT OUT")  # raw wording alone would be 'unknown'
    report = make_report([f])
    report["evidence_audit"] = [{"evidence_id": f["evidence_ids"][0],
                                 "metadata": {"source_key": "hpd_violations", "normalized_status": "open"}}]
    assert run(report)["verdict"] == CAUTION
    assert run(make_report([f]))["verdict"] == NO_FLAGS


@pytest.mark.parametrize("identity", ["missing", "ambiguous", "unverified", None])
def test_unverified_identity_is_not_enough_data(identity):
    result = run(make_report(many("hpd_violations", 3, severity="C"), identity=identity))
    assert result["verdict"] == NOT_ENOUGH_DATA
    assert result["basis"]["not_enough_data_reasons"]
    assert result["rules_fired"] == []


@pytest.mark.parametrize("source", ["hpd_violations", "hpd_complaints"])
@pytest.mark.parametrize("status", ["unavailable", "bounded", "budget_exhausted", "failed", "not_selected"])
def test_unavailable_required_source_is_not_enough_data_even_if_others_are_clean(source, status):
    result = run(make_report([], coverage={source: status}))
    assert result["verdict"] == NOT_ENOUGH_DATA
    assert any(source in reason for reason in result["basis"]["not_enough_data_reasons"])


def test_missing_required_coverage_entry_is_not_enough_data():
    report = make_report([])
    report["coverage"] = [c for c in report["coverage"] if c["source"] != "hpd_complaints"]
    assert run(report)["verdict"] == NOT_ENOUGH_DATA
    assert run({"identity": {"verification_status": "verified"}})["verdict"] == NOT_ENOUGH_DATA


def test_unavailable_optional_source_does_not_block_and_is_listed():
    result = run(make_report([], coverage={"hpd_aep": "unavailable"}))
    assert result["verdict"] == NO_FLAGS
    assert "hpd_aep" in result["basis"]["sources_unavailable"]
    assert "hpd_aep" in result["disclaimer"]
    assert "hpd_violations" in result["basis"]["sources_checked"]


def test_sample_identity_counts_as_verified():
    assert run(make_report([], identity="sample"))["verdict"] == NO_FLAGS


def test_clean_report_shape():
    result = run(make_report([]))
    assert result["verdict"] == NO_FLAGS
    assert set(result) == {"verdict", "rules_fired", "rules_checked", "basis", "disclaimer"}
    assert result["rules_checked"] == ["W1", "W2", "C1", "C2", "C3", "C4"]
    assert {"counts", "windows", "sources_checked", "sources_unavailable"} <= set(result["basis"])
    assert "not a safety guarantee" in result["disclaimer"]
    assert "recorded agency data" in result["disclaimer"]


def test_every_fired_rule_carries_evidence_ids_and_matching_urls():
    for _, findings, _, _ in THRESHOLDS:
        for rule in run(make_report(findings))["rules_fired"]:
            assert rule["evidence_ids"], rule
            assert len(rule["source_urls"]) == len(rule["evidence_ids"])
            assert rule["level"] in {WALK_AWAY, CAUTION}


def test_sign_or_safe_wording_never_appears():
    outputs = [run(make_report(f)) for _, f, _, _ in THRESHOLDS]
    outputs += [run(make_report([], identity="missing")), run(make_report([], coverage={"hpd_violations": "unavailable"}))]
    for result in outputs:
        text = json.dumps(result)
        assert not re.search(r"\bSIGN\b", text)
        assert result["verdict"] in {NOT_ENOUGH_DATA, WALK_AWAY, CAUTION, NO_FLAGS}
        assert not re.search(r"\b(is|are) safe\b|\bsafe to (rent|sign|live)\b", text, re.I)


def test_deterministic_and_does_not_mutate_input():
    report = make_report(many("hpd_violations", 3, severity="C"))
    before = json.dumps(report, sort_keys=True)
    assert run(report) == run(report)
    assert json.dumps(report, sort_keys=True) == before


def test_dataset_map_matches_source_registry():
    registry = json.loads((Path(__file__).resolve().parents[1] / "data" / "source_registry.json").read_text())
    datasets = {s["key"]: s.get("dataset") for s in registry["sources"]}
    for dataset, key in DATASET_SOURCES.items():
        assert datasets[key] == dataset


def sample_style_coverage(checked_extra=0):
    """Like the recorded sample: 4 of 17 machine-readable sources checked, 3 manual-only."""
    cov = {"hpd_violations": "retrieved", "hpd_complaints": "no_records", "hpd_aep": "unavailable",
           "hpd_litigation": "unavailable", "executed_evictions": "unavailable"}
    cov.update({"hpd_buildings": "retrieved", **{f"src{i}": "unavailable" for i in range(8)}})
    for i in range(checked_extra):
        cov[f"src{i}"] = "no_records"
    cov.update({f"manual{i}": "manual_only" for i in range(3)})
    return cov


def test_threshold_constant_is_half():
    assert MIN_MACHINE_COVERAGE == 0.5


def test_sample_style_low_coverage_is_not_enough_data_instead_of_no_flags():
    result = run(make_report([], coverage=sample_style_coverage()))
    assert result["verdict"] == NOT_ENOUGH_DATA
    assert result["rules_fired"] == []
    assert result["basis"]["not_enough_data_reasons"] == ["coverage below 50% of machine-readable sources (3 of 14 checked)"]
    assert result["basis"]["coverage"]["machine_readable"] == 14  # manual-only excluded from the denominator


@pytest.mark.parametrize("extra,verdict", [(3, NOT_ENOUGH_DATA), (4, NO_FLAGS)])
def test_coverage_boundary_is_inclusive_at_half(extra, verdict):
    # 14 machine-readable sources: 3 base + extra checked; 7/14 = 50% passes, 6/14 does not.
    assert run(make_report([], coverage=sample_style_coverage(extra)))["verdict"] == verdict


def test_full_coverage_and_no_flags_is_no_flags_found():
    cov = {f"src{i}": "no_records" for i in range(17)}
    cov.update({"hpd_violations": "retrieved", "hpd_complaints": "no_records"})
    cov.update({f"manual{i}": "manual_only" for i in range(3)})
    result = run(make_report([], coverage=cov))
    assert result["verdict"] == NO_FLAGS
    assert result["basis"]["coverage"]["fraction"] == 1.0


def test_bad_news_still_fires_on_partial_coverage():
    cov = sample_style_coverage()  # only 3 of 14 machine-readable sources checked
    result = run(make_report(many("hpd_violations", 1, severity="C"), coverage=cov))
    assert result["verdict"] == CAUTION and rule_ids(result) == ["C1"]
    result = run(make_report(many("hpd_violations", 3, severity="C"), coverage=cov))
    assert result["verdict"] == WALK_AWAY


def test_required_source_gate_still_beats_coverage():
    cov = {f"src{i}": "no_records" for i in range(20)}
    cov["hpd_violations"] = "unavailable"
    assert run(make_report([], coverage=cov))["verdict"] == NOT_ENOUGH_DATA


def aep(n, **kw):
    return finding("hpd_aep", n, day="2020-01-01", **kw)


@pytest.mark.parametrize("name,extra", [
    ("status text", {"status": "Discharged"}),
    ("status text with round", {"status": "DISCHARGED - ROUND 3"}),
    ("discharge_date on finding", {"discharge_date": "2023-05-01"}),
])
def test_discharged_aep_does_not_fire(name, extra):
    f = aep(1, status=extra.get("status", "Active"))
    if "discharge_date" in extra:
        f["discharge_date"] = extra["discharge_date"]
    result = run(make_report([f]))
    assert result["verdict"] == NO_FLAGS
    assert result["basis"]["counts"]["hpd_aep_discharged_ignored"] == 1


def test_discharge_date_from_raw_record_in_evidence_audit_and_future_date():
    f = aep(1, status="Active")
    report = make_report([f])
    report["evidence_audit"] = [{"evidence_id": f["evidence_ids"][0], "metadata": {"raw_record": {"discharge_date": "2023-05-01"}}}]
    assert run(report)["verdict"] == NO_FLAGS
    report["evidence_audit"][0]["metadata"]["raw_record"]["discharge_date"] = "2027-05-01"  # not yet discharged
    assert run(report)["verdict"] == WALK_AWAY


def test_active_aep_still_fires_and_discharged_one_is_not_cited():
    active, gone = aep(1, status="Active"), aep(2, status="Discharged")
    result = run(make_report([active, gone]))
    assert result["verdict"] == WALK_AWAY
    assert result["rules_fired"][0]["evidence_ids"] == [active["evidence_ids"][0]]


def test_replay_style_manual_sources_are_excluded_via_match_field():
    report = make_report([], coverage={f"src{i}": "no_records" for i in range(2)})
    report["coverage"] += [{"source": f"court{i}", "status": "unavailable", "match_field": "manual"} for i in range(8)]
    result = run(report)  # 7 machine-readable sources, all checked; the 8 manual ones do not count against it
    assert result["verdict"] == NO_FLAGS
    assert result["basis"]["coverage"] == {"checked": 7, "machine_readable": 7, "fraction": 1.0, "minimum_for_no_flags": 0.5}


# ---- apartment-level violations held by the Critic (R8, unit_mismatch) --------------------------------

IDENTIFIERS = {"hpd_building_id": "2342", "bin": "1036164", "bbl": "1012980034"}


def apartment_record(n, *, cls="C", status="open", day="2026-03-01", apartment="1D", conflict=None, decision="quarantine",
                     rule="R8", method="unit_mismatch"):
    """(audit row, decision row) for a violation the Critic held because it is tied to one apartment."""
    eid = f"wvxf-dwi5:{9000 + n}"
    meta = {"source_key": "hpd_violations", "match_method": method, "normalized_status": status, **{k: v for k, v in IDENTIFIERS.items()},
            "source_url": f"https://data.cityofnewyork.us/resource/wvxf-dwi5.json?violationid={9000 + n}",
            "raw_record": {"class": cls, "apartment": apartment, "inspectiondate": f"{day}T00:00:00.000"}}
    meta.update(conflict or {})
    return ({"evidence_id": eid, "violation_class": cls, "date": day, "status": "Open", "metadata": meta},
            {"record_id": eid, "decision": decision, "rule": rule})


def with_apartments(report, records):
    report["identity"]["identifiers"] = dict(IDENTIFIERS)
    report["evidence_audit"] += [a for a, _ in records]
    report["record_decisions"] = report.get("record_decisions", []) + [d for _, d in records]
    return report


def apt_report(building=(), apartments=(), **kw):
    return with_apartments(make_report(list(building)), [apartment_record(i, **kw) for i in range(apartments)] if isinstance(apartments, int) else list(apartments))


def test_zero_building_and_eleven_apartment_level_is_walk_away_not_no_flags():
    result = run(apt_report(apartments=11))
    assert result["verdict"] == WALK_AWAY
    assert rule_ids(result) == ["W1", "C1"]
    assert len(result["rules_fired"][0]["evidence_ids"]) == 11
    assert result["basis"]["apartment_level"]["open_class_c"] == 11
    assert len(result["basis"]["apartment_level"]["records"]) == 11


def test_one_building_plus_ten_apartment_level_is_walk_away():
    result = run(apt_report(building=many("hpd_violations", 1, severity="C"), apartments=10))
    assert result["verdict"] == WALK_AWAY
    assert "11 open Class C HPD violations (threshold 3): 1 for the building, 10 for individual apartments; inspected 2026." in result["rules_fired"][0]["summary"]


def test_years_span_appears_in_the_rule_text():
    records = [apartment_record(0, day="2025-02-01"), apartment_record(1, day="2026-03-01"), apartment_record(2, day="2025-07-01")]
    summary = run(apt_report(apartments=records))["rules_fired"][0]["summary"]
    assert "3 open Class C HPD violations (threshold 3): 0 for the building, 3 for individual apartments; inspected 2025-2026." in summary


def test_closed_apartment_level_records_are_not_counted():
    result = run(apt_report(apartments=[apartment_record(i, status="closed") for i in range(5)]))
    assert result["verdict"] == NO_FLAGS
    assert result["basis"]["apartment_level"] == {"open_class_c": 0, "open_class_b": 0, "records": []}


def test_conflicting_identifiers_are_not_counted():
    for conflict in ({"bin": "9999999"}, {"hpd_building_id": "1"}, {"bbl": "1000000001"}):
        result = run(apt_report(apartments=[apartment_record(i, conflict=conflict) for i in range(5)]))
        assert result["verdict"] == NO_FLAGS, conflict


def test_only_unit_mismatch_r8_quarantines_are_counted():
    others = [apartment_record(0, decision="reject", rule="R5"), apartment_record(1, rule="R6"),
              apartment_record(2, method="bin"), apartment_record(3, decision="accept", rule=None)]
    assert run(apt_report(apartments=others))["verdict"] == NO_FLAGS


def test_apartment_level_open_class_b_counts_toward_the_class_b_rules():
    result = run(apt_report(apartments=[apartment_record(i, cls="B") for i in range(5)]))
    assert rule_ids(result) == ["C2"] and result["verdict"] == CAUTION
    assert "0 for the building, 5 for individual apartments" in result["rules_fired"][0]["summary"]
    assert result["basis"]["apartment_level"]["open_class_b"] == 5


def test_old_open_class_c_in_either_group_is_never_no_flags_but_lone_class_b_is_below_threshold():
    for report in (apt_report(building=many("hpd_violations", 1, severity="C", day="2001-01-01")),
                   apt_report(apartments=[apartment_record(0, cls="C", day="2001-01-01")])):
        assert run(report)["verdict"] in {CAUTION, WALK_AWAY}
    for report in (apt_report(building=many("hpd_violations", 1, severity="B", day="2001-01-01")),
                   apt_report(apartments=[apartment_record(0, cls="B", day="2001-01-01")])):
        result = run(report)
        assert result["verdict"] == NO_FLAGS and "C5" not in result["rules_checked"]
        assert result["basis"]["also_on_record"]


def test_accepted_unit_record_is_counted_once_as_building_level():
    accepted = finding("hpd_violations", 1, severity="C", scope="unit", unit="4B")
    held = apartment_record(2, apartment="1D")
    report = with_apartments(make_report([accepted]), [held])
    # also present in the audit/decisions as an accepted record: must not be re-counted as held
    twin, _ = apartment_record(1)
    twin["evidence_id"] = accepted["evidence_ids"][0]
    report["evidence_audit"].append(twin)
    report["record_decisions"].append({"record_id": twin["evidence_id"], "decision": "quarantine", "rule": "R8"})
    counts = run(report, unit="4B")["basis"]["counts"]
    assert (counts["open_class_c_building"], counts["open_class_c_apartment"], counts["open_class_c_violations"]) == (1, 1, 2)


def test_apartment_record_list_is_capped_and_public_fields_only():
    result = run(apt_report(apartments=60))
    records = result["basis"]["apartment_level"]["records"]
    assert len(records) == 50 and result["basis"]["apartment_level"]["open_class_c"] == 60
    assert set(records[0]) == {"evidence_id", "inspection_date", "class", "status", "apartment", "source_url"}


# ---- also_on_record: sub-threshold facts NO FLAGS FOUND must not hide ---------------------------------

def test_also_on_record_lists_subthreshold_class_b_and_complaints():
    report = apt_report(apartments=[apartment_record(i, cls="B", day="2020-07-05", apartment="9F") for i in range(2)])
    report["factual_findings"] += many("hpd_complaints", 3)
    result = run(report)
    assert result["verdict"] == NO_FLAGS
    assert result["basis"]["also_on_record"] == [
        "2 open Class B HPD violations on record (0 for the building, 2 for individual apartments; inspected 2020). "
        "None were inspected in the last 12 months, so they do not trigger CAUTION.",
        "3 HPD complaints in the last 12 months"]


def test_also_on_record_is_empty_for_a_clean_report_and_skips_zero_items():
    assert run(make_report([]))["basis"]["also_on_record"] == []


def test_also_on_record_is_capped_at_six_and_kept_when_not_enough_data():
    report = apt_report(apartments=[apartment_record(0, cls="B")])
    report["factual_findings"] += many("hpd_complaints", 2) + many("hpd_violations", 1, severity="A", status="Closed")
    report["factual_findings"] += [finding("hpd_litigation", 1, day=None), finding("hpd_violations", 50, severity="A", scope="unit", unit="9Z")]
    report["factual_findings"] += [finding("hpd_aep", 2, status="Discharged")]
    assert len(run(report)["basis"]["also_on_record"]) <= 6
    low = make_report([], coverage=sample_style_coverage())
    low["factual_findings"] = many("hpd_complaints", 2)
    result = run(low)
    assert result["verdict"] == NOT_ENOUGH_DATA and result["basis"]["also_on_record"] == ["2 HPD complaints in the last 12 months"]


def test_class_b_counts_only_through_c2_building_plus_apartment():
    result = run(apt_report(building=many("hpd_violations", 2, severity="B"), apartments=[apartment_record(i, cls="B") for i in range(3)]))
    assert rule_ids(result) == ["C2"]
    assert "0 for the building" not in result["rules_fired"][0]["summary"] and "2 for the building, 3 for individual apartments" in result["rules_fired"][0]["summary"]
    assert run(apt_report(apartments=[apartment_record(i, cls="B") for i in range(4)]))["verdict"] == NO_FLAGS


# ---- bounded (page-capped) sources ---------------------------------------------------------------------

SUFFIX = "(HPD results were truncated; the real number may be higher)."


def test_rule_firing_on_a_bounded_required_source_stands_and_says_at_least():
    result = run(make_report(many("hpd_violations", 3, severity="C"), coverage={"hpd_violations": "bounded", "hpd_complaints": "bounded"}))
    assert result["verdict"] == WALK_AWAY
    assert result["rules_fired"][0]["summary"].startswith("at least 3 open Class C HPD violations")
    assert all(r["summary"].endswith(SUFFIX) for r in result["rules_fired"] if r["rule_id"] in {"W1", "C1"})
    assert result["basis"]["partial_sources"] == ["hpd_complaints", "hpd_violations"]
    assert "Required source hpd_violations" in " ".join(result["basis"]["data_gaps"])


def test_bounded_required_source_with_no_rule_fired_is_not_enough_data():
    result = run(make_report([], coverage={"hpd_violations": "bounded"}))
    assert result["verdict"] == NOT_ENOUGH_DATA
    assert result["basis"]["partial_sources"] == ["hpd_violations"]


def test_complete_sources_have_no_truncation_text_and_no_partial_sources():
    result = run(make_report(many("hpd_violations", 3, severity="C")))
    assert result["basis"]["partial_sources"] == []
    assert not any("truncated" in r["summary"] or r["summary"].startswith("at least") for r in result["rules_fired"])


def test_unavailable_required_source_does_not_hide_bad_news_from_other_data():
    result = run(make_report([finding("hpd_aep", 1, day="2020-01-01")], coverage={"hpd_complaints": "unavailable"}))
    assert result["verdict"] == WALK_AWAY and rule_ids(result) == ["W2"]
    assert not result["rules_fired"][0]["summary"].endswith(")")  # not bounded: no truncation wording


def test_c3_does_not_fire_when_violations_are_truncated():
    result = run(make_report(many("hpd_complaints", 5), coverage={"hpd_violations": "bounded"}))
    assert result["verdict"] == NOT_ENOUGH_DATA
    assert result["basis"]["also_on_record"] == ["5 HPD complaints in the last 12 months"]
    complete = run(make_report(many("hpd_complaints", 5), coverage={"hpd_complaints": "bounded"}))
    assert rule_ids(complete) == ["C3"] and complete["rules_fired"][0]["summary"].startswith("at least 5 HPD complaints")


def test_class_b_line_says_none_inside_the_window_when_all_are_old():
    old = many("hpd_violations", 1, severity="B", day="1990-05-01") + [finding("hpd_violations", 7, severity="B", day="2019-05-01")]
    report = apt_report(building=old, apartments=[apartment_record(i, cls="B", day="2015-01-01") for i in range(3)])
    line = run(report)["basis"]["also_on_record"][0]
    assert line == ("5 open Class B HPD violations on record (2 for the building, 3 for individual apartments; inspected 1990-2019). "
                    "None were inspected in the last 12 months, so they do not trigger CAUTION.")


def test_class_b_line_counts_the_ones_inside_the_window_when_fewer_than_five():
    report = apt_report(building=many("hpd_violations", 1, severity="B", day="2025-12-01") + [finding("hpd_violations", 7, severity="B", day="2019-05-01")],
                        apartments=[apartment_record(i, cls="B", day="2026-03-01") for i in range(2)] + [apartment_record(5, cls="B", day="2018-01-01")])
    result = run(report)
    assert result["verdict"] == NO_FLAGS
    assert result["basis"]["also_on_record"][0].endswith("3 of them inspected in the last 12 months (CAUTION needs 5).")
    assert "None" not in result["basis"]["also_on_record"][0]


def test_class_b_line_singular_and_absent_when_c2_fires():
    one = run(apt_report(building=many("hpd_violations", 1, severity="B", day="2001-01-01")))["basis"]["also_on_record"][0]
    assert one.startswith("1 open Class B HPD violation on record") and one.endswith("None was inspected in the last 12 months, so it does not trigger CAUTION.")
    fires = run(make_report(many("hpd_violations", 5, severity="B")))
    assert rule_ids(fires) == ["C2"] and not any("Class B" in x for x in fires["basis"]["also_on_record"])


def test_truncation_note_is_a_clause_before_the_full_stop():
    hpd = run(make_report(many("hpd_violations", 3, severity="C"), coverage={"hpd_violations": "bounded"}))
    for rule in hpd["rules_fired"]:
        assert rule["summary"].endswith("(HPD results were truncated; the real number may be higher).")
        assert ". (" not in rule["summary"] and rule["summary"].count("truncated") == 1
    assert "inspected 2026 (HPD results were truncated" in hpd["rules_fired"][0]["summary"]
    other = run(make_report([finding("hpd_litigation", 1, day="2026-01-01")], coverage={"hpd_litigation": "bounded"}))
    assert other["rules_fired"][0]["summary"].endswith("in the last 2 years (HPD results were truncated; the real number may be higher).")
    non_hpd = run(make_report([finding("executed_evictions", 1, day="2026-01-01")], coverage={"executed_evictions": "bounded"}))
    assert non_hpd["rules_fired"][0]["summary"].endswith("(Results were truncated; the real number may be higher).")
