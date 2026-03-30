from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field

from env.environment import SREIncidentEnv
from env.incidents import get_scenario, list_scenarios, materialize_seeded_scenario, public_task_id_for, public_template_id_for
from env.models import Action, TaskTier


LEGACY_OPENROUTER_MODEL = "stepfun/step-3.5-flash:free"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-20b:free"


def _normalize_openrouter_model(model: str | None) -> str:
    if not model or model == LEGACY_OPENROUTER_MODEL:
        return DEFAULT_OPENROUTER_MODEL
    return model


def _provider_env_prefix(provider_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", provider_name.strip().upper()).strip("_")


class BaselineResponse(BaseModel):
    tier: TaskTier
    task_id: str
    score: float
    solved: bool
    steps_taken: int
    seed: int = 0
    mode: str
    model: str | None = None
    error: str | None = None
    analytics: dict[str, float] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    grading_notes: list[str] = Field(default_factory=list)


class BenchmarkScenarioResult(BaseModel):
    task_id: str
    tier: TaskTier
    template_id: str | None = None
    seed: int = 0
    visibility: str = "public"
    score: float
    solved: bool
    steps_taken: int
    analytics: dict[str, float] = Field(default_factory=dict)
    grading_notes: list[str] = Field(default_factory=list)


class BenchmarkTierSummary(BaseModel):
    tier: TaskTier
    average_score: float
    solve_rate: float
    average_steps: float


class BenchmarkReport(BaseModel):
    generated_at: str
    mode: str
    model: str | None = None
    scenario_count: int
    template_count: int
    public_scenario_count: int
    holdout_scenario_count: int
    overall_average_score: float
    overall_solve_rate: float
    analytics_summary: dict[str, float]
    tier_summaries: list[BenchmarkTierSummary]
    family_breakdown: dict[str, int]
    hardest_scenarios: list[BenchmarkScenarioResult]
    scenario_results: list[BenchmarkScenarioResult]


def _error_baseline_response(
    *,
    scenario,
    env: SREIncidentEnv,
    seed: int,
    mode: str,
    model: str | None,
    error: str,
    actions_taken: list[dict[str, Any]] | None = None,
) -> BaselineResponse:
    result = env.result()
    return BaselineResponse(
        tier=scenario.tier,
        task_id=public_task_id_for(scenario.scenario_id),
        score=result.final_score,
        solved=result.solved,
        steps_taken=result.steps_taken,
        seed=seed,
        mode=mode,
        model=model,
        error=error,
        analytics=result.analytics,
        actions=actions_taken or [],
        grading_notes=result.grading_notes,
    )


def _friendly_provider_error(provider: str, exc: Exception) -> str:
    raw = str(exc)
    retry_match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", raw, flags=re.IGNORECASE)
    retry_delay = f" Retry after ~{round(float(retry_match.group(1)))}s." if retry_match else ""
    lowered = raw.lower()
    if "resource_exhausted" in lowered or "quota exceeded" in lowered or "rate limit" in lowered or "429" in lowered:
        return f"{provider} quota or rate limit exhausted.{retry_delay}".strip()
    if "api key" in lowered or "authentication" in lowered or "unauthorized" in lowered:
        return f"{provider} authentication failed. Check the configured API key."
    if "parse" in lowered or "json" in lowered:
        return f"{provider} returned an invalid action payload."
    compact = " ".join(raw.split())
    if len(compact) > 220:
        compact = compact[:217] + "..."
    return f"{provider} request failed: {compact}"


def _next_action_system_prompt() -> str:
    return (
        "You are an on-call SRE. Return exactly one JSON object representing the next action to take. "
        "Valid action_type values are: read_logs, check_metrics, ping_service, inspect_deploy, "
        "query_traces, check_runbook, diff_config, drain_traffic, failover_region, restart_service, "
        "rollback_deploy, scale_up, check_dependencies, submit_diagnosis. "
        "Services must be one of: api-gateway, auth-service, user-service, payment-service, db-postgres, cache-redis. "
        "Required fields by action: read_logs/check_metrics/ping_service/inspect_deploy/query_traces/check_runbook/"
        "diff_config/drain_traffic/failover_region/restart_service/check_dependencies require service; "
        "rollback_deploy requires service and target_version; scale_up requires service and replicas; "
        "submit_diagnosis requires root_cause_service, root_cause_category, and fix_description. "
        "Only include fields needed for the chosen action. "
        "Investigate before remediation: in medium/hard incidents, use check_dependencies and at least one direct check "
        "(ping_service/check_metrics/read_logs) on the suspected root service before applying a fix. "
        "Avoid fixing red herrings. Use submit_diagnosis only after confirming recovery."
    )


def _extract_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_action_response(raw_text: str) -> Action:
    parsed = json.loads(_extract_json_text(raw_text))
    return Action.model_validate(parsed)


def _validate_action_requirements(action: Action) -> str | None:
    service_required = {
        "read_logs",
        "check_metrics",
        "ping_service",
        "inspect_deploy",
        "query_traces",
        "check_runbook",
        "diff_config",
        "drain_traffic",
        "failover_region",
        "restart_service",
        "check_dependencies",
    }
    if action.action_type.value in service_required and not action.service:
        return f"{action.action_type.value} requires a non-empty service field."
    if action.action_type.value == "rollback_deploy":
        if not action.service:
            return "rollback_deploy requires a non-empty service field."
        if not action.target_version:
            return "rollback_deploy requires target_version."
    if action.action_type.value == "scale_up":
        if not action.service:
            return "scale_up requires a non-empty service field."
        if action.replicas is None:
            return "scale_up requires replicas."
    if action.action_type.value == "submit_diagnosis":
        if not action.root_cause_service:
            return "submit_diagnosis requires root_cause_service."
        if action.root_cause_category is None:
            return "submit_diagnosis requires root_cause_category."
        if not action.fix_description:
            return "submit_diagnosis requires fix_description."
    return None


def _model_user_prompt(tier: TaskTier, observation, correction: str | None = None) -> str:
    tier_hint = (
        "For medium and hard tiers, prioritize dependency mapping and avoid early restart/rollback on the first degraded service. "
        "Validate recovery with an explicit follow-up check before submit_diagnosis."
        if tier in {TaskTier.MEDIUM, TaskTier.HARD}
        else "Investigate first and avoid repeated actions."
    )
    payload: dict[str, Any] = {
        "tier": tier.value,
        "observation": observation.model_dump(mode="json"),
        "instruction": "Decide the single best next action. Return only valid JSON.",
        "tier_hint": tier_hint,
    }
    if correction:
        payload["correction"] = correction
    return json.dumps(payload)


def _scripted_actions_for(task_id: str, tier: TaskTier) -> list[Action]:
    task_actions = {
        "easy-auth-oom": [
            Action(action_type="ping_service", service="auth-service"),
            Action(action_type="check_metrics", service="auth-service"),
            Action(action_type="read_logs", service="auth-service", lines=3),
            Action(action_type="restart_service", service="auth-service"),
            Action(action_type="ping_service", service="auth-service"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="auth-service",
                root_cause_category="oom_crash",
                fix_description="Restarted the crashed auth-service after confirming an OOM event.",
            ),
        ],
        "easy-cache-memory-pressure": [
            Action(action_type="check_metrics", service="auth-service"),
            Action(action_type="check_dependencies", service="auth-service"),
            Action(action_type="ping_service", service="cache-redis"),
            Action(action_type="check_metrics", service="cache-redis"),
            Action(action_type="scale_up", service="cache-redis", replicas=4),
            Action(action_type="check_metrics", service="cache-redis"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="cache-redis",
                root_cause_category="memory_leak",
                fix_description="Scaled the overloaded cache tier after tracing auth degradation back to Redis memory pressure.",
            ),
        ],
        "easy-user-bad-deploy": [
            Action(action_type="ping_service", service="user-service"),
            Action(action_type="read_logs", service="user-service", lines=3),
            Action(action_type="check_metrics", service="user-service"),
            Action(action_type="rollback_deploy", service="user-service", target_version="v4.0.2"),
            Action(action_type="ping_service", service="user-service"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="user-service",
                root_cause_category="bad_deploy",
                fix_description="Rolled back the broken user-service release after startup failures.",
            ),
        ],
        "easy-gateway-config-flags": [
            Action(action_type="ping_service", service="api-gateway"),
            Action(action_type="read_logs", service="api-gateway", lines=3),
            Action(action_type="check_metrics", service="api-gateway"),
            Action(action_type="rollback_deploy", service="api-gateway", target_version="v3.2.1"),
            Action(action_type="ping_service", service="api-gateway"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="api-gateway",
                root_cause_category="config_error",
                fix_description="Rolled back the bad gateway config bundle after confirming edge-side rejection.",
            ),
        ],
        "easy-payment-oom-loop": [
            Action(action_type="ping_service", service="payment-service"),
            Action(action_type="check_metrics", service="payment-service"),
            Action(action_type="read_logs", service="payment-service", lines=3),
            Action(action_type="restart_service", service="payment-service"),
            Action(action_type="ping_service", service="payment-service"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="payment-service",
                root_cause_category="oom_crash",
                fix_description="Restarted the crash-looping payment workers after confirming an OOM-style failure.",
            ),
        ],
        "medium-db-cascade": [
            Action(action_type="check_metrics", service="user-service"),
            Action(action_type="check_dependencies", service="user-service"),
            Action(action_type="ping_service", service="db-postgres"),
            Action(action_type="check_metrics", service="db-postgres"),
            Action(action_type="restart_service", service="db-postgres"),
            Action(action_type="check_metrics", service="db-postgres"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="db-postgres",
                root_cause_category="dependency_fail",
                fix_description="Restarted the database after tracing downstream errors to the failed dependency.",
            ),
        ],
        "medium-payment-config": [
            Action(action_type="check_metrics", service="api-gateway"),
            Action(action_type="read_logs", service="payment-service", lines=3),
            Action(action_type="check_metrics", service="payment-service"),
            Action(action_type="rollback_deploy", service="payment-service", target_version="v5.4.1"),
            Action(action_type="ping_service", service="payment-service"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="payment-service",
                root_cause_category="config_error",
                fix_description="Rolled back the payment-service config release after bootstrap errors.",
            ),
        ],
        "medium-auth-cache-chain": [
            Action(action_type="check_metrics", service="auth-service"),
            Action(action_type="check_dependencies", service="auth-service"),
            Action(action_type="ping_service", service="cache-redis"),
            Action(action_type="check_metrics", service="cache-redis"),
            Action(action_type="restart_service", service="cache-redis"),
            Action(action_type="ping_service", service="cache-redis"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="cache-redis",
                root_cause_category="dependency_fail",
                fix_description="Restarted Redis after tracing auth failures to its dependency outage.",
            ),
        ],
        "medium-user-db-deadlock": [
            Action(action_type="check_metrics", service="user-service"),
            Action(action_type="check_dependencies", service="user-service"),
            Action(action_type="ping_service", service="db-postgres"),
            Action(action_type="read_logs", service="db-postgres", lines=3),
            Action(action_type="restart_service", service="db-postgres"),
            Action(action_type="ping_service", service="db-postgres"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="db-postgres",
                root_cause_category="db_deadlock",
                fix_description="Restarted Postgres after tracing user write stalls to blocked transactions.",
            ),
        ],
        "medium-cache-bad-deploy": [
            Action(action_type="check_metrics", service="auth-service"),
            Action(action_type="check_dependencies", service="auth-service"),
            Action(action_type="read_logs", service="cache-redis", lines=3),
            Action(action_type="check_metrics", service="cache-redis"),
            Action(action_type="rollback_deploy", service="cache-redis", target_version="v7.2.4"),
            Action(action_type="ping_service", service="cache-redis"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="cache-redis",
                root_cause_category="bad_deploy",
                fix_description="Rolled back the unstable Redis shard rollout after tracing auth and user latency to cache failures.",
            ),
        ],
        "hard-payment-red-herrings": [
            Action(action_type="check_metrics", service="api-gateway"),
            Action(action_type="read_logs", service="payment-service", lines=3),
            Action(action_type="check_metrics", service="payment-service"),
            Action(action_type="rollback_deploy", service="payment-service", target_version="v5.4.1"),
            Action(action_type="check_metrics", service="payment-service"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="payment-service",
                root_cause_category="bad_deploy",
                fix_description="Rolled back the failing payment-service deploy after confirming startup errors.",
            ),
        ],
        "hard-db-deadlock-noise": [
            Action(action_type="check_metrics", service="payment-service"),
            Action(action_type="check_dependencies", service="payment-service"),
            Action(action_type="ping_service", service="db-postgres"),
            Action(action_type="read_logs", service="db-postgres", lines=3),
            Action(action_type="check_metrics", service="db-postgres"),
            Action(action_type="restart_service", service="db-postgres"),
            Action(action_type="ping_service", service="db-postgres"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="db-postgres",
                root_cause_category="db_deadlock",
                fix_description="Restarted the deadlocked database after tracing stalled downstream services back to blocked transactions.",
            ),
        ],
        "hard-auth-memleak-rollup": [
            Action(action_type="check_metrics", service="api-gateway"),
            Action(action_type="check_metrics", service="auth-service"),
            Action(action_type="read_logs", service="auth-service", lines=3),
            Action(action_type="scale_up", service="auth-service", replicas=5),
            Action(action_type="check_metrics", service="auth-service"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="auth-service",
                root_cause_category="memory_leak",
                fix_description="Scaled auth-service after isolating a memory leak under production traffic.",
            ),
        ],
        "hard-gateway-config-canary": [
            Action(action_type="check_metrics", service="user-service"),
            Action(action_type="read_logs", service="api-gateway", lines=3),
            Action(action_type="check_metrics", service="api-gateway"),
            Action(action_type="rollback_deploy", service="api-gateway", target_version="v3.2.1"),
            Action(action_type="ping_service", service="api-gateway"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="api-gateway",
                root_cause_category="config_error",
                fix_description="Rolled back the broken gateway canary after confirming edge-only rejection before upstream fan-out.",
            ),
        ],
        "hard-user-db-rollup": [
            Action(action_type="check_metrics", service="payment-service"),
            Action(action_type="check_dependencies", service="payment-service"),
            Action(action_type="ping_service", service="db-postgres"),
            Action(action_type="read_logs", service="db-postgres", lines=3),
            Action(action_type="restart_service", service="db-postgres"),
            Action(action_type="ping_service", service="db-postgres"),
            Action(
                action_type="submit_diagnosis",
                root_cause_service="db-postgres",
                root_cause_category="db_deadlock",
                fix_description="Restarted the blocked database after separating its primary deadlock from the noisy user-service deploy issue.",
            ),
        ],
    }
    default_by_tier = {
        TaskTier.EASY: "easy-auth-oom",
        TaskTier.MEDIUM: "medium-db-cascade",
        TaskTier.HARD: "hard-payment-red-herrings",
    }
    return task_actions.get(task_id, task_actions[default_by_tier[tier]])


def scripted_baseline(tier: TaskTier, task_id: str | None = None) -> BaselineResponse:
    return scripted_baseline_for_seed(tier=tier, task_id=task_id, seed=0)


def scripted_baseline_for_seed(tier: TaskTier, task_id: str | None = None, seed: int = 0) -> BaselineResponse:
    scenario = materialize_seeded_scenario(get_scenario(tier=tier, task_id=task_id), seed)
    env = SREIncidentEnv(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    actions = _scripted_actions_for(scenario.scenario_id, scenario.tier)
    for action in actions:
        env.step(action)
    result = env.result()
    return BaselineResponse(
        tier=scenario.tier,
        task_id=public_task_id_for(scenario.scenario_id),
        score=result.final_score,
        solved=result.solved,
        steps_taken=result.steps_taken,
        seed=seed,
        mode="scripted",
        analytics=result.analytics,
        actions=[action.model_dump(mode="json") for action in actions],
        grading_notes=result.grading_notes,
    )


def openai_baseline(
    tier: TaskTier,
    task_id: str | None = None,
    model: str | None = None,
    seed: int = 0,
    step_logger: Callable[[str], None] | None = None,
) -> BaselineResponse:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    selected_model = model or os.getenv("OPENAI_BASELINE_MODEL")
    if not selected_model:
        raise RuntimeError("OPENAI_BASELINE_MODEL is not set.")
    client = OpenAI(api_key=api_key)
    scenario = materialize_seeded_scenario(get_scenario(tier=tier, task_id=task_id), seed)
    env = SREIncidentEnv(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    observation = env.reset(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    actions_taken: list[dict[str, Any]] = []

    system_prompt = _next_action_system_prompt()

    for _ in range(env._require_episode().scenario.max_steps):
        action: Action | None = None
        correction: str | None = None
        for _attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": _model_user_prompt(tier, observation, correction=correction)},
                    ],
                    response_format={"type": "json_object"},
                )
            except Exception as exc:
                return _error_baseline_response(
                    scenario=scenario,
                    env=env,
                    seed=seed,
                    mode="openai",
                    model=selected_model,
                    error=_friendly_provider_error("OpenAI", exc),
                    actions_taken=actions_taken,
                )
            raw_action = ((response.choices[0].message.content if response.choices else "") or "").strip()
            try:
                parsed_action = _parse_action_response(raw_action)
            except Exception as exc:
                correction = f"Previous response could not be parsed as a valid action JSON object: {exc}."
                continue
            validation_error = _validate_action_requirements(parsed_action)
            if validation_error:
                correction = (
                    f"Previous response was invalid: {validation_error} "
                    "Return a corrected action JSON object with all required fields."
                )
                continue
            action = parsed_action
            break
        if action is None:
            return _error_baseline_response(
                scenario=scenario,
                env=env,
                seed=seed,
                mode="openai",
                model=selected_model,
                error="OpenAI returned repeated invalid actions that were missing required fields.",
                actions_taken=actions_taken,
            )

        actions_taken.append(action.model_dump(mode="json"))
        observation, _reward = env.step(action)
        if step_logger is not None:
            step_logger(
                f"step={observation.step_number} action={action.action_type}"
                + (f" service={action.service}" if action.service else "")
                + (f" target_version={action.target_version}" if action.target_version else "")
                + (f" replicas={action.replicas}" if action.replicas is not None else "")
                + (
                    f" diagnosis={action.root_cause_service}/{action.root_cause_category}"
                    if action.root_cause_service and action.root_cause_category
                    else ""
                )
                + f" reward={_reward.total:+.2f} done={observation.episode_done}"
            )
            if observation.action_result:
                step_logger(f"  result: {observation.action_result}")
        if observation.episode_done:
            break

    result = env.result()
    return BaselineResponse(
        tier=scenario.tier,
        task_id=public_task_id_for(scenario.scenario_id),
        score=result.final_score,
        solved=result.solved,
        steps_taken=result.steps_taken,
        seed=seed,
        mode="openai",
        model=selected_model,
        analytics=result.analytics,
        actions=actions_taken,
        grading_notes=result.grading_notes,
    )


def gemini_baseline(
    tier: TaskTier,
    task_id: str | None = None,
    model: str | None = None,
    seed: int = 0,
    step_logger: Callable[[str], None] | None = None,
) -> BaselineResponse:
    from openai import OpenAI

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    selected_model = model or os.getenv("GEMINI_BASELINE_MODEL")
    if not selected_model:
        raise RuntimeError("GEMINI_BASELINE_MODEL is not set.")
    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
    )
    scenario = materialize_seeded_scenario(get_scenario(tier=tier, task_id=task_id), seed)
    env = SREIncidentEnv(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    observation = env.reset(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    actions_taken: list[dict[str, Any]] = []

    for _ in range(env._require_episode().scenario.max_steps):
        action: Action | None = None
        correction: str | None = None
        for _attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": _next_action_system_prompt()},
                        {"role": "user", "content": _model_user_prompt(tier, observation, correction=correction)},
                    ],
                )
            except Exception as exc:
                return _error_baseline_response(
                    scenario=scenario,
                    env=env,
                    seed=seed,
                    mode="gemini",
                    model=selected_model,
                    error=_friendly_provider_error("Gemini", exc),
                    actions_taken=actions_taken,
                )
            raw_action = ((response.choices[0].message.content if response.choices else "") or "").strip()
            try:
                parsed_action = _parse_action_response(raw_action)
            except Exception as exc:
                correction = f"Previous response could not be parsed as a valid action JSON object: {exc}."
                continue
            validation_error = _validate_action_requirements(parsed_action)
            if validation_error:
                correction = (
                    f"Previous response was invalid: {validation_error} "
                    "Return a corrected action JSON object with all required fields."
                )
                continue
            action = parsed_action
            break
        if action is None:
            return _error_baseline_response(
                scenario=scenario,
                env=env,
                seed=seed,
                mode="gemini",
                model=selected_model,
                error="Gemini returned repeated invalid actions that were missing required fields.",
                actions_taken=actions_taken,
            )

        actions_taken.append(action.model_dump(mode="json"))
        observation, _reward = env.step(action)
        if step_logger is not None:
            step_logger(
                f"step={observation.step_number} action={action.action_type}"
                + (f" service={action.service}" if action.service else "")
                + (f" target_version={action.target_version}" if action.target_version else "")
                + (f" replicas={action.replicas}" if action.replicas is not None else "")
                + (
                    f" diagnosis={action.root_cause_service}/{action.root_cause_category}"
                    if action.root_cause_service and action.root_cause_category
                    else ""
                )
                + f" reward={_reward.total:+.2f} done={observation.episode_done}"
            )
            if observation.action_result:
                step_logger(f"  result: {observation.action_result}")
        if observation.episode_done:
            break

    result = env.result()
    return BaselineResponse(
        tier=scenario.tier,
        task_id=public_task_id_for(scenario.scenario_id),
        score=result.final_score,
        solved=result.solved,
        steps_taken=result.steps_taken,
        seed=seed,
        mode="gemini",
        model=selected_model,
        analytics=result.analytics,
        actions=actions_taken,
        grading_notes=result.grading_notes,
    )


def custom_openai_compatible_baseline(
    provider_name: str,
    tier: TaskTier,
    task_id: str | None = None,
    model: str | None = None,
    seed: int = 0,
    step_logger: Callable[[str], None] | None = None,
) -> BaselineResponse:
    from openai import OpenAI

    env_prefix = _provider_env_prefix(provider_name)
    api_key = os.getenv(f"{env_prefix}_API_KEY")
    if not api_key:
        raise RuntimeError(f"{env_prefix}_API_KEY is not set.")

    selected_model = model or os.getenv(f"{env_prefix}_BASELINE_MODEL")
    if not selected_model:
        raise RuntimeError(f"{env_prefix}_BASELINE_MODEL is not set.")

    base_url = os.getenv(f"{env_prefix}_BASE_URL")
    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    scenario = materialize_seeded_scenario(get_scenario(tier=tier, task_id=task_id), seed)
    env = SREIncidentEnv(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    observation = env.reset(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    actions_taken: list[dict[str, Any]] = []

    for _ in range(env._require_episode().scenario.max_steps):
        action: Action | None = None
        correction: str | None = None
        for _attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": _next_action_system_prompt()},
                        {"role": "user", "content": _model_user_prompt(tier, observation, correction=correction)},
                    ],
                )
            except Exception as exc:
                return _error_baseline_response(
                    scenario=scenario,
                    env=env,
                    seed=seed,
                    mode=provider_name,
                    model=selected_model,
                    error=_friendly_provider_error(provider_name, exc),
                    actions_taken=actions_taken,
                )
            raw_action = ((response.choices[0].message.content if response.choices else "") or "").strip()
            try:
                parsed_action = _parse_action_response(raw_action)
            except Exception as exc:
                correction = f"Previous response could not be parsed as a valid action JSON object: {exc}."
                continue
            validation_error = _validate_action_requirements(parsed_action)
            if validation_error:
                correction = (
                    f"Previous response was invalid: {validation_error} "
                    "Return a corrected action JSON object with all required fields."
                )
                continue
            action = parsed_action
            break
        if action is None:
            return _error_baseline_response(
                scenario=scenario,
                env=env,
                seed=seed,
                mode=provider_name,
                model=selected_model,
                error=f"{provider_name} returned repeated invalid actions that were missing required fields.",
                actions_taken=actions_taken,
            )

        actions_taken.append(action.model_dump(mode="json"))
        observation, _reward = env.step(action)
        if step_logger is not None:
            step_logger(
                f"step={observation.step_number} action={action.action_type}"
                + (f" service={action.service}" if action.service else "")
                + (f" target_version={action.target_version}" if action.target_version else "")
                + (f" replicas={action.replicas}" if action.replicas is not None else "")
                + (
                    f" diagnosis={action.root_cause_service}/{action.root_cause_category}"
                    if action.root_cause_service and action.root_cause_category
                    else ""
                )
                + f" reward={_reward.total:+.2f} done={observation.episode_done}"
            )
            if observation.action_result:
                step_logger(f"  result: {observation.action_result}")
        if observation.episode_done:
            break

    result = env.result()
    return BaselineResponse(
        tier=scenario.tier,
        task_id=public_task_id_for(scenario.scenario_id),
        score=result.final_score,
        solved=result.solved,
        steps_taken=result.steps_taken,
        seed=seed,
        mode=provider_name,
        model=selected_model,
        analytics=result.analytics,
        actions=actions_taken,
        grading_notes=result.grading_notes,
    )


def openrouter_baseline(
    tier: TaskTier,
    task_id: str | None = None,
    model: str | None = None,
    seed: int = 0,
    step_logger: Callable[[str], None] | None = None,
) -> BaselineResponse:
    from openai import OpenAI

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")

    selected_model = _normalize_openrouter_model(model or os.getenv("OPENROUTER_BASELINE_MODEL", DEFAULT_OPENROUTER_MODEL))
    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )
    scenario = materialize_seeded_scenario(get_scenario(tier=tier, task_id=task_id), seed)
    env = SREIncidentEnv(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    observation = env.reset(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    actions_taken: list[dict[str, Any]] = []

    for _ in range(env._require_episode().scenario.max_steps):
        action: Action | None = None
        correction: str | None = None
        for _attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": _next_action_system_prompt()},
                        {"role": "user", "content": _model_user_prompt(tier, observation, correction=correction)},
                    ],
                    response_format={"type": "json_object"},
                    extra_headers={
                        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:8000"),
                        "X-Title": os.getenv("OPENROUTER_APP_TITLE", "SRE Incident Environment"),
                    },
                )
            except Exception as exc:
                return _error_baseline_response(
                    scenario=scenario,
                    env=env,
                    seed=seed,
                    mode="openrouter",
                    model=selected_model,
                    error=_friendly_provider_error("OpenRouter", exc),
                    actions_taken=actions_taken,
                )
            raw_action = ((response.choices[0].message.content if response.choices else "") or "").strip()
            try:
                parsed_action = _parse_action_response(raw_action)
            except Exception as exc:
                correction = f"Previous response could not be parsed as a valid action JSON object: {exc}."
                continue
            validation_error = _validate_action_requirements(parsed_action)
            if validation_error:
                correction = (
                    f"Previous response was invalid: {validation_error} "
                    "Return a corrected action JSON object with all required fields."
                )
                continue
            action = parsed_action
            break
        if action is None:
            return _error_baseline_response(
                scenario=scenario,
                env=env,
                seed=seed,
                mode="openrouter",
                model=selected_model,
                error="OpenRouter returned repeated invalid actions that were missing required fields.",
                actions_taken=actions_taken,
            )

        actions_taken.append(action.model_dump(mode="json"))
        observation, _reward = env.step(action)
        if step_logger is not None:
            step_logger(
                f"step={observation.step_number} action={action.action_type}"
                + (f" service={action.service}" if action.service else "")
                + (f" target_version={action.target_version}" if action.target_version else "")
                + (f" replicas={action.replicas}" if action.replicas is not None else "")
                + (
                    f" diagnosis={action.root_cause_service}/{action.root_cause_category}"
                    if action.root_cause_service and action.root_cause_category
                    else ""
                )
                + f" reward={_reward.total:+.2f} done={observation.episode_done}"
            )
            if observation.action_result:
                step_logger(f"  result: {observation.action_result}")
        if observation.episode_done:
            break

    result = env.result()
    return BaselineResponse(
        tier=scenario.tier,
        task_id=public_task_id_for(scenario.scenario_id),
        score=result.final_score,
        solved=result.solved,
        steps_taken=result.steps_taken,
        seed=seed,
        mode="openrouter",
        model=selected_model,
        analytics=result.analytics,
        actions=actions_taken,
        grading_notes=result.grading_notes,
    )


