"""Demo web front end: type an address, watch the agents work, read the report.

    SAMPLE_MODE=true python3 webapp.py     # recorded replay, no credentials or network
    python3 webapp.py                      # live: needs .env.local and the Nightshift app open
Then open http://127.0.0.1:5050

This is a thin layer over the same code path as run.py (run.build_argv and
scripts.investigate_address.run_investigation). It adds no agent logic: the live
feed is the run's own trace.jsonl, read while the run is still writing it.
One investigation runs at a time (Zetaris temporary databases, one Nightshift).
"""
import argparse
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import run as front_door  # noqa: E402  (reuses run.py's argv builder and env defaults)
from scripts.investigate_address import argument_parser, run_investigation  # noqa: E402

OUTPUT_ROOT = Path(os.getenv("WEB_OUTPUT", ROOT / "outputs" / "web"))
FILES = ("renter_report.md", "trace.jsonl", "run_summary.json", "investigation_report.json", "investigation_report.md")
MAX_EVENT_CHARS = 3000
MAX_JOBS = 25

app = Flask(__name__, static_folder=str(ROOT / "web"), static_url_path="/static")
JOBS: dict = {}
RUN_LOCK = threading.Lock()


class Job:
    def __init__(self, case: dict, mode: str):
        self.id = uuid.uuid4().hex[:12]
        self.case = case
        self.mode = mode
        self.state = "running"  # running | done | error
        self.started = time.time()
        self.finished = None
        self.root = OUTPUT_ROOT / self.id
        self.dir = None
        self.result = None
        self.error = None

    def run_dir(self):
        if self.dir is None and self.root.exists():
            children = sorted(p for p in self.root.iterdir() if p.is_dir())
            if children:
                self.dir = children[0]
        return self.dir


def _cap(data):
    text = json.dumps(data, default=str)
    if len(text) <= MAX_EVENT_CHARS:
        return data
    return {"_truncated": True, "preview": text[:600]}


def _read_events(directory, after):
    """Complete trace lines after `after`. A half-written last line is left for the next poll."""
    path = directory / "trace.jsonl" if directory else None
    if not path or not path.exists():
        return [], after
    events, count = [], 0
    with path.open("rb") as handle:
        for raw in handle:
            if not raw.endswith(b"\n"):
                break
            count += 1
            if count <= after:
                continue
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            events.append({"type": event.get("type"), "ts": event.get("timestamp"), "data": _cap(event.get("data"))})
    return events, max(count, after)


def _work(job: Job):
    previous = os.environ.get("SAMPLE_MODE")
    os.environ["SAMPLE_MODE"] = "true" if job.mode == "sample" else "false"
    try:
        front_door.apply_env_defaults()
        args = argument_parser().parse_args(front_door.build_argv(job.case, job.root))
        summary, directory = run_investigation(args)
        job.dir = directory
        report = json.loads((directory / "investigation_report.json").read_text())
        job.result = {
            "run_id": summary["run_id"],
            "status": summary["status"],
            "exit_code": summary["exit_code"],
            "termination_reason": summary["termination_reason"],
            "data_mode": summary["data_mode"],
            "provider": summary["provider"],
            "identity_status": summary["identity_status"],
            "factual_findings": len(report.get("factual_findings", [])),
            "duration_seconds": summary.get("total_duration_seconds"),
            "models_used": sorted({m["model"] for m in summary.get("model_activity", []) if m.get("model")}),
            "files": [name for name in FILES if (directory / name).exists()],
        }
        job.state = "done"
    except SystemExit:
        job.state, job.error = "error", "Those inputs were rejected by the investigator. Check the address and borough."
    except Exception as error:  # surface the type, never a stack trace or credentials
        job.state, job.error = "error", f"{type(error).__name__}: {str(error)[:300]}"
    finally:
        if previous is None:
            os.environ.pop("SAMPLE_MODE", None)
        else:
            os.environ["SAMPLE_MODE"] = previous
        job.finished = time.time()
        RUN_LOCK.release()


FINDING_FIELDS = (
    "finding_id", "evidence_ids", "categories", "description", "agency", "dataset", "kind",
    "severity", "event_date", "recorded_status", "scope", "source_url", "why_it_matters",
)
COVERAGE_FIELDS = ("source", "title", "publisher", "status", "records_returned", "reason", "source_url")


