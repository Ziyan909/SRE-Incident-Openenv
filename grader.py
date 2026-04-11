"""Singular grader module alias for hackathon validator discovery."""

from graders import GRADERS, TASK_GRADER_PAIRS, grade_easy_01, grade_medium_01, grade_hard_01

__all__ = [
    "grade_easy_01",
    "grade_medium_01",
    "grade_hard_01",
    "GRADERS",
    "TASK_GRADER_PAIRS",
]
