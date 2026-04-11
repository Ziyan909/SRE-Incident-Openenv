from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class ActionType(str, Enum):
    READ_LOGS = "read_logs"
    CHECK_METRICS = "check_metrics"
    PING_SERVICE = "ping_service"
    INSPECT_DEPLOY = "inspect_deploy"
    QUERY_TRACES = "query_traces"
    CHECK_RUNBOOK = "check_runbook"
    DIFF_CONFIG = "diff_config"
    DRAIN_TRAFFIC = "drain_traffic"
    FAILOVER_REGION = "failover_region"
    RESTART_SERVICE = "restart_service"
    ROLLBACK_DEPLOY = "rollback_deploy"
    SCALE_UP = "scale_up"
    CHECK_DEPENDENCIES = "check_dependencies"
    SUBMIT_DIAGNOSIS = "submit_diagnosis"


class TaskTier(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class RootCauseCategory(str, Enum):
    BAD_DEPLOY = "bad_deploy"
    OOM_CRASH = "oom_crash"
    DEPENDENCY_FAIL = "dependency_fail"
    DB_DEADLOCK = "db_deadlock"
    MEMORY_LEAK = "memory_leak"
    CONFIG_ERROR = "config_error"


class ServiceMetrics(BaseModel):
    cpu_percent: float = Field(..., ge=0, le=100)
    memory_percent: float = Field(..., ge=0, le=100)
    error_rate: float = Field(..., ge=0, le=1)
    latency_ms: float = Field(..., ge=0)
    restart_count: int = Field(default=0, ge=0)
    replicas: int = Field(default=2, ge=1, le=20)


class ServiceState(BaseModel):
    name: str
    status: ServiceStatus
    metrics: ServiceMetrics
    version: str
    last_deploy: str
    dependencies: List[str] = Field(default_factory=list)


class LogEntry(BaseModel):
    timestamp: str
    level: Literal["INFO", "WARN", "ERROR", "FATAL"]
    service: str
    message: str


class Observation(BaseModel):
    step_number: int
    timestamp: str
    services: Dict[str, ServiceState]
    active_alerts: List[str]
    incident_ticket: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    operator_notes: List[str] = Field(default_factory=list)
    service_owners: List[str] = Field(default_factory=list)
    deploy_history: List[str] = Field(default_factory=list)
    runbook_hints: List[str] = Field(default_factory=list)
    config_findings: List[str] = Field(default_factory=list)
    business_impact: List[str] = Field(default_factory=list)
    traffic_status: List[str] = Field(default_factory=list)
    queue_status: List[str] = Field(default_factory=list)
    feature_flags: List[str] = Field(default_factory=list)
    regional_status: List[str] = Field(default_factory=list)
    telemetry_warnings: List[str] = Field(default_factory=list)
    change_events: List[str] = Field(default_factory=list)
    rollout_status: List[str] = Field(default_factory=list)
    trace_spans: List[str] = Field(default_factory=list)
    logs: List[LogEntry] = Field(default_factory=list)
    action_result: Optional[str] = None
    evidence_summary: List[str] = Field(default_factory=list)
    unknowns: List[str] = Field(default_factory=list)
    validation_status: Optional[str] = None
    episode_done: bool = False


class Action(BaseModel):
    action_type: ActionType
    service: Optional[str] = None
    lines: Optional[int] = Field(default=50, ge=1, le=500)
    window_seconds: Optional[int] = Field(default=300, ge=60, le=3600)
    target_version: Optional[str] = None
    replicas: Optional[int] = Field(default=None, ge=1, le=10)
    root_cause_service: Optional[str] = None
    root_cause_category: Optional[RootCauseCategory] = None
    fix_description: Optional[str] = None


class RewardBreakdown(BaseModel):
    correct_service_identified: float = 0.0
    correct_root_cause: float = 0.0
    correct_fix_applied: float = 0.0
    acceptable_fix_applied: float = 0.0
    correct_diagnosis_text: float = 0.0
    exploration_bonus: float = 0.0
    wrong_action_penalty: float = 0.0
    redundant_step_penalty: float = 0.0


class Reward(BaseModel):
    total: float = Field(..., ge=-1.0, le=1.0)
    breakdown: RewardBreakdown
    message: str


class IncidentScenario(BaseModel):
    scenario_id: str
    tier: TaskTier
    template_id: str
    seed: int = 0
    root_cause_service: str
    root_cause_category: RootCauseCategory
    correct_fix_action: ActionType
    correct_fix_version: Optional[str] = None
    correct_fix_replicas: Optional[int] = None
    acceptable_fix_actions: List[ActionType] = Field(default_factory=list)
    acceptable_fix_versions: List[str] = Field(default_factory=list)
    acceptable_fix_replicas: List[int] = Field(default_factory=list)
    secondary_root_causes: Dict[str, RootCauseCategory] = Field(default_factory=dict)
    secondary_fix_actions: Dict[str, ActionType] = Field(default_factory=dict)
    secondary_fix_versions: Dict[str, str] = Field(default_factory=dict)
    secondary_fix_replicas: Dict[str, int] = Field(default_factory=dict)
    red_herring_services: List[str] = Field(default_factory=list)
    max_steps: int = Field(default=20, ge=5, le=50)
    public: bool = True
    description: str
    initial_versions: Dict[str, str]
    target_versions: Dict[str, str]
    dependency_graph: Dict[str, List[str]]
    initial_statuses: Dict[str, ServiceStatus]
    change_events: Dict[str, List[str]] = Field(default_factory=dict)
    rollout_status: Dict[str, str] = Field(default_factory=dict)
    trace_signals: Dict[str, List[str]] = Field(default_factory=dict)
    config_signals: Dict[str, List[str]] = Field(default_factory=dict)


class TaskDefinition(BaseModel):
    task_id: str
    tier: TaskTier
    name: str
    description: str
    max_steps: int
    grader: str | None = None
    template_id: str | None = None
    supports_seed_variants: bool = False
    service_focus: List[str] = Field(default_factory=list)
    action_space: List[ActionType]
    observation_space_description: str


class EpisodeResult(BaseModel):
    scenario_id: str
    tier: TaskTier
    steps_taken: int
    final_score: float = Field(..., ge=0.0, le=1.0)
    solved: bool
    analytics: Dict[str, float] = Field(default_factory=dict)
    reward_history: List[Reward]
    final_diagnosis: Optional[Action] = None
    grading_notes: List[str] = Field(default_factory=list)


class ReplayStep(BaseModel):
    step_number: int
    action: Optional[Action] = None
    observation: Observation
    reward: Optional[Reward] = None


class ReplayRecord(BaseModel):
    session_id: str
    scenario_id: str
    tier: TaskTier
    seed: int
    replay_steps: List[ReplayStep]
    result: EpisodeResult
    judge_summary: List[str] = Field(default_factory=list)
