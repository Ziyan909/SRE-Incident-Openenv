from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.server import ResetRequest, get_baseline, get_tasks, reset_environment, state_environment


def run_openenv_validate() -> dict[str, object]:
    try:
        completed = subprocess.run(
            ["openenv", "validate"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "command_available": False,
            "returncode": None,
            "stdout": "",
            "stderr": "openenv command not found",
        }

    return {
        "ok": completed.returncode == 0,
        "command_available": True,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def run_unit_tests() -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def run_api_smoke_test() -> dict[str, object]:
    tasks_payload = get_tasks()
    reset_payload = reset_environment(ResetRequest(tier="easy", seed=0))
    session_id = reset_payload["session_id"]
    state_payload = state_environment(session_id)
    baseline_payload = get_baseline(tier="easy", seed=0)

    return {
        "ok": bool(tasks_payload) and bool(session_id) and state_payload["session_id"] == session_id,
        "task_count": len(tasks_payload),
        "session_id_present": bool(session_id),
        "state_matches_session": state_payload["session_id"] == session_id,
        "baseline_has_score": "score" in baseline_payload,
    }


def main() -> int:
    validate = run_openenv_validate()
    tests = run_unit_tests()
    smoke = run_api_smoke_test()
    success = validate["ok"] and tests["ok"] and smoke["ok"]
    report = {
        "success": success,
        "openenv_validate": validate,
        "unit_tests": tests,
        "api_smoke_test": smoke,
    }
    print(json.dumps(report, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
