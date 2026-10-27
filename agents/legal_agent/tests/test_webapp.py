"""The demo web page's server (webapp.py): a thin layer over the same investigation code as run.py.

Like test_cli_runs.py, each check runs in a fresh process, because the suite's pythonpath
(agents/legal_agent first) shadows the top-level `agents` package that the root CLI imports.
"""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]

PRELUDE = '''
import json, sys, threading, time
from pathlib import Path
sys.path.insert(0, %r)
import webapp
client = webapp.app.test_client()

def wait_for(job_id, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/runs/{job_id}").get_json()
        if body["state"] != "running":
            return body
        time.sleep(0.2)
    raise AssertionError("run did not finish")
''' % str(ROOT)


def run_child(code, tmp_path):
    env = {**os.environ, "SAMPLE_MODE": "true", "WEB_OUTPUT": str(tmp_path / "web"), "LEGAL_MEMORY_DIR": str(tmp_path / "memory"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("RUN_REASONING", "LLM_PROVIDER", "INVESTIGATION_TIMEOUT"):
        env.pop(key, None)
    process = subprocess.run([sys.executable, "-B", "-c", PRELUDE + code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stdout + process.stderr


def test_pages_config_and_input_validation(tmp_path):
    run_child('''
page = client.get("/")
assert page.status_code == 200 and b"SignSafe" in page.data
for asset in ("app.js", "style.css", "board.js"):
    assert client.get(f"/static/{asset}").status_code == 200, asset
cfg = client.get("/api/config").get_json()
assert cfg["default_mode"] == "sample"
assert cfg["cases"] and all(case["address"] for case in cfg["cases"])
assert client.post("/api/runs", json={"address": "   "}).status_code == 400
assert client.post("/api/runs", json={"address": "x" * 201}).status_code == 400
assert client.post("/api/runs", data="not json").status_code == 400
assert client.get("/api/runs/doesnotexist").status_code == 404
''', tmp_path)


def test_recorded_run_streams_events_returns_result_and_serves_only_whitelisted_files(tmp_path):
    run_child('''
started = client.post("/api/runs", json={"address": "1 Mock Street", "borough": "Manhattan", "mode": "sample"})
assert started.status_code == 202
body = wait_for(started.get_json()["id"])
assert body["state"] == "done", body.get("error")
types = {event["type"] for event in body["events"]}
assert {"run.started", "run.finished"} <= types, types        # the live feed is the run's own trace
result = body["result"]
assert result["data_mode"] == "recorded_replay" and result["files"]
assert result["coverage"] and "findings" in result and "limitations" in result
assert "verdict" in result                                     # None until the verdict layer exists, never missing
assert client.get(f"/api/runs/{body['id']}?after={body['next']}").get_json()["events"] == []
job_id = body["id"]
assert client.get(f"/api/runs/{job_id}/files/trace.jsonl").status_code == 200
assert client.get(f"/api/runs/{job_id}/files/renter_report.md").status_code == 200
assert client.get(f"/api/runs/{job_id}/files/..%2F..%2Fwebapp.py").status_code == 404
assert client.get(f"/api/runs/{job_id}/files/.env.local").status_code == 404
''', tmp_path)


def test_one_investigation_at_a_time_and_trace_reader_edge_cases(tmp_path):
    run_child('''
release = threading.Event()
def slow(job):
    try:
        release.wait(10)
        job.state, job.result = "done", {}
    finally:
        webapp.RUN_LOCK.release()
webapp._work = slow
assert client.post("/api/runs", json={"address": "1 A St"}).status_code == 202
assert client.post("/api/runs", json={"address": "2 B St"}).status_code == 409
release.set()

folder = Path(%r)
folder.mkdir(parents=True, exist_ok=True)
trace = folder / "trace.jsonl"
trace.write_bytes(b'{"type": "a", "data": {}}\\n{"type": "b", "da')   # last line still being written
events, nxt = webapp._read_events(folder, 0)
assert [e["type"] for e in events] == ["a"] and nxt == 1
trace.write_bytes(b'{"type": "a", "data": {}}\\n{"type": "b", "data": {}}\\n')
events, nxt = webapp._read_events(folder, nxt)
assert [e["type"] for e in events] == ["b"] and nxt == 2
capped = webapp._cap({"blob": "x" * 10000})
assert capped["_truncated"] is True and len(json.dumps(capped)) < 1000
''' % str(tmp_path / "trace_dir"), tmp_path)

def test_result_details_carry_the_ai_reviewers_output_capped_and_only_when_present(tmp_path):
    run_child('''
folder = Path(%r)
folder.mkdir(parents=True, exist_ok=True)
long = "x" * 900
issue = lambda n: {"code": "VIOLATION_STATUS_UNVERIFIED", "message": long, "evidence_ids": ["wvxf-dwi5:" + str(n)], "follow_up_query": "secret-looking", "required_correction": "dropped"}
report = {
    "identity": {"canonical_address": "1 A ST", "borough": "MANHATTAN"},
    "legal_assessment": {
        "status": "inconclusive", "critic_outcome": "INCONCLUSIVE",
        "plans": [{"questions": ["q1", "q2"]}, {"questions": ["q3"]}],
        "findings": [{"finding_id": "fnd-%%d" %% n, "summary": long + "\\x1b[31m\\x00", "evidence_ids": ["wvxf-dwi5:1"] if n %% 2 else [], "sufficiency": "partial",
                      "missing_information": [long] * 9, "registration_contacts": [{"name": "must not leak"}]} for n in range(9)],
        "review_history": [{"outcome": "REVISE", "issues": [issue(0)], "revision_instructions": ["old"]},
                           {"outcome": "INCONCLUSIVE", "issues": [issue(n) for n in range(9)], "revision_instructions": [long] * 6}],
    },
    "board_update": {"legal_findings": []},
    "registration_contacts": [{"name": "must not leak"}],
}
(folder / "investigation_report.json").write_text(json.dumps(report))
legal = webapp._result_details(folder)["legal"]
assert set(legal) == {"status", "critic_outcome", "reviews", "published", "planner_questions", "observation_total", "observations_cited",
                      "observations", "critic_issues", "follow_ups"}, sorted(legal)
assert legal["published"] == 0 and legal["reviews"] == 2 and legal["planner_questions"] == 3
assert legal["status"] == "inconclusive" and legal["critic_outcome"] == "INCONCLUSIVE"
assert legal["observation_total"] == 9 and legal["observations_cited"] == 4 and len(legal["observations"]) == 6
assert set(legal["observations"][0]) == {"finding_id", "summary", "evidence_ids", "sufficiency", "missing_information"}
assert all(len(o["summary"]) == 400 and "\\x1b" not in o["summary"] and "\\x00" not in o["summary"] for o in legal["observations"])
assert all(len(m) == 400 for o in legal["observations"] for m in o["missing_information"]) and len(legal["observations"][0]["missing_information"]) == 6
assert len(legal["critic_issues"]) == 6 and set(legal["critic_issues"][0]) == {"code", "message", "evidence_ids"}
assert all(len(i["message"]) == 400 for i in legal["critic_issues"])
assert len(legal["follow_ups"]) == 4 and all(len(f) == 400 for f in legal["follow_ups"])  # the LAST review's, not the first's
assert "must not leak" not in json.dumps(webapp._result_details(folder)["legal"]) and "secret-looking" not in json.dumps(legal)

report["board_update"] = {"legal_findings": [{"finding_id": "fnd-1"}, {"finding_id": "fnd-2"}]}
(folder / "investigation_report.json").write_text(json.dumps(report))
assert webapp._result_details(folder)["legal"]["published"] == 2

report["legal_assessment"]["reasoning_mode"] = "demo_deterministic"  # scripted reviewers: no AI ran, so nothing to show
(folder / "investigation_report.json").write_text(json.dumps(report))
assert webapp._result_details(folder)["legal"] is None
report["legal_assessment"]["reasoning_mode"] = "llm:meterless"
(folder / "investigation_report.json").write_text(json.dumps(report))
assert webapp._result_details(folder)["legal"] is not None
del report["legal_assessment"]
(folder / "investigation_report.json").write_text(json.dumps(report))
assert webapp._result_details(folder)["legal"] is None
''' % str(tmp_path / "legal_report"), tmp_path)
