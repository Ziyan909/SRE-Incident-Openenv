"""Static task metadata for hackathon validator discovery.

These compatibility exports make at least three graded tasks discoverable
without changing the main API/runtime implementation.
"""

from grader import grade_easy_01, grade_medium_01, grade_hard_01

TASKS = [
    {
        "task_id": "easy-01",
        "name": "Easy Incident 01",
        "description": "Diagnose and mitigate the first public easy-tier incident.",
        "tier": "easy",
        "grader": grade_easy_01,
    },
    {
        "task_id": "medium-01",
        "name": "Medium Incident 01",
        "description": "Diagnose and mitigate the first public medium-tier incident.",
        "tier": "medium",
        "grader": grade_medium_01,
    },
    {
        "task_id": "hard-01",
        "name": "Hard Incident 01",
        "description": "Diagnose and mitigate the first public hard-tier incident.",
        "tier": "hard",
        "grader": grade_hard_01,
    },
]

TASK_GRADER_PAIRS = [
    ("easy-01", grade_easy_01),
    ("medium-01", grade_medium_01),
    ("hard-01", grade_hard_01),
]

__all__ = ["TASKS", "TASK_GRADER_PAIRS"]
