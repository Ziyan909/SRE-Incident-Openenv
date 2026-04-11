"""Static grader exports for hackathon validator discovery."""

from __future__ import annotations


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


def grade_easy_01(state: dict | None = None, reward: float = 0.0, result: dict | None = None, **kwargs: object) -> float:
    return _normalize_reward(reward if _extract_task_id(state=state, result=result, **kwargs) == "easy-01" else 0.0)


def grade_medium_01(
    state: dict | None = None, reward: float = 0.0, result: dict | None = None, **kwargs: object
) -> float:
    return _normalize_reward(reward if _extract_task_id(state=state, result=result, **kwargs) == "medium-01" else 0.0)


def grade_hard_01(state: dict | None = None, reward: float = 0.0, result: dict | None = None, **kwargs: object) -> float:
    return _normalize_reward(reward if _extract_task_id(state=state, result=result, **kwargs) == "hard-01" else 0.0)


GRADERS = {
    "easy-01": grade_easy_01,
    "medium-01": grade_medium_01,
    "hard-01": grade_hard_01,
}

TASK_GRADER_PAIRS = [
    ("easy-01", grade_easy_01),
    ("medium-01", grade_medium_01),
    ("hard-01", grade_hard_01),
]

__all__ = [
    "grade_easy_01",
    "grade_medium_01",
    "grade_hard_01",
    "GRADERS",
    "TASK_GRADER_PAIRS",
]
