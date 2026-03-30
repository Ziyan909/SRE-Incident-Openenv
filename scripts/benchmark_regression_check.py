from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from env.baseline_runner import run_benchmark
from env.models import TaskTier


MIN_OVERALL_AVERAGE = 0.70
MIN_OVERALL_SOLVE_RATE = 0.60
MIN_HARD_AVERAGE = 0.30


def main() -> int:
    report = run_benchmark(provider="scripted", seeds_per_scenario=1)
    hard_summary = next(item for item in report.tier_summaries if item.tier == TaskTier.HARD)
    checks = {
        "overall_average_score": report.overall_average_score >= MIN_OVERALL_AVERAGE,
        "overall_solve_rate": report.overall_solve_rate >= MIN_OVERALL_SOLVE_RATE,
        "hard_average_score": hard_summary.average_score >= MIN_HARD_AVERAGE,
    }
    payload = {
        "ok": all(checks.values()),
        "checks": checks,
        "overall_average_score": report.overall_average_score,
        "overall_solve_rate": report.overall_solve_rate,
        "hard_average_score": hard_summary.average_score,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
