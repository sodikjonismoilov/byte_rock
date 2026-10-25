"""
SignSafe Critic agent — ByteRock, GenAI.Works Open Agent Hackathon 2026.

The Critic is basically a bouncer for the evidence board. Two vetoes:

  1. Match veto: links the Matcher proposes get rejected or quarantined
     when they look like bad address matches.
  2. Evidence veto: an Investigator finding with no record IDs behind it,
     or IDs that are not on the board, gets rejected. No evidence, no
     finding.

Rules decide first — they are fast, free and easy to audit. The LLM pass
(LLM.generate -> Nightshift) only sees quarantined items, and can promote
or demote them with a written reason. Every decision comes back as a
trace entry: {record_id, decision, rule, reason, decided_by, model}.

The rules path needs nothing else running, so this also works standalone
in SAMPLE_MODE, with no Zetaris and no Nightshift.

Written by Crypto (Alif Cryptovan Sinaga) for team ByteRock.
"""

from __future__ import annotations

import json
import math
import re
import sys

# config

GEO_REJECT_M = 150.0        # R3: farther away than this, it is not this building
CONFIDENCE_FLOOR = 0.6      # R8: below this an uncorroborated link gets held

# address helpers

_EXPANSIONS = {
    "ST": "STREET", "AVE": "AVENUE", "BLVD": "BOULEVARD", "RD": "ROAD",
    "PL": "PLACE", "E": "EAST", "W": "WEST", "N": "NORTH", "S": "SOUTH",
}
_UNIT_MARKERS = {"APT", "UNIT", "STE", "SUITE", "#", "FL", "FLOOR", "RM", "ROOM"}


def normalize_address(raw: str) -> str:
    """Normalize an address so two spellings of the same place compare
    equal: uppercase, punctuation dropped, unit designators stripped,
    suffixes and directions expanded, ordinal endings removed
    (55TH -> 55)."""
    text = re.sub(r"[^A-Z0-9 ]", " ", (raw or "").upper())
    tokens = text.split()
    out: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:            # the token after APT/UNIT/# is the unit id
            skip_next = False
            continue
        if tok in _UNIT_MARKERS:
            skip_next = True
            continue
        tok = re.sub(r"^(\d+)(ST|ND|RD|TH)$", r"\1", tok)   # ordinals
        out.append(_EXPANSIONS.get(tok, tok))
    return " ".join(out)


def has_unit_marker(raw: str) -> bool:
    tokens = re.sub(r"[^A-Z0-9# ]", " ", (raw or "").upper()).split()
    return any(t in _UNIT_MARKERS for t in tokens)


def house_number(normalized: str) -> str:
    parts = normalized.split()
    return parts[0] if parts else ""


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# the Critic

def _decision(record_id, decision, rule, reason, decided_by="rule", model=None):
    return {
        "record_id": record_id,
        "decision": decision,          # accept | reject | quarantine
        "rule": rule,                  # R1..R10 or None
        "reason": reason,
        "decided_by": decided_by,      # rule | llm
        "model": model,                # Nightshift model name when the llm decided
    }