def groq_baseline(
    tier: TaskTier,
    task_id: str | None = None,
    model: str | None = None,
    seed: int = 0,
    step_logger: Callable[[str], None] | None = None,
) -> BaselineResponse:
    from openai import OpenAI

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")

    selected_model = model or os.getenv("GROQ_BASELINE_MODEL", "llama-3.3-70b-versatile")
    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
    )
    scenario = materialize_seeded_scenario(get_scenario(tier=tier, task_id=task_id), seed)
    env = SREIncidentEnv(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    observation = env.reset(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    actions_taken: list[dict[str, Any]] = []

    for _ in range(env._require_episode().scenario.max_steps):
        action: Action | None = None
        correction: str | None = None
        for _attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": _next_action_system_prompt()},
                        {"role": "user", "content": _model_user_prompt(tier, observation, correction=correction)},
                    ],
                    response_format={"type": "json_object"},
                )
            except Exception as exc:
                return _error_baseline_response(
                    scenario=scenario,
                    env=env,
                    seed=seed,
                    mode="groq",
                    model=selected_model,
                    error=_friendly_provider_error("Groq", exc),
                    actions_taken=actions_taken,
                )
            raw_action = ((response.choices[0].message.content if response.choices else "") or "").strip()
            try:
                parsed_action = _parse_action_response(raw_action)
            except Exception as exc:
                correction = f"Previous response could not be parsed as a valid action JSON object: {exc}."
                continue
            validation_error = _validate_action_requirements(parsed_action)
            if validation_error:
                correction = (
                    f"Previous response was invalid: {validation_error} "
                    "Return a corrected action JSON object with all required fields."
                )
                continue
            action = parsed_action
            break
        if action is None:
            return _error_baseline_response(
                scenario=scenario,
                env=env,
                seed=seed,
                mode="groq",
                model=selected_model,
                error="Groq returned repeated invalid actions that were missing required fields.",
                actions_taken=actions_taken,
            )

        actions_taken.append(action.model_dump(mode="json"))
        observation, _reward = env.step(action)
        if step_logger is not None:
            step_logger(
                f"step={observation.step_number} action={action.action_type}"
                + (f" service={action.service}" if action.service else "")
                + (f" target_version={action.target_version}" if action.target_version else "")
                + (f" replicas={action.replicas}" if action.replicas is not None else "")
                + (
                    f" diagnosis={action.root_cause_service}/{action.root_cause_category}"
                    if action.root_cause_service and action.root_cause_category
                    else ""
                )
                + f" reward={_reward.total:+.2f} done={observation.episode_done}"
            )
            if observation.action_result:
                step_logger(f"  result: {observation.action_result}")
        if observation.episode_done:
            break

    result = env.result()
    return BaselineResponse(
        tier=scenario.tier,
        task_id=public_task_id_for(scenario.scenario_id),
        score=result.final_score,
        solved=result.solved,
        steps_taken=result.steps_taken,
        seed=seed,
        mode="groq",
        model=selected_model,
        analytics=result.analytics,
        actions=actions_taken,
        grading_notes=result.grading_notes,
    )


