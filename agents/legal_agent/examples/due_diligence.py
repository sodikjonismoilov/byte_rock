"""Offline address-first example. Fictional evidence, no external services."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import sample_task
from workflow import investigate_legal_issue

if __name__ == '__main__':
    task, context = sample_task()
    task.update(question='Due diligence before signing a lease', issue_types=[])
    print(json.dumps(investigate_legal_issue(task, context), indent=2))