def review_link(record: dict, building: dict, pinned: list[dict] | None = None) -> dict:
    """Match veto. `record` is one candidate link from the Matcher,
    `building` is the building card it claims to belong to, and `pinned`
    is what is already accepted onto that building (needed for R5)."""
    pinned = pinned or []
    rid = record.get("record_id", "?")

    rec_bbl = str(record.get("bbl", ""))
    bld_bbl = str(building.get("bbl", ""))

    # R2 - borough conflict (the first BBL digit is the borough code)
    if rec_bbl and bld_bbl and rec_bbl[0] != bld_bbl[0]:
        return _decision(rid, "reject", "R2",
                         f"Borough conflict: record BBL starts {rec_bbl[0]}, building is borough {bld_bbl[0]}.")

    # R1 - BBL mismatch (the BBL is the gold key; different BBL, different building)
    if rec_bbl and bld_bbl and rec_bbl != bld_bbl:
        return _decision(rid, "reject", "R1",
                         f"BBL mismatch: record {rec_bbl} != building {bld_bbl}.")

    # R3 - geo distance
    if None not in (record.get("lat"), record.get("lon"),
                    building.get("lat"), building.get("lon")):
        dist = haversine_m(record["lat"], record["lon"],
                           building["lat"], building["lon"])
        if dist > GEO_REJECT_M:
            return _decision(rid, "reject", "R3",
                             f"Coordinates {dist:.0f} m from the building (> {GEO_REJECT_M:.0f} m).")

    # R4 - record older than the building itself
    rdate = str(record.get("record_date", ""))
    ybuilt = building.get("year_built") or record.get("year_built")
    if rdate[:4].isdigit() and ybuilt and int(rdate[:4]) < int(ybuilt):
        return _decision(rid, "reject", "R4",
                         f"Record dated {rdate[:4]}, building built {ybuilt}.")

    # R5 - same-dataset collision (same event already pinned under another ID)
    rec_norm = normalize_address(record.get("address_raw", ""))
    for other in pinned:
        if other.get("record_id") == rid:
            continue
        if (other.get("dataset") == record.get("dataset")
                and other.get("record_date") == record.get("record_date")
                and normalize_address(other.get("address_raw", "")) == rec_norm):
            return _decision(rid, "reject", "R5",
                             f"Same {record.get('dataset')} event already pinned as {other.get('record_id')}.")

    # R6 - addresses diverge (unit artifacts, house-number variants)
    bld_norm = normalize_address(building.get("address_raw", ""))
    if has_unit_marker(record.get("address_raw", "")) and not has_unit_marker(building.get("address_raw", "")):
        return _decision(rid, "quarantine", "R6",
                         "Record carries a unit designator the building card lacks — may be a unit-level hit on the wrong building.")
    if house_number(rec_norm) != house_number(bld_norm) or rec_norm != bld_norm:
        return _decision(rid, "quarantine", "R6",
                         f"Address diverges after normalization: '{rec_norm}' vs '{bld_norm}'.")

    # R7 - building class disagrees with the card and no permit explains it
    if (record.get("building_class") and building.get("building_class")
            and record["building_class"] != building["building_class"]
            and not record.get("bridging_permit")):
        return _decision(rid, "quarantine", "R7",
                         f"Building class {record['building_class']} conflicts with card {building['building_class']}, no alteration permit bridges it.")

    # R8 - low confidence and nothing else backs the link up
    conf = record.get("matcher_confidence")
    if conf is not None and conf < CONFIDENCE_FLOOR and not record.get("corroborated"):
        return _decision(rid, "quarantine", "R8",
                         f"Matcher confidence {conf} < {CONFIDENCE_FLOOR} and no second dataset confirms the link.")

    return _decision(rid, "accept", None, "Passed all Critic rules.")


def review_finding(finding: dict, board_record_ids: set[str]) -> dict:
    """Evidence veto. No sources, or sources that are not on the board,
    and the finding never reaches the Reporter."""
    ids = finding.get("record_ids") or []
    if not ids:
        return _decision("(finding)", "reject", "R9",
                         "Finding carries no record IDs — no evidence, no finding.")
    phantom = [i for i in ids if i not in board_record_ids]
    if phantom:
        return _decision("(finding)", "reject", "R10",
                         f"Finding cites records not on the board: {', '.join(phantom)}.")
    return _decision("(finding)", "accept", None, "All cited records are on the board.")


# LLM gray zone
# Quarantined items are the only things the LLM ever sees. This gets
# wired to the Squad's LLM.generate() (Nightshift) when that lands.
# Until then a quarantine just stays a quarantine, which is the safe
# default anyway.

def llm_review(decision_entry: dict, record: dict, building: dict) -> dict:
    """Stub for the Nightshift judge pass. Has to return the entry with
    the decision promoted or demoted, decided_by='llm' and model set."""
    raise NotImplementedError("Wire to LLM.generate() via Nightshift.")


# fixture runner

def run_fixtures(path: str) -> int:
    with open(path) as fh:
        pack = json.load(fh)
    building = pack["building_card"]
    pinned: list[dict] = []
    board_ids: set[str] = set()
    passed = failed = 0

    print(f"CRITIC TRACE — building {building['address_raw']} (BBL {building['bbl']})")
    for case in pack["cases"]:
        if "record" in case:
            entry = review_link(case["record"], building, pinned)
            if entry["decision"] == "accept":
                pinned.append(case["record"])
                board_ids.add(case["record"]["record_id"])
        else:
            entry = review_finding(case["finding"], board_ids)

        ok = entry["decision"] == case["expect"] and entry["rule"] == case["rule"]
        passed += ok
        failed += (not ok)
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {case['id']} -> {entry['decision'].upper():10s} "
              f"rule={entry['rule'] or '-':4s} by={entry['decided_by']:4s} :: {entry['reason']}")
        if not ok:
            print(f"       expected {case['expect']} / {case['rule']} — {case['note']}")

    print(f"\n{passed}/{passed + failed} fixtures passed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_fixtures(sys.argv[1] if len(sys.argv) > 1 else "critic-fixtures.json"))
