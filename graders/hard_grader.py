from env.models import TaskTier
from graders.base import grade_tier


def grade():
    return grade_tier(TaskTier.HARD)
