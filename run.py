"""Front door: JSON in, JSON out.

    SAMPLE_MODE=true python3 run.py input_examples/1.json   # no network, no credentials
    python3 run.py input_examples/1.json                    # live: needs .env.local

Input:  {"address": "1 Mock Street", "borough": "Manhattan", "unit": null}
Output: one JSON object on stdout. Full artifacts (renter report, audit report,
        trace.jsonl) are written to the run directory it names.
Exit:   0 completed, 2 inconclusive (partial factual report), 1 error / bad input.

SAMPLE_MODE replays a recorded capture. The only address in that capture is the
synthetic "1 Mock Street, Manhattan"; every run is labelled data_mode=recorded_replay.

Defaults (os.environ.setdefault, so your own environment always wins):
  both modes  LEGAL_MEMORY_DIR=.local/legal-memory   H-MEM (Meterless engine) on by default
  live mode   LLM_PROVIDER=meterless, LEGAL_CONTEXT_MAX_BYTES=60000,
              LEGAL_CONTEXT_MAX_TOKENS=60000, LEGAL_MODEL_MAX_TOKENS=100000,
              INVESTIGATION_TIMEOUT=480 (a model-backed run takes ~225 s)
Other knobs: RUN_REASONING (live, default "configured"), RUN_OUTPUT (default ./outputs).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from scripts.investigate_address import argument_parser, run_investigation  # noqa: E402

SAMPLE_REPLAY = ROOT / "agents/legal_agent/tests/fixtures/address_replay.synthetic.json"
SAMPLE_ADDRESS = "1 mock street"


LIVE_DEFAULTS = {
    "LLM_PROVIDER": "meterless",
    # The repo defaults (40000 bytes / 16000 tokens) stop the Planner before any model call.
    "LEGAL_CONTEXT_MAX_BYTES": "60000",
    "LEGAL_CONTEXT_MAX_TOKENS": "60000",
    "LEGAL_MODEL_MAX_TOKENS": "100000",
    "INVESTIGATION_TIMEOUT": "480",
}


def apply_env_defaults() -> None:
    os.environ.setdefault("LEGAL_MEMORY_DIR", str(ROOT / ".local" / "legal-memory"))
    if not sample_mode():
        for key, value in LIVE_DEFAULTS.items():
            os.environ.setdefault(key, value)


def sample_mode() -> bool:
    return os.getenv("SAMPLE_MODE", "").strip().lower() in {"1", "true", "yes"}


def load_case(path: str) -> dict:
    case = json.loads(Path(path).read_text())
    address = case.get("address") if isinstance(case, dict) else None
    if not isinstance(address, str) or not address.strip():
        raise ValueError('input must be a JSON object with a non-empty "address"')
    return case


def build_argv(case: dict, output: Path) -> list[str]:
    argv = [case["address"], "--output", str(output)]
    if case.get("borough"):
        argv += ["--borough", case["borough"]]
    if case.get("unit"):
        argv += ["--unit", case["unit"]]
    if sample_mode():
        argv += ["--provider", "replay", "--replay", str(SAMPLE_REPLAY), "--reasoning", "deterministic"]
    else:
        # LLM_PROVIDER=meterless + "configured" is the official Meterless/Nightshift path.
        argv += ["--provider", "zetaris", "--reasoning", os.getenv("RUN_REASONING", "configured")]
    return argv


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python3 run.py <input.json>", file=sys.stderr)
        return 1
    try:
        case = load_case(argv[0])
    except (OSError, ValueError) as error:  # json.JSONDecodeError is a ValueError
        print(json.dumps({"error": "bad_input", "message": str(error)}, indent=2))
        return 1

    if sample_mode() and case["address"].strip().lower() != SAMPLE_ADDRESS:
        print("SAMPLE_MODE only contains a recording for '1 Mock Street'; "
              "other addresses will come back mostly unavailable.", file=sys.stderr)

    apply_env_defaults()
    output = Path(os.getenv("RUN_OUTPUT", ROOT / "outputs"))
    args = argument_parser().parse_args(build_argv(case, output))
    summary, directory = run_investigation(args)
    report = json.loads((directory / "investigation_report.json").read_text())

    result = {
        "run_id": summary["run_id"],
        "status": summary["status"],
        "exit_code": summary["exit_code"],
        "termination_reason": summary["termination_reason"],
        "sample_mode": sample_mode(),
        "data_mode": summary["data_mode"],
        "provider": summary["provider"],
        "identity_status": summary["identity_status"],
        "factual_findings": len(report.get("factual_findings", [])),
        "models_used": sorted({m["model"] for m in summary["model_activity"] if m.get("model")}),
        "run_dir": str(directory),
        "renter_report": str(directory / "renter_report.md"),
        "trace": str(directory / "trace.jsonl"),
    }
    print(json.dumps(result, indent=2))
    return summary["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main()) 