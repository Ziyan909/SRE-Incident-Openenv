from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from env.baseline_runner import BaselineResponse, run_benchmark, run_requested_baseline
from env.environment import SREIncidentEnv
from env.incidents import list_tasks, public_task_id_for
from env.models import Action, ReplayRecord, ReplayStep, TaskTier


app = FastAPI(title="SRE Incident Environment", version="0.1.0")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
ARTIFACTS_ROOT = Path(__file__).resolve().parent.parent / "artifacts"
REPLAYS_DIR = ARTIFACTS_ROOT / "replays"
BENCHMARKS_DIR = ARTIFACTS_ROOT / "benchmarks"
REPLAYS_DIR.mkdir(parents=True, exist_ok=True)
BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@dataclass
class SessionEntry:
    env: SREIncidentEnv
    seed: int
    replay_steps: list[ReplayStep] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


SESSIONS: dict[str, SessionEntry] = {}
SESSION_TTL_SECONDS = max(60, int(os.getenv("SESSION_TTL_SECONDS", "7200")))
MAX_ACTIVE_SESSIONS = max(1, int(os.getenv("MAX_ACTIVE_SESSIONS", "500")))


class GraderRequest(BaseModel):
    tier: TaskTier = TaskTier.EASY
    task_id: str | None = None
    seed: int = 0
    actions: list[Action] = Field(default_factory=list)


class ResetRequest(BaseModel):
    tier: TaskTier = TaskTier.EASY
    task_id: str | None = None
    seed: int = 0


class StepRequest(BaseModel):
    session_id: str
    action: Action


@app.get("/")
def frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/tasks")
def get_tasks():
    return [task.model_dump(mode="json") for task in list_tasks()]


@app.post("/reset")
def reset_environment(request: ResetRequest):
    _cleanup_sessions()
    env = SREIncidentEnv(tier=request.tier, task_id=request.task_id, seed=request.seed)
    session_id = uuid4().hex
    observation = env.state()
    SESSIONS[session_id] = SessionEntry(
        env=env,
        seed=request.seed,
        replay_steps=[ReplayStep(step_number=observation.step_number, observation=observation)],
    )
    _enforce_session_limit()
    _persist_replay(session_id)
    return {
        "session_id": session_id,
        "task_id": public_task_id_for(env.task_id or "unknown"),
        "observation": observation.model_dump(mode="json"),
    }


@app.post("/step")
def step_environment(request: StepRequest):
    _cleanup_sessions()
    session = SESSIONS.get(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    session.updated_at = datetime.now(timezone.utc)
    observation, reward = session.env.step(request.action)
    session.replay_steps.append(
        ReplayStep(
            step_number=observation.step_number,
            action=request.action,
            observation=observation,
            reward=reward,
        )
    )
    _persist_replay(request.session_id)
    return {
        "session_id": request.session_id,
        "observation": observation.model_dump(mode="json"),
        "reward": reward.model_dump(mode="json"),
        "result": _public_result_payload(session.env.result().model_dump(mode="json")),
    }


@app.get("/state/{session_id}")
def state_environment(session_id: str):
    _cleanup_sessions()
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    session.updated_at = datetime.now(timezone.utc)
    return {
        "session_id": session_id,
        "observation": session.env.state().model_dump(mode="json"),
        "result": _public_result_payload(session.env.result().model_dump(mode="json")),
    }


@app.post("/grader")
def run_grader(request: GraderRequest):
    env = SREIncidentEnv(tier=request.tier, task_id=request.task_id, seed=request.seed)
    observations = []
    rewards = []
    for action in request.actions:
        observation, reward = env.step(action)
        observations.append(observation.model_dump(mode="json"))
        rewards.append(reward.model_dump(mode="json"))
        if observation.episode_done:
            break
    return {
        "observations": observations,
        "rewards": rewards,
        "result": _public_result_payload(env.result().model_dump(mode="json")),
    }


@app.get("/baseline")
def get_baseline(
    tier: TaskTier = TaskTier.EASY,
    task_id: str | None = None,
    use_openai: bool = False,
    provider: str | None = None,
    model: str | None = None,
    seed: int = 0,
):
    try:
        return run_requested_baseline(
            tier=tier,
            task_id=task_id,
            use_openai=use_openai,
            provider=provider,
            model=model,
            seed=seed,
        ).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/benchmark")
def get_benchmark(
    use_openai: bool = False,
    provider: str | None = None,
    model: str | None = None,
    seeds_per_scenario: int = Query(default=1, ge=1),
):
    benchmark_id = uuid4().hex
    try:
        report = run_benchmark(
            use_openai=use_openai,
            provider=provider,
            model=model,
            seeds_per_scenario=seeds_per_scenario,
        ).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    report["benchmark_id"] = benchmark_id
    report["provider"] = provider or report.get("mode")
    try:
        (BENCHMARKS_DIR / f"{benchmark_id}.json").write_text(json.dumps(report, indent=2))
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to persist benchmark report") from exc
    return report


@app.get("/benchmark/history")
def get_benchmark_history():
    items = []
    for path in sorted(BENCHMARKS_DIR.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "benchmark_id": payload.get("benchmark_id", path.stem),
                "generated_at": payload.get("generated_at"),
                "provider": payload.get("provider", payload.get("mode")),
                "model": payload.get("model"),
                "scenario_count": payload.get("scenario_count", 0),
                "public_scenario_count": payload.get("public_scenario_count", 0),
                "holdout_scenario_count": payload.get("holdout_scenario_count", 0),
                "overall_average_score": payload.get("overall_average_score", 0.0),
                "overall_solve_rate": payload.get("overall_solve_rate", 0.0),
            }
        )
    return items