def _result_details(directory: Path) -> dict:
    """What the page needs to draw the result, taken from the run's own report file."""
    try:
        report = json.loads((directory / "investigation_report.json").read_text())
    except (OSError, ValueError):
        return {}
    request_info = report.get("request") or {}
    identity = report.get("identity") or {}
    return {
        "address": identity.get("canonical_address") or request_info.get("normalized_address"),
        "borough": identity.get("borough") or request_info.get("borough"),
        "identifiers": identity.get("identifiers") or {},
        "verdict": report.get("verdict"),  # None when the verdict layer is not installed
        "findings": [{k: f.get(k) for k in FINDING_FIELDS} for f in report.get("factual_findings", [])],
        "coverage": [{k: c.get(k) for k in COVERAGE_FIELDS} for c in report.get("coverage", [])],
        "limitations": report.get("limitations", [])[:12],
    }


def _live_ready() -> bool:
    has_url = bool(os.getenv("ZETARIS_BASE_URL"))
    has_auth = bool(os.getenv("ZETARIS_API_KEY") or (os.getenv("ZETARIS_USERNAME") and os.getenv("ZETARIS_PASSWORD")))
    return has_url and has_auth


@app.get("/")
def index():
    return send_file(ROOT / "web" / "index.html")


def _sample_cases() -> list:
    """The committed sample inputs (input_examples/*.json), offered as one-click cases."""
    cases = []
    for path in sorted((ROOT / "input_examples").glob("*.json")):
        try:
            case = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(case, dict) and isinstance(case.get("address"), str) and case["address"].strip():
            cases.append({k: case.get(k) for k in ("address", "borough", "unit", "label")})
    return cases


@app.get("/api/config")
def config():
    return jsonify(
        default_mode="sample" if front_door.sample_mode() else "live",
        live_ready=_live_ready(),
        cases=_sample_cases(),
    )


@app.post("/api/runs")
def start_run():
    body = request.get_json(silent=True) or {}
    address = str(body.get("address") or "").strip()
    if not address or len(address) > 200:
        return jsonify(error="Enter a NYC street address (up to 200 characters)."), 400
    mode = "sample" if body.get("mode") == "sample" else "live"
    case = {"address": address}
    for key in ("borough", "unit"):
        value = str(body.get(key) or "").strip()
        if value:
            case[key] = value[:60]
    if not RUN_LOCK.acquire(blocking=False):
        return jsonify(error="An investigation is already running. Wait for it to finish."), 409
    job = Job(case, mode)
    JOBS[job.id] = job
    for stale in list(JOBS)[:-MAX_JOBS]:
        JOBS.pop(stale, None)
    threading.Thread(target=_work, args=(job,), daemon=True).start()
    return jsonify(id=job.id), 202


@app.get("/api/runs/<job_id>")
def run_status(job_id):
    job = JOBS.get(job_id) or abort(404)
    try:
        after = max(0, int(request.args.get("after", 0)))
    except ValueError:
        after = 0
    state = job.state  # read the state BEFORE the trace, so a "done" reply always carries every event
    events, nxt = _read_events(job.run_dir(), after)
    body = {
        "id": job.id,
        "state": state,
        "mode": job.mode,
        "case": job.case,
        "elapsed": round((job.finished or time.time()) - job.started, 1),
        "events": events,
        "next": nxt,
    }
    if state == "done" and job.result:
        directory = job.run_dir() or Path()
        body["result"] = {**job.result, **_result_details(directory)}
        report = directory / "renter_report.md"
        body["report_md"] = report.read_text() if report.exists() else ""
    if state == "error":
        body["error"] = job.error
    return jsonify(body)


@app.get("/api/runs/<job_id>/files/<name>")
def run_file(job_id, name):
    job = JOBS.get(job_id) or abort(404)
    directory = job.run_dir()
    if name not in FILES or directory is None or not (directory / name).exists():
        abort(404)
    return send_file(directory / name, as_attachment=request.args.get("download") == "1", mimetype="text/plain" if name.endswith((".md", ".jsonl")) else None)


def main():
    parser = argparse.ArgumentParser(description="SignSafe demo web page")
    parser.add_argument("--host", default=os.getenv("WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("WEB_PORT", "5050")))
    args = parser.parse_args()
    try:  # live mode reads Zetaris settings from .env.local; harmless if absent
        from scripts.zetaris_sql import load_env
        load_env()
    except Exception:
        pass
    mode = "recorded replay (SAMPLE_MODE)" if front_door.sample_mode() else "live"
    print(f"SignSafe demo page on http://{args.host}:{args.port}  [default mode: {mode}]")
    app.run(host=args.host, port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()