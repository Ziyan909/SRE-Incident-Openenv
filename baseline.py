from __future__ import annotations

import argparse
import json
import os
import re
import sys

from env.baseline_runner import run_requested_baseline
from env.incidents import list_tasks
from env.models import TaskTier


CUSTOM_PROVIDER_NAMES: list[str] = []


def _is_interactive() -> bool:
    return sys.stdin.isatty()


def _normalize_provider_model(provider: str, model: str | None) -> str | None:
    # Keep model normalization hook for future provider-specific aliases.
    return model


def _provider_env_prefix(provider: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", provider.strip().lower()).strip("_")
    return normalized.upper()


def _provider_model_env_name(provider: str) -> str:
    if provider == "openai":
        return "OPENAI_BASELINE_MODEL"
    if provider == "gemini":
        return "GEMINI_BASELINE_MODEL"
    return f"{_provider_env_prefix(provider)}_BASELINE_MODEL"


def _provider_api_env_name(provider: str) -> str:
    if provider == "openai":
        return "OPENAI_API_KEY"
    if provider == "gemini":
        return "GEMINI_API_KEY"
    return f"{_provider_env_prefix(provider)}_API_KEY"


def _provider_base_url_env_name(provider: str) -> str:
    if provider == "gemini":
        return "GEMINI_BASE_URL"
    return f"{_provider_env_prefix(provider)}_BASE_URL"


def _register_custom_provider(provider: str, api_key: str, model_name: str, base_url: str | None) -> None:
    env_prefix = _provider_env_prefix(provider)
    os.environ[f"{env_prefix}_API_KEY"] = api_key
    os.environ[f"{env_prefix}_BASELINE_MODEL"] = model_name
    if base_url:
        os.environ[f"{env_prefix}_BASE_URL"] = base_url
    if provider not in CUSTOM_PROVIDER_NAMES:
        CUSTOM_PROVIDER_NAMES.append(provider)


def _parse_kv_tokens(message: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in message.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value
    return fields


def _truncate(text: str, limit: int = 96) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _format_step_log_line(message: str, tier: str) -> str:
    stripped = message.strip()
    if stripped.startswith("result:"):
        result_text = stripped.split(":", 1)[1].strip()
        return f"[{tier}]   outcome : {result_text}"

    if not stripped.startswith("step="):
        return f"[{tier}] {stripped}"

    fields = _parse_kv_tokens(stripped)
    step = fields.get("step", "?")
    try:
        step_display = f"{int(step):02d}"
    except ValueError:
        step_display = step

    action = fields.get("action", "unknown")
    reward = fields.get("reward", "+0.00")
    done_raw = fields.get("done", "False").lower()
    done_display = "yes" if done_raw in {"true", "1", "yes"} else "no"

    details: list[str] = []
    if fields.get("service"):
        details.append(f"service={fields['service']}")
    if fields.get("target_version"):
        details.append(f"target={fields['target_version']}")
    if fields.get("replicas"):
        details.append(f"replicas={fields['replicas']}")
    if fields.get("diagnosis"):
        details.append(f"diagnosis={fields['diagnosis']}")

    header = f"[{tier}] Step {step_display} | action={action} | reward={reward} | done={done_display}"
    if not details:
        return header
    detail_text = _truncate("; ".join(details))
    return f"{header}\n[{tier}]   details : {detail_text}"


def _resolve_provider_and_model() -> tuple[str, str | None, bool, bool]:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    openai_client_initialized = False
    gemini_client_initialized = False

    if openai_api_key:
        try:
            from openai import OpenAI

            OpenAI(api_key=openai_api_key)
            openai_client_initialized = True
        except ImportError:
            openai_client_initialized = False

    if gemini_api_key:
        try:
            from openai import OpenAI

            OpenAI(
                api_key=gemini_api_key,
                base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            )
            gemini_client_initialized = True
        except ImportError:
            gemini_client_initialized = False

    provider = os.getenv("BASELINE_PROVIDER")
    if not provider:
        if openai_client_initialized and os.getenv("OPENAI_USE_REAL_BASELINE", "0") == "1":
            provider = "openai"
        elif gemini_client_initialized and os.getenv("GEMINI_USE_REAL_BASELINE", "0") == "1":
            provider = "gemini"
        else:
            provider = "scripted"

    model = os.getenv("BASELINE_MODEL")
    if not model:
        if provider == "openai":
            model = os.getenv("OPENAI_BASELINE_MODEL")
        elif provider == "gemini":
            model = os.getenv("GEMINI_BASELINE_MODEL")
        elif provider and provider != "scripted":
            model = os.getenv(_provider_model_env_name(provider))

    model = _normalize_provider_model(provider, model)

    return (
        provider,
        model,
        openai_client_initialized,
        gemini_client_initialized,
    )


def _default_model_for_provider(provider: str) -> str | None:
    if provider == "scripted":
        return None
    return os.getenv(_provider_model_env_name(provider))


def _provider_options(default_provider: str | None = None) -> list[str]:
    options = ["scripted", "openai", "gemini"]
    for name in CUSTOM_PROVIDER_NAMES:
        if name not in options:
            options.append(name)
    if default_provider and default_provider not in options and default_provider != "scripted":
        options.append(default_provider)
    options.append("add_another_provider")
    return options


def _prompt_non_empty(prompt: str) -> str:
    print(prompt, flush=True)
    while True:
        try:
            value = input("Enter value: ").strip()
        except EOFError:
            raise RuntimeError(f"Input required for '{prompt}', but no interactive input is available.")
        if value:
            return value
        print("Value is required.", flush=True)


def _prompt_optional(prompt: str) -> str | None:
    print(prompt, flush=True)
    try:
        value = input("Enter value (or press Enter to skip): ").strip()
    except EOFError:
        return None
    return value or None


def _prompt_add_another_provider() -> tuple[str, str]:
    while True:
        provider = _prompt_non_empty("Set provider name (for example: openrouter)").lower()
        if provider in {"scripted", "openai", "gemini", "add_another_provider", "later"}:
            print("That provider name is reserved. Choose another name.", flush=True)
            continue
        break
    api_key = _prompt_non_empty(f"Set {_provider_api_env_name(provider)}")
    model_name = _prompt_non_empty(f"Set {_provider_model_env_name(provider)}")
    base_url = _prompt_optional(f"Optional: set {_provider_base_url_env_name(provider)} for OpenAI-compatible endpoints")
    _register_custom_provider(provider, api_key, model_name, base_url)
    print(f"Provider added: {provider}", flush=True)
    return provider, model_name


def _prompt_provider_setup_if_missing_keys(
    provider: str,
    model: str | None,
    openai_client_initialized: bool,
    gemini_client_initialized: bool,
) -> tuple[str, str | None, bool, bool]:
    if openai_client_initialized or gemini_client_initialized:
        return provider, model, openai_client_initialized, gemini_client_initialized

    if not _is_interactive():
        # In non-interactive mode, never block on setup prompts.
        return "scripted", None, False, False

    choice = _prompt_choice(
        "No API key found. Configure a provider now?",
        ["openai", "gemini", "add_another_provider", "later"],
        default="later",
    )
    if choice == "later":
        return "scripted", None, False, False
    if choice == "add_another_provider":
        provider_name, model_name = _prompt_add_another_provider()
        return provider_name, model_name, False, False

    api_key = _prompt_non_empty(f"Set {choice.upper()} API key")
    model_name = _prompt_non_empty(f"Set {choice.upper()} model name")

    if choice == "openai":
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_BASELINE_MODEL"] = model_name
        os.environ["OPENAI_USE_REAL_BASELINE"] = "1"
        return "openai", model_name, True, False

    os.environ["GEMINI_API_KEY"] = api_key
    os.environ["GEMINI_BASELINE_MODEL"] = model_name
    os.environ["GEMINI_USE_REAL_BASELINE"] = "1"
    return "gemini", model_name, False, True


def _ensure_provider_requirements(provider: str, model: str | None) -> tuple[str, str | None]:
    if provider == "scripted":
        return provider, None

    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = _prompt_non_empty("Set OPENAI_API_KEY")
        if not model:
            model = _prompt_non_empty("Set OPENAI model name")
            os.environ["OPENAI_BASELINE_MODEL"] = model
        return provider, model
    if provider == "gemini":
        if not os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = _prompt_non_empty("Set GEMINI_API_KEY")
        if not model:
            model = _prompt_non_empty("Set GEMINI model name")
            os.environ["GEMINI_BASELINE_MODEL"] = model
        return provider, model

    api_env = _provider_api_env_name(provider)
    model_env = _provider_model_env_name(provider)
    if not os.getenv(api_env):
        os.environ[api_env] = _prompt_non_empty(f"Set {api_env}")
    if not model:
        model = _prompt_non_empty(f"Set {model_env}")
        os.environ[model_env] = model
    if provider not in CUSTOM_PROVIDER_NAMES:
        CUSTOM_PROVIDER_NAMES.append(provider)
    return provider, model


def _prompt_choice(prompt: str, options: list[str], default: str | None = None) -> str:
    print(prompt, flush=True)
    for index, option in enumerate(options, start=1):
        default_label = " (default)" if option == default else ""
        print(f"  {index}. {option}{default_label}", flush=True)
    while True:
        try:
            raw = input("Enter number or value, then press Enter: ").strip()
        except EOFError:
            if default is not None:
                print(f"No input available. Using default: {default}", flush=True)
                return default
            fallback = options[0]
            print(f"No input available. Using fallback: {fallback}", flush=True)
            return fallback
        if not raw and default:
            return default
        if raw.isdigit():
            index = int(raw) - 1
            if 0 <= index < len(options):
                return options[index]
        value = raw
        if value in options:
            return value
        print(f"Choose one of: {', '.join(options)}", flush=True)


def _prompt_int(prompt: str, default: int = 0) -> int:
    print(f"{prompt} (press Enter for {default})", flush=True)
    while True:
        try:
            raw = input("Enter integer: ").strip()
        except EOFError:
            print(f"No input available. Using default: {default}", flush=True)
            return default
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            print("Enter a valid integer.", flush=True)


def _select_single_run(provider: str, model: str | None) -> tuple[TaskTier, str, int, str, str | None]:
    available_tiers = [tier.value for tier in TaskTier]
    tier_value = _prompt_choice("Select tier", available_tiers, default=TaskTier.EASY.value)
    tier = TaskTier(tier_value)
    tasks = [task for task in list_tasks() if task.tier == tier]
    print(f"Available {tier.value} scenarios:", flush=True)
    for index, task in enumerate(tasks, start=1):
        print(f"  {index}. {task.task_id}  {task.name}", flush=True)
    task_id = _prompt_choice("Select scenario", [task.task_id for task in tasks], default=tasks[0].task_id)
    seed = _prompt_int("Select seed", default=0)
    provider_options = _provider_options(default_provider=provider)
    default_provider = provider if provider in provider_options else "scripted"
    chosen_provider = _prompt_choice("Select provider", provider_options, default=default_provider)
    if chosen_provider == "add_another_provider":
        chosen_provider, chosen_model = _prompt_add_another_provider()
    else:
        chosen_model = model if chosen_provider == provider else _default_model_for_provider(chosen_provider)
    chosen_provider, chosen_model = _ensure_provider_requirements(chosen_provider, chosen_model)
    return tier, task_id, seed, chosen_provider, chosen_model


def run_baseline(verbose: bool = False, run_all: bool = False):
    provider, model, openai_client_initialized, gemini_client_initialized = _resolve_provider_and_model()
    provider, model, openai_client_initialized, gemini_client_initialized = _prompt_provider_setup_if_missing_keys(
        provider,
        model,
        openai_client_initialized,
        gemini_client_initialized,
    )

    if verbose:
        print(
            f"Baseline provider={provider} model={model or 'unset'} "
            f"openai_ready={openai_client_initialized} gemini_ready={gemini_client_initialized}",
            flush=True,
        )

    if not run_all:
        tier, task_id, seed, provider, model = _select_single_run(provider, model)
        if verbose:
            print(
                f"Running tier={tier.value} task_id={task_id} seed={seed} provider={provider} model={model or 'unset'}...",
                flush=True,
            )
        step_logger = None
        if verbose and provider in {"openai", "gemini"}:
            def _log_step(message: str, *, current_tier: str = tier.value) -> None:
                print(_format_step_log_line(message, current_tier), flush=True)

            step_logger = _log_step
        result = run_requested_baseline(
            tier=tier,
            task_id=task_id,
            provider=provider,
            model=model,
            seed=seed,
            step_logger=step_logger,
        ).model_dump(mode="json")
        if verbose:
            print(
                f"Completed tier={tier.value} task_id={task_id} score={result['score']:.2f} "
                f"solved={result['solved']} steps={result['steps_taken']} mode={result['mode']}",
                flush=True,
            )
        return {
            "openai_client_initialized": openai_client_initialized,
            "gemini_client_initialized": gemini_client_initialized,
            "provider": provider,
            "model": model,
            "selected_tier": tier.value,
            "selected_task_id": task_id,
            "seed": seed,
            "result": result,
        }

    results = {}
    for tier in TaskTier:
        if verbose:
            print(f"Running tier={tier.value}...", flush=True)
        step_logger = None
        if verbose and provider in {"openai", "gemini"}:
            def _log_step(message: str, *, current_tier: str = tier.value) -> None:
                print(_format_step_log_line(message, current_tier), flush=True)

            step_logger = _log_step
        result = run_requested_baseline(tier=tier, provider=provider, model=model, step_logger=step_logger).model_dump(mode="json")
        results[tier.value] = result
        if verbose:
            print(
                f"Completed tier={tier.value} score={result['score']:.2f} "
                f"solved={result['solved']} steps={result['steps_taken']} mode={result['mode']}",
                flush=True,
            )
    return {
        "openai_client_initialized": openai_client_initialized,
        "gemini_client_initialized": gemini_client_initialized,
        "provider": provider,
        "model": model,
        "results": results,
    }


def _print_summary(payload: dict, run_all: bool) -> None:
    if run_all:
        print("Final summary:", flush=True)
        for tier, result in payload["results"].items():
            print(
                f"  {tier}: score={result['score']:.2f} solved={result['solved']} "
                f"steps={result['steps_taken']} mode={result['mode']}",
                flush=True,
            )
        return

    result = payload["result"]
    print("Final summary:", flush=True)
    print(
        f"  tier={payload['selected_tier']} task_id={payload['selected_task_id']} seed={payload['seed']}",
        flush=True,
    )
    print(
        f"  provider={payload['provider']} model={payload['model'] or 'default'} "
        f"score={result['score']:.2f} solved={result['solved']} steps={result['steps_taken']}",
        flush=True,
    )
    if result.get("grading_notes"):
        print("  notes:", flush=True)
        for note in result["grading_notes"]:
            print(f"    - {note}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the SRE incident baseline.")
    parser.add_argument("--all", action="store_true", help="Run one baseline scenario per tier instead of interactive single-scenario mode.")
    parser.add_argument("--json", action="store_true", help="Print the full result payload as JSON.")
    args = parser.parse_args()
    payload = run_baseline(verbose=not args.json, run_all=args.all)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_summary(payload, run_all=args.all)
