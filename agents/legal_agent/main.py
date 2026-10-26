from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

if __package__ and __package__.startswith("agents.legal_agent"):
    from .workflow import investigate_legal_issue
else:
    from workflow import investigate_legal_issue
if __package__ and __package__.startswith("agents.legal_agent"):
    from .identity import resolve_building_identity
else:
    from identity import resolve_building_identity
from pydantic import ValidationError
from werkzeug.exceptions import BadRequest

ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "data" / "sample_evidence.json"


def load_sample_bundle() -> dict:
    with SAMPLE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def evidence_for_address(address: str) -> list[dict]:
    bundle = load_sample_bundle()
    return [item for item in bundle["evidence"] if item.get("building_address") == address]


def sample_task(address: str = "214 East 7th Street") -> tuple[dict, dict]:
    bundle = load_sample_bundle()
    building = next(item for item in bundle["buildings"] if item["address"] == address)
    evidence = evidence_for_address(address)
    task = {
        "task_id": "demo-heat-001" if "7th" in address else f"demo-{address[:8].lower()}",
        "question": "What NYC housing duties and HPD records are relevant to this renter's heat and habitability concern?",
        "building": building,
        "issue_types": ["heat"],
        "evidence_ids": [item["evidence_id"] for item in evidence],
        "requested_by": "renter-due-diligence-demo",
    }
    if "Roosevelt" in address:
        task["task_id"] = "demo-pest-complaints"
        task["question"] = "Are there confirmed pest violations, or only complaints?"
        task["issue_types"] = ["pests"]
    if "145th" in address:
        task["task_id"] = "demo-pest-violation"
        task["question"] = "What pest-related legal sources apply to the confirmed HPD violation?"
        task["issue_types"] = ["pests"]
    if "Pierrepont" in address:
        task["task_id"] = "demo-thin-record"
        task["question"] = "Is there enough evidence of a water-supply code problem?"
        task["issue_types"] = ["water"]
    context = {"evidence": evidence, "notes": "Fictional sample evidence only."}
    return task, context


def create_app(*, snapshot_loader=None, meterless_settings=False) -> Flask:
    """HTTP clients submit requests, never authoritative identity/review state.

    snapshot_loader is a trusted server-side callable, not a JSON field. Without
    it the legacy endpoint is explicitly sample-only; Python callers can still
    pass trusted snapshots directly to investigate_legal_issue.
    """
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH']=2_000_000

    def client_context(value):
        if not isinstance(value,dict):raise ValueError('Invalid client context')
        protected={'identity','identity_candidates','record_matches','reconciliation','root_critic_outcome'}
        if protected.intersection(value):raise ValueError('Trusted review fields cannot be supplied by HTTP clients')
        if value.get('data_mode','sample')!='sample':raise ValueError('Live context must be loaded server-side')
        if value.get('data_provider','unspecified') not in {'unspecified','client_supplied_sample'}:
            raise ValueError('Provider selection is server-side')
        return {**value,'data_mode':'sample','data_provider':'client_supplied_sample'}

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "module": "legal-research-agent"})

    @app.errorhandler(ValidationError)
    @app.errorhandler(ValueError)
    @app.errorhandler(KeyError)
    @app.errorhandler(TypeError)
    @app.errorhandler(BadRequest)
    def invalid_input(error):
        return jsonify({"error":"invalid_input","message":"Supply valid task/context or address/context JSON matching the documented schemas."}), 400

    @app.post('/resolve-identity')
    def resolve_identity():
        payload = request.get_json(force=True, silent=False)
        if not isinstance(payload,dict) or not isinstance(payload.get('address'),str) or not payload['address'].strip():
            raise ValueError('Address required')
        context=payload.get('context') or {}
        if not isinstance(context,dict) or set(context)-{'unit','borough'}:
            raise ValueError('Identity provenance must be resolved server-side')
        return jsonify(resolve_building_identity(payload['address'],context))

    @app.post("/investigate")
    def investigate():
        payload = request.get_json(force=True, silent=False)
        if not isinstance(payload,dict):raise ValueError('JSON object required')
        if snapshot_loader:
            if payload.get('context'):raise ValueError('Context must be loaded server-side')
            context=snapshot_loader(payload['task'])
        else:
            context=client_context(payload.get('context') or {})
        result = investigate_legal_issue(payload["task"], context)
        return jsonify(result)

    if meterless_settings:
        if __package__ and __package__.startswith('agents.legal_agent'):
            from .tools.meterless_settings_ui import install_settings_routes
        else:
            from tools.meterless_settings_ui import install_settings_routes
        install_settings_routes(app)
    return app


def _print_demo(address: str) -> None:
    task, context = sample_task(address)
    result = investigate_legal_issue(task, context)
    print(json.dumps({"input_task": task, "output": result}, indent=2, default=str))


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Standalone Legal Research Agent demo")
    parser.add_argument("--meterless-settings",action="store_true",help="Enable local-only Meterless connection settings")
    parser.add_argument("--serve", action="store_true", help="Run a local Flask JSON endpoint")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument(
        "--address",
        default="214 East 7th Street",
        help="Fictional sample building address",
    )
    args = parser.parse_args()
    if args.serve:
        create_app(meterless_settings=args.meterless_settings).run(host=args.host, port=args.port, debug=False)
        return
    _print_demo(args.address)


if __name__ == "__main__":
    main()
