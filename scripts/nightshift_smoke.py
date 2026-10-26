"""Nightshift smoke test: which model does the RESPONSE say handled each routing alias?

One tiny chat request per alias, sequential, no retries. Prints a table and saves a
secret-free receipt to docs/receipts/nightshift_smoke.json. Exit 0 if any alias
returned a model name, else 2. The token comes from the same private store the
Meterless provider uses and is never printed or saved.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.legal_agent.tools.meterless import APP_ID, RuntimeConfig  # noqa: E402
from scripts.zetaris_sql import load_env  # noqa: E402

# meterless/local is skipped (may start a 0.9 GB model download); fusion is not under test.
ALIASES = ["meterless/auto", "meterless/fast", "meterless/cheap", "meterless/deep"]
PROMPT = "Reply with exactly: ok"
TIMEOUT = 90
RECEIPT = Path(__file__).resolve().parents[1] / "docs" / "receipts" / "nightshift_smoke.json"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def probe(config, alias):
    row = {"alias": alias, "http_status": None, "model": None, "usage": None,
           "request_id": None, "elapsed_s": None, "error": None}
    body = {"model": alias, "messages": [{"role": "user", "content": PROMPT}],
            "stream": False, "max_tokens": 16}
    headers = {"Authorization": "Bearer " + config.token, "meterless-app": APP_ID,
               "meterless-scope": "user", "Content-Type": "application/json"}
    request = urllib.request.Request(config.base_url + "/chat/completions",
                                     data=json.dumps(body).encode(), headers=headers, method="POST")
    start = time.monotonic()
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=TIMEOUT) as response:
            row["http_status"] = response.status
            row["request_id"] = response.headers.get("x-meterless-request-id")
            try:
                data = json.loads(response.read(2_000_001))
            except ValueError:
                data = None
            if isinstance(data, dict):
                row["model"] = data.get("model") if isinstance(data.get("model"), str) else None
                row["usage"] = data.get("usage")
                if not row["model"]:
                    row["error"] = "no_model_in_response"
            else:
                row["error"] = "invalid_json"
    except urllib.error.HTTPError as error:  # body deliberately not read: may echo secrets
        row["http_status"] = error.code
        row["request_id"] = error.headers.get("x-meterless-request-id")
        row["error"] = "unauthorized" if error.code in {401, 403} else "http_error"
    except TimeoutError:
        row["error"] = "timeout"
    except urllib.error.URLError as error:
        row["error"] = "timeout" if isinstance(error.reason, TimeoutError) else "connection_failed"
    except OSError:
        row["error"] = "connection_failed"
    row["elapsed_s"] = round(time.monotonic() - start, 2)
    return row


def main() -> int:
    load_env()
    config = RuntimeConfig.from_env()
    if not config.token:
        print("No Meterless token configured; run scripts/meterless_runtime.py configure", file=sys.stderr)
        return 2
    rows = [probe(config, alias) for alias in ALIASES]
    receipt = {"timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "base_url": config.base_url, "prompt": PROMPT, "results": rows}
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n")

    print(f"{'alias':<16} {'status':<6} {'response model':<40} {'tokens':<8} {'sec':<6} error")
    for r in rows:
        total = (r["usage"] or {}).get("total_tokens", "-") if isinstance(r["usage"], dict) else "-"
        print(f"{r['alias']:<16} {str(r['http_status'] or '-'):<6} {str(r['model'] or '-'):<40} "
              f"{str(total):<8} {r['elapsed_s']:<6} {r['error'] or ''}")
    print("receipt:", RECEIPT.relative_to(RECEIPT.parents[2]))
    return 0 if any(r["model"] for r in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