@app.get("/benchmark/history/{benchmark_id}")
def get_benchmark_record(benchmark_id: str):
    path = BENCHMARKS_DIR / f"{benchmark_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Unknown benchmark_id")
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Benchmark record is unreadable") from exc


@app.get("/replay/{session_id}")
def get_replay(session_id: str):
    session = SESSIONS.get(session_id)
    if session is None:
        replay_path = REPLAYS_DIR / f"{session_id}.json"
        if replay_path.exists():
            try:
                return json.loads(replay_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=500, detail="Replay record is unreadable") from exc
        raise HTTPException(status_code=404, detail="Unknown session_id")
    replay = _build_replay_payload(session_id, session)
    replay["result"] = _public_result_payload(replay["result"])
    return replay


@app.get("/sessions")
def list_sessions():
    sessions = []
    for path in sorted(REPLAYS_DIR.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        sessions.append(
            {
                "session_id": payload["session_id"],
                "scenario_id": payload["scenario_id"],
                "tier": payload["tier"],
                "seed": payload["seed"],
                "steps": len(payload.get("replay_steps", [])),
                "score": payload.get("result", {}).get("final_score", 0.0),
                "solved": payload.get("result", {}).get("solved", False),
            }
        )
    return sessions


@app.get("/compare/{session_id}")
def compare_session(session_id: str, provider: str = "scripted", model: str | None = None):
    human = get_replay(session_id)
    scripted = _baseline_comparison_for(
        tier=TaskTier(human["tier"]),
        task_id=human["scenario_id"],
        seed=human["seed"],
        provider="scripted",
        model=None,
    )
    selected = None
    if provider != "scripted" or model:
        try:
            selected = _baseline_comparison_for(
                tier=TaskTier(human["tier"]),
                task_id=human["scenario_id"],
                seed=human["seed"],
                provider=provider,
                model=model,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session_id": session_id,
        "scenario_id": human["scenario_id"],
        "seed": human["seed"],
        "human": human,
        "scripted": scripted,
        "selected": selected,
    }


def _public_result_payload(result: dict) -> dict:
    if "scenario_id" in result:
        result["scenario_id"] = public_task_id_for(result["scenario_id"])
    return result


def _build_replay_payload(session_id: str, session: SessionEntry) -> dict:
    return ReplayRecord(
        session_id=session_id,
        scenario_id=public_task_id_for(session.env.task_id or "unknown"),
        tier=session.env.tier,
        seed=session.seed,
        replay_steps=session.replay_steps,
        result=session.env.result(),
        judge_summary=session.env.result().grading_notes,
    ).model_dump(mode="json")


def _persist_replay(session_id: str) -> None:
    session = SESSIONS.get(session_id)
    if session is None:
        return
    replay = _build_replay_payload(session_id, session)
    replay["result"] = _public_result_payload(replay["result"])
    replay["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        (REPLAYS_DIR / f"{session_id}.json").write_text(json.dumps(replay, indent=2))
    except OSError:
        # Keep in-memory session alive even if local persistence is temporarily unavailable.
        return


def _cleanup_sessions() -> None:
    if not SESSIONS:
        return
    now = datetime.now(timezone.utc)
    stale_ids = [
        session_id
        for session_id, session in SESSIONS.items()
        if (now - session.updated_at).total_seconds() > SESSION_TTL_SECONDS
    ]
    for session_id in stale_ids:
        SESSIONS.pop(session_id, None)


def _enforce_session_limit() -> None:
    overflow = len(SESSIONS) - MAX_ACTIVE_SESSIONS
    if overflow <= 0:
        return
    oldest = sorted(SESSIONS.items(), key=lambda item: item[1].updated_at)
    for session_id, _session in oldest[:overflow]:
        SESSIONS.pop(session_id, None)


def _baseline_comparison_for(
    *,
    tier: TaskTier,
    task_id: str,
    seed: int,
    provider: str,
    model: str | None,
) -> dict:
    baseline = run_requested_baseline(tier=tier, task_id=task_id, provider=provider, model=model, seed=seed)
    replay = _replay_from_baseline_result(tier=tier, task_id=task_id, seed=seed, baseline=baseline)
    return {
        "summary": baseline.model_dump(mode="json"),
        "replay": replay,
    }


def _replay_from_baseline_result(*, tier: TaskTier, task_id: str, seed: int, baseline: BaselineResponse) -> dict:
    env = SREIncidentEnv(tier=tier, task_id=task_id, seed=seed)
    initial_observation = env.state()
    replay_steps = [ReplayStep(step_number=initial_observation.step_number, observation=initial_observation)]
    for action_payload in baseline.actions:
        action = Action.model_validate(action_payload)
        observation, reward = env.step(action)
        replay_steps.append(
            ReplayStep(
                step_number=observation.step_number,
                action=action,
                observation=observation,
                reward=reward,
            )
        )
        if observation.episode_done:
            break
    replay = ReplayRecord(
        session_id=f"baseline-{baseline.mode}-{task_id}-{seed}",
        scenario_id=public_task_id_for(env.task_id or task_id),
        tier=tier,
        seed=seed,
        replay_steps=replay_steps,
        result=env.result(),
        judge_summary=env.result().grading_notes,
    ).model_dump(mode="json")
    replay["result"] = _public_result_payload(replay["result"])
    return replay
