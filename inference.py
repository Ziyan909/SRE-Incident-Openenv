from __future__ import annotations

import argparse
import json
import os

from env.baseline_runner import run_requested_baseline
from env.models import TaskTier


def _default_provider() -> str:
    if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_BASELINE_MODEL"):
        return "openai"
    if os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_BASELINE_MODEL"):
        return "gemini"
    return "scripted"


def run_inference(provider: str | None, model: str | None, seed: int, run_all: bool) -> dict:
    selected_provider = (provider or _default_provider()).strip().lower()

    if run_all:
        results: dict[str, dict] = {}
        for tier in TaskTier:
            result = run_requested_baseline(
                tier=tier,
                provider=selected_provider,
                model=model,
                seed=seed,
            ).model_dump(mode="json")
            results[tier.value] = result
        return {
            "provider": selected_provider,
            "model": model,
            "seed": seed,
            "results": results,
        }

    result = run_requested_baseline(
        tier=TaskTier.EASY,
        provider=selected_provider,
        model=model,
        seed=seed,
    ).model_dump(mode="json")
    return {
        "provider": selected_provider,
        "model": model,
        "seed": seed,
        "result": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run non-interactive baseline inference for submission checks.")
    parser.add_argument("--provider", type=str, default=None, help="Provider to use (scripted, openai, gemini, or custom).")
    parser.add_argument("--model", type=str, default=None, help="Model name override.")
    parser.add_argument("--seed", type=int, default=0, help="Scenario seed.")
    parser.add_argument("--all", action="store_true", help="Run one baseline scenario per tier.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    payload = run_inference(
        provider=args.provider,
        model=args.model,
        seed=args.seed,
        run_all=args.all,
    )

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if args.all:
            print(f"provider={payload['provider']} seed={payload['seed']}")
            for tier, result in payload["results"].items():
                print(
                    f"{tier}: score={result['score']:.2f} solved={result['solved']} "
                    f"steps={result['steps_taken']} mode={result['mode']}"
                )
        else:
            result = payload["result"]
            print(
                f"provider={payload['provider']} score={result['score']:.2f} "
                f"solved={result['solved']} steps={result['steps_taken']} mode={result['mode']}"
            )


if __name__ == "__main__":
    main()