def cerebras_baseline(
    tier: TaskTier,
    task_id: str | None = None,
    model: str | None = None,
    seed: int = 0,
    step_logger: Callable[[str], None] | None = None,
) -> BaselineResponse:
    from cerebras.cloud.sdk import Cerebras

    api_key = os.getenv("CEREBRAS_API_KEY")
    if not api_key:
        raise RuntimeError("CEREBRAS_API_KEY is not set.")

    selected_model = model or os.getenv("CEREBRAS_BASELINE_MODEL", "llama3.1-8b")
    client = Cerebras(api_key=api_key)
    scenario = materialize_seeded_scenario(get_scenario(tier=tier, task_id=task_id), seed)
    env = SREIncidentEnv(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    observation = env.reset(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
    actions_taken: list[dict[str, Any]] = []

    for _ in range(env._require_episode().scenario.max_steps):
        action: Action | None = None
        correction: str | None = None
        for _attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": _next_action_system_prompt()},
                        {"role": "user", "content": _model_user_prompt(tier, observation, correction=correction)},
                    ],
                    stream=False,
                    temperature=0.2,
                    top_p=1,
                    max_completion_tokens=int(os.getenv("CEREBRAS_MAX_COMPLETION_TOKENS", "1024")),
                )
            except Exception as exc:
                return _error_baseline_response(
                    scenario=scenario,
                    env=env,
                    seed=seed,
                    mode="cerebras",
                    model=selected_model,
                    error=_friendly_provider_error("Cerebras", exc),
                    actions_taken=actions_taken,
                )

            raw_action = ((response.choices[0].message.content if response.choices else "") or "").strip()
            try:
                parsed_action = _parse_action_response(raw_action)
            except Exception as exc:
                correction = f"Previous response could not be parsed as a valid action JSON object: {exc}."
                continue
            validation_error = _validate_action_requirements(parsed_action)
            if validation_error:
                correction = (
                    f"Previous response was invalid: {validation_error} "
                    "Return a corrected action JSON object with all required fields."
                )
                continue
            action = parsed_action
            break
        if action is None:
            return _error_baseline_response(
                scenario=scenario,
                env=env,
                seed=seed,
                mode="cerebras",
                model=selected_model,
                error="Cerebras returned repeated invalid actions that were missing required fields.",
                actions_taken=actions_taken,
            )

        actions_taken.append(action.model_dump(mode="json"))
        observation, _reward = env.step(action)
        if step_logger is not None:
            step_logger(
                f"step={observation.step_number} action={action.action_type}"
                + (f" service={action.service}" if action.service else "")
                + (f" target_version={action.target_version}" if action.target_version else "")
                + (f" replicas={action.replicas}" if action.replicas is not None else "")
                + (
                    f" diagnosis={action.root_cause_service}/{action.root_cause_category}"
                    if action.root_cause_service and action.root_cause_category
                    else ""
                )
                + f" reward={_reward.total:+.2f} done={observation.episode_done}"
            )
            if observation.action_result:
                step_logger(f"  result: {observation.action_result}")
        if observation.episode_done:
            break

    result = env.result()
    return BaselineResponse(
        tier=scenario.tier,
        task_id=public_task_id_for(scenario.scenario_id),
        score=result.final_score,
        solved=result.solved,
        steps_taken=result.steps_taken,
        seed=seed,
        mode="cerebras",
        model=selected_model,
        analytics=result.analytics,
        actions=actions_taken,
        grading_notes=result.grading_notes,
    )


