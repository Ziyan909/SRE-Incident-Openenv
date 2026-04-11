"""Tier-specific deterministic graders and validator discovery exports."""

from __future__ import annotations

from env.incidents import list_tasks


def _normalize_reward(reward: float | int | None) -> float:
    if reward is None:
        return 0.0
    return min(max(float(reward), 0.0), 1.0)


def _extract_task_id(state: object = None, result: object = None, **_: object) -> str | None:
    for payload in (state, result):
        if isinstance(payload, dict):
            task_id = payload.get("task_id") or payload.get("scenario_id")
            if isinstance(task_id, str):
                return task_id
    return None


def _make_task_grader(expected_task_id: str):
    def _grader(
        state: dict | None = None, reward: float = 0.0, result: dict | None = None, **kwargs: object
    ) -> float:
        return _normalize_reward(reward if _extract_task_id(state=state, result=result, **kwargs) == expected_task_id else 0.0)

    _grader.__name__ = f"grade_{expected_task_id.replace('-', '_')}"
    return _grader


GRADERS = {}
TASK_GRADER_PAIRS = []

for _task in list_tasks():
    if not _task.grader:
        continue
    _grader = _make_task_grader(_task.task_id)
    globals()[_task.grader] = _grader
    GRADERS[_task.task_id] = _grader
    TASK_GRADER_PAIRS.append((_task.task_id, _grader))

__all__ = sorted([*globals().keys()])
