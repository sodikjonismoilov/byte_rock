import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
KEYS = ["SAMPLE_MODE", "RUN_REASONING", "LEGAL_MEMORY_DIR", "LLM_PROVIDER", "LEGAL_CONTEXT_MAX_BYTES",
        "LEGAL_CONTEXT_MAX_TOKENS", "LEGAL_MODEL_MAX_TOKENS", "INVESTIGATION_TIMEOUT"]


@pytest.fixture()
def run_py(monkeypatch):
    saved = {key: os.environ.get(key) for key in KEYS}  # run.py writes os.environ directly
    for key in KEYS:
        os.environ.pop(key, None)
    # The suite's pythonpath shadows the top-level `agents` package, so stub the heavy CLI import:
    # these tests only exercise run.py's own argv/env helpers.
    stub = types.ModuleType("scripts.investigate_address")
    stub.argument_parser = stub.run_investigation = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "scripts.investigate_address", stub)
    spec = importlib.util.spec_from_file_location("front_door_run", ROOT / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


CASE = {"address": "1 Mock Street", "borough": "Manhattan", "unit": None}


def test_sample_argv_uses_replay_and_deterministic(run_py, monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    argv = run_py.build_argv(CASE, Path("out"))
    assert argv[argv.index("--provider") + 1] == "replay"
    assert argv[argv.index("--reasoning") + 1] == "deterministic"
    assert "--replay" in argv


def test_live_argv_uses_configured_by_default(run_py):
    argv = run_py.build_argv(CASE, Path("out"))
    assert argv[argv.index("--provider") + 1] == "zetaris"
    assert argv[argv.index("--reasoning") + 1] == "configured"


def test_live_reasoning_can_be_overridden(run_py, monkeypatch):
    monkeypatch.setenv("RUN_REASONING", "nvidia")
    assert run_py.build_argv(CASE, Path("out"))[-1] == "nvidia"


def test_live_defaults_applied(run_py, monkeypatch):
    run_py.apply_env_defaults()
    assert os.environ["LLM_PROVIDER"] == "meterless"
    assert os.environ["LEGAL_CONTEXT_MAX_BYTES"] == "60000"
    assert os.environ["LEGAL_CONTEXT_MAX_TOKENS"] == "60000"
    assert os.environ["LEGAL_MODEL_MAX_TOKENS"] == "100000"
    assert os.environ["INVESTIGATION_TIMEOUT"] == "480"


def test_live_defaults_do_not_override_user_env(run_py, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("INVESTIGATION_TIMEOUT", "100")
    monkeypatch.setenv("LEGAL_CONTEXT_MAX_BYTES", "50000")
    run_py.apply_env_defaults()
    assert os.environ["LLM_PROVIDER"] == "nvidia"
    assert os.environ["INVESTIGATION_TIMEOUT"] == "100"
    assert os.environ["LEGAL_CONTEXT_MAX_BYTES"] == "50000"


@pytest.mark.parametrize("sample", ["true", "false"])
def test_memory_dir_default_in_both_modes(run_py, monkeypatch, sample):
    monkeypatch.setenv("SAMPLE_MODE", sample)
    run_py.apply_env_defaults()
    assert os.environ["LEGAL_MEMORY_DIR"] == str(ROOT / ".local" / "legal-memory")


def test_sample_mode_skips_live_defaults(run_py, monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    run_py.apply_env_defaults()
    assert "LLM_PROVIDER" not in os.environ and "INVESTIGATION_TIMEOUT" not in os.environ