def run_requested_baseline(
    tier: TaskTier,
    task_id: str | None = None,
    use_openai: bool = False,
    provider: str | None = None,
    model: str | None = None,
    seed: int = 0,
    step_logger: Callable[[str], None] | None = None,
) -> BaselineResponse:
    selected_provider = (provider or ("openai" if use_openai else "scripted")).strip().lower()
    if selected_provider == "scripted":
        return scripted_baseline_for_seed(tier=tier, task_id=task_id, seed=seed)
    if selected_provider == "openai":
        try:
            return openai_baseline(tier=tier, task_id=task_id, model=model, seed=seed, step_logger=step_logger)
        except Exception as exc:
            scenario = materialize_seeded_scenario(get_scenario(tier=tier, task_id=task_id), seed)
            env = SREIncidentEnv(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
            return _error_baseline_response(
                scenario=scenario,
                env=env,
                seed=seed,
                mode="openai",
                model=model or os.getenv("OPENAI_BASELINE_MODEL"),
                error=_friendly_provider_error("OpenAI", exc),
            )
    if selected_provider == "gemini":
        try:
            return gemini_baseline(tier=tier, task_id=task_id, model=model, seed=seed, step_logger=step_logger)
        except Exception as exc:
            scenario = materialize_seeded_scenario(get_scenario(tier=tier, task_id=task_id), seed)
            env = SREIncidentEnv(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
            return _error_baseline_response(
                scenario=scenario,
                env=env,
                seed=seed,
                mode="gemini",
                model=model or os.getenv("GEMINI_BASELINE_MODEL"),
                error=_friendly_provider_error("Gemini", exc),
            )
    try:
        return custom_openai_compatible_baseline(
            provider_name=selected_provider,
            tier=tier,
            task_id=task_id,
            model=model,
            seed=seed,
            step_logger=step_logger,
        )
    except Exception as exc:
        scenario = materialize_seeded_scenario(get_scenario(tier=tier, task_id=task_id), seed)
        env = SREIncidentEnv(tier=scenario.tier, task_id=scenario.scenario_id, seed=seed)
        env_prefix = _provider_env_prefix(selected_provider)
        return _error_baseline_response(
            scenario=scenario,
            env=env,
            seed=seed,
            mode=selected_provider,
            model=model or os.getenv(f"{env_prefix}_BASELINE_MODEL"),
            error=_friendly_provider_error(selected_provider, exc),
        )


def run_benchmark(
    use_openai: bool = False,
    provider: str | None = None,
    model: str | None = None,
    seeds_per_scenario: int = 1,
) -> BenchmarkReport:
    if seeds_per_scenario < 1:
        raise ValueError("seeds_per_scenario must be >= 1")

    scenario_results: list[BenchmarkScenarioResult] = []
    scenarios = list_scenarios(include_hidden=True)
    selected_provider = provider or ("openai" if use_openai else "scripted")
    for scenario in scenarios:
        for seed in range(seeds_per_scenario):
            result = run_requested_baseline(
                tier=scenario.tier,
                task_id=scenario.scenario_id,
                use_openai=use_openai,
                provider=selected_provider,
                model=model,
                seed=seed,
            )
            scenario_results.append(
                BenchmarkScenarioResult(
                    task_id=f"{public_task_id_for(scenario.scenario_id)}#seed{seed}",
                    tier=scenario.tier,
                    template_id=public_template_id_for(scenario.template_id),
                    seed=seed,
                    visibility="public" if scenario.public else "holdout",
                    score=result.score,
                    solved=result.solved,
                    steps_taken=result.steps_taken,
                    analytics=result.analytics,
                    grading_notes=result.grading_notes,
                )
            )

    tier_summaries: list[BenchmarkTierSummary] = []
    for tier in TaskTier:
        tier_results = [item for item in scenario_results if item.tier == tier]
        if not tier_results:
            continue
        tier_summaries.append(
            BenchmarkTierSummary(
                tier=tier,
                average_score=sum(item.score for item in tier_results) / len(tier_results),
                solve_rate=sum(1 for item in tier_results if item.solved) / len(tier_results),
                average_steps=sum(item.steps_taken for item in tier_results) / len(tier_results),
            )
        )

    analytics_keys = ["mitigation_speed", "evidence_quality", "blast_radius_control", "recovery_certainty", "action_efficiency"]
    analytics_summary = {
        key: (
            sum(item.analytics.get(key, 0.0) for item in scenario_results) / len(scenario_results)
            if scenario_results else 0.0
        )
        for key in analytics_keys
    }

    return BenchmarkReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode=selected_provider,
        model=model,
        scenario_count=len(scenario_results),
        template_count=len({scenario.template_id for scenario in scenarios}),
        public_scenario_count=sum(1 for scenario in scenarios if scenario.public) * seeds_per_scenario,
        holdout_scenario_count=sum(1 for scenario in scenarios if not scenario.public) * seeds_per_scenario,
        overall_average_score=(
            sum(item.score for item in scenario_results) / len(scenario_results)
            if scenario_results else 0.0
        ),
        overall_solve_rate=(
            sum(1 for item in scenario_results if item.solved) / len(scenario_results)
            if scenario_results else 0.0
        ),
        analytics_summary=analytics_summary,
        tier_summaries=tier_summaries,
        family_breakdown={
            template_id: sum(1 for item in scenario_results if item.template_id == template_id)
            for template_id in sorted({item.template_id for item in scenario_results if item.template_id})
        },
        hardest_scenarios=sorted(scenario_results, key=lambda item: (item.score, item.steps_taken))[:5],
        scenario_results=scenario_results,
    )
