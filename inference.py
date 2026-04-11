from __future__ import annotations

import argparse
import json
import os
import re

from env.baseline_runner import run_requested_baseline
from env.environment import SREIncidentEnv
from env.models import Action, TaskTier

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-oss-20b")
HF_TOKEN = os.getenv("HF_TOKEN")
API_KEY = os.getenv("API_KEY") or HF_TOKEN
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")


def _default_provider() -> str:
    if API_KEY and MODEL_NAME:
        return "hackathon"
    if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_BASELINE_MODEL"):
        return "openai"
    if os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_BASELINE_MODEL"):
        return "gemini"
    return "scripted"


def _configure_hackathon_provider(provider: str | None, model: str | None) -> tuple[str | None, str | None]:
    selected_provider = (provider or "").strip().lower() or None
    selected_model = model or MODEL_NAME

    hackathon_api_key = API_KEY
    hackathon_model = selected_model
    hackathon_base_url = API_BASE_URL

    if selected_provider in {None, "hackathon"} and hackathon_api_key and hackathon_model:
        os.environ["HACKATHON_API_KEY"] = hackathon_api_key
        os.environ["HACKATHON_BASELINE_MODEL"] = hackathon_model
        if hackathon_base_url:
            os.environ["HACKATHON_BASE_URL"] = hackathon_base_url
        return "hackathon", hackathon_model

    return selected_provider, selected_model


def run_inference(provider: str | None, model: str | None, seed: int, run_all: bool) -> dict:
    configured_provider, configured_model = _configure_hackathon_provider(provider, model)
    selected_provider = (configured_provider or _default_provider()).strip().lower()

    if run_all:
        results: dict[str, dict] = {}
        for tier in TaskTier:
            result = run_requested_baseline(
                tier=tier,
                provider=selected_provider,
                model=configured_model,
                seed=seed,
            ).model_dump(mode="json")
            results[tier.value] = result
        return {
            "provider": selected_provider,
            "model": configured_model,
            "seed": seed,
            "results": results,
        }

    result = run_requested_baseline(
        tier=TaskTier.EASY,
        provider=selected_provider,
        model=configured_model,
        seed=seed,
    ).model_dump(mode="json")
    return {
        "provider": selected_provider,
        "model": configured_model,
        "seed": seed,
        "result": result,
    }


def _normalize_field_value(value: object) -> str:
    if value is None:
        return "none"
    text = str(value).strip()
    if not text:
        return "none"
    text = re.sub(r"\s+", "_", text)
    return text


def _resolve_env_name() -> str:
    return os.getenv("OPENENV_ENV_NAME") or os.getenv("ENV_NAME") or "sre-incident-env"


def _replay_actions(result: dict) -> list[tuple[dict, float, bool]]:
    env = SREIncidentEnv(tier=TaskTier(result["tier"]), task_id=result["task_id"], seed=int(result["seed"]))
    replay_rows: list[tuple[dict, float, bool]] = []
    for action_payload in result.get("actions", []) or []:
        action = Action.model_validate(action_payload)
        observation, reward = env.step(action)
        replay_rows.append((action_payload, float(reward.total), bool(observation.episode_done)))
    return replay_rows


def _emit_structured_result(task_name: str, result: dict, provider: str, seed: int, model: str | None) -> None:
    start_fields = [
        f"task={_normalize_field_value(task_name)}",
        f"env={_normalize_field_value(_resolve_env_name())}",
        f"model={_normalize_field_value(model or provider)}",
    ]
    print(f"[START] {' '.join(start_fields)}", flush=True)

    replay_rows = _replay_actions(result)
    reward_history: list[float] = []
    if replay_rows:
        for index, (action, reward, done) in enumerate(replay_rows, start=1):
            reward_history.append(reward)
            action_text = json.dumps(action, separators=(",", ":"), sort_keys=True)
            step_fields = [
                f"step={index}",
                f"action={_normalize_field_value(action_text)}",
                f"reward={reward:.2f}",
                f"done={str(done).lower()}",
                "error=null",
            ]
            print(f"[STEP] {' '.join(step_fields)}", flush=True)
    else:
        reward_history.append(float(result["score"]))
        print("[STEP] step=0 action=no_action reward=0.00 done=true error=null", flush=True)

    end_fields = [
        f"success={str(bool(result['solved'])).lower()}",
        f"steps={int(result['steps_taken'])}",
        f"score={float(result['score']):.4f}",
        f"rewards={_normalize_field_value(','.join(f'{reward:.2f}' for reward in reward_history))}",
    ]
    if result.get("error"):
        end_fields.append(f"error={_normalize_field_value(result['error'])}")
    print(f"[END] {' '.join(end_fields)}", flush=True)


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
            for tier, result in payload["results"].items():
                _emit_structured_result(
                    task_name=tier,
                    result=result,
                    provider=payload["provider"],
                    seed=payload["seed"],
                    model=payload["model"],
                )
        else:
            _emit_structured_result(
                task_name=payload["result"]["task_id"],
                result=payload["result"],
                provider=payload["provider"],
                seed=payload["seed"],
                model=payload["model"],
            )


if __name__ == "__main__":
    main()
