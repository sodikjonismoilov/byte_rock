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