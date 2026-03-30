from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from env.baseline_runner import scripted_baseline
from env.incidents import list_scenarios
from env.models import TaskTier


class ScenarioGrade(BaseModel):
    task_id: str
    score: float
    solved: bool
    steps_taken: int


class TierGradeReport(BaseModel):
    tier: TaskTier
    scenario_count: int
    average_score: float = Field(..., ge=0.0, le=1.0)
    all_solved: bool
    scenario_results: List[ScenarioGrade]


def grade_tier(tier: TaskTier) -> TierGradeReport:
    scenario_results: list[ScenarioGrade] = []
    for scenario in list_scenarios(tier):
        result = scripted_baseline(tier=tier, task_id=scenario.scenario_id)
        scenario_results.append(
            ScenarioGrade(
                task_id=scenario.scenario_id,
                score=result.score,
                solved=result.solved,
                steps_taken=result.steps_taken,
            )
        )
    if not scenario_results:
        return TierGradeReport(
            tier=tier,
            scenario_count=0,
            average_score=0.0,
            all_solved=False,
            scenario_results=[],
        )
    average_score = sum(item.score for item in scenario_results) / len(scenario_results)
    return TierGradeReport(
        tier=tier,
        scenario_count=len(scenario_results),
        average_score=average_score,
        all_solved=all(item.solved for item in scenario_results),
        scenario_results=scenario_results,
    )
