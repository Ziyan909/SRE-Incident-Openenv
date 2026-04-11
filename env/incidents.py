from __future__ import annotations

from copy import deepcopy
from random import Random

from env.models import ActionType, IncidentScenario, RootCauseCategory, ServiceStatus, TaskDefinition, TaskTier


SERVICES = [
    "api-gateway",
    "auth-service",
    "user-service",
    "payment-service",
    "db-postgres",
    "cache-redis",
]

DEPENDENCY_GRAPH = {
    "api-gateway": ["auth-service", "user-service", "payment-service"],
    "auth-service": ["cache-redis"],
    "user-service": ["db-postgres", "cache-redis"],
    "payment-service": ["db-postgres"],
    "db-postgres": [],
    "cache-redis": [],
}

BASE_VERSIONS = {
    "api-gateway": "v3.2.1",
    "auth-service": "v2.8.0",
    "user-service": "v4.0.2",
    "payment-service": "v5.4.1",
    "db-postgres": "v14.11",
    "cache-redis": "v7.2.4",
}


def make_scenario(
    *,
    scenario_id: str,
    tier: TaskTier,
    template_id: str | None = None,
    root_cause_service: str,
    root_cause_category: RootCauseCategory,
    correct_fix_action: ActionType,
    description: str,
    initial_statuses: dict[str, ServiceStatus],
    initial_versions: dict[str, str] | None = None,
    target_versions: dict[str, str] | None = None,
    correct_fix_version: str | None = None,
    correct_fix_replicas: int | None = None,
    acceptable_fix_actions: list[ActionType] | None = None,
    acceptable_fix_versions: list[str] | None = None,
    acceptable_fix_replicas: list[int] | None = None,
    secondary_root_causes: dict[str, RootCauseCategory] | None = None,
    secondary_fix_actions: dict[str, ActionType] | None = None,
    secondary_fix_versions: dict[str, str] | None = None,
    secondary_fix_replicas: dict[str, int] | None = None,
    red_herring_services: list[str] | None = None,
    max_steps: int = 20,
    public: bool = True,
    change_events: dict[str, list[str]] | None = None,
    rollout_status: dict[str, str] | None = None,
    trace_signals: dict[str, list[str]] | None = None,
    config_signals: dict[str, list[str]] | None = None,
) -> IncidentScenario:
    return IncidentScenario(
        scenario_id=scenario_id,
        tier=tier,
        template_id=template_id or scenario_id,
        seed=0,
        root_cause_service=root_cause_service,
        root_cause_category=root_cause_category,
        correct_fix_action=correct_fix_action,
        correct_fix_version=correct_fix_version,
        correct_fix_replicas=correct_fix_replicas,
        acceptable_fix_actions=list(acceptable_fix_actions or []),
        acceptable_fix_versions=list(acceptable_fix_versions or []),
        acceptable_fix_replicas=list(acceptable_fix_replicas or []),
        secondary_root_causes=deepcopy(secondary_root_causes or {}),
        secondary_fix_actions=deepcopy(secondary_fix_actions or {}),
        secondary_fix_versions=deepcopy(secondary_fix_versions or {}),
        secondary_fix_replicas=deepcopy(secondary_fix_replicas or {}),
        red_herring_services=red_herring_services or [],
        max_steps=max_steps,
        public=public,
        description=description,
        initial_versions=deepcopy(initial_versions or BASE_VERSIONS),
        target_versions=deepcopy(target_versions or BASE_VERSIONS),
        dependency_graph=deepcopy(DEPENDENCY_GRAPH),
        initial_statuses=initial_statuses,
        change_events=deepcopy(change_events or {}),
        rollout_status=deepcopy(rollout_status or {}),
        trace_signals=deepcopy(trace_signals or {}),
        config_signals=deepcopy(config_signals or {}),
    )


SCENARIOS_BY_TIER: dict[TaskTier, list[IncidentScenario]] = {
    TaskTier.EASY: [
        make_scenario(
            scenario_id="easy-auth-oom",
            tier=TaskTier.EASY,
            template_id="auth-oom",
            root_cause_service="auth-service",
            root_cause_category=RootCauseCategory.OOM_CRASH,
            correct_fix_action=ActionType.RESTART_SERVICE,
            acceptable_fix_actions=[ActionType.SCALE_UP],
            acceptable_fix_replicas=[3],
            description="Auth service crashed after an out-of-memory spike. API traffic is partially failing.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.DOWN,
                "user-service": ServiceStatus.HEALTHY,
                "payment-service": ServiceStatus.HEALTHY,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.HEALTHY,
            },
            change_events={
                "auth-service": [
                    "00:19 UTC deploy controller restarted one auth-service pod after memory pressure",
                    "00:14 UTC autoscaler reported repeated container restarts on auth-service",
                ]
            },
            max_steps=16,
        ),
        make_scenario(
            scenario_id="easy-cache-memory-pressure",
            tier=TaskTier.EASY,
            template_id="cache-memory-pressure",
            root_cause_service="cache-redis",
            root_cause_category=RootCauseCategory.MEMORY_LEAK,
            correct_fix_action=ActionType.SCALE_UP,
            correct_fix_replicas=4,
            acceptable_fix_actions=[ActionType.RESTART_SERVICE],
            description="Cache saturation is driving elevated auth latency. Additional replicas stabilize the hot path.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.DEGRADED,
                "user-service": ServiceStatus.HEALTHY,
                "payment-service": ServiceStatus.HEALTHY,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.DEGRADED,
            },
            change_events={
                "cache-redis": [
                    "00:21 UTC cache-redis traffic rose sharply after a batch import window opened",
                ],
                "auth-service": [
                    "00:17 UTC auth-service latency warning opened after cache response times climbed",
                ],
            },
            max_steps=16,
        ),
        make_scenario(
            scenario_id="easy-user-bad-deploy",
            tier=TaskTier.EASY,
            template_id="user-bad-deploy",
            root_cause_service="user-service",
            root_cause_category=RootCauseCategory.BAD_DEPLOY,
            correct_fix_action=ActionType.ROLLBACK_DEPLOY,
            correct_fix_version="v4.0.2",
            description="A user-service rollout broke profile fetches and is degrading top-level API calls.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.HEALTHY,
                "user-service": ServiceStatus.DOWN,
                "payment-service": ServiceStatus.HEALTHY,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.HEALTHY,
            },
            initial_versions={**BASE_VERSIONS, "user-service": "v4.1.0"},
            change_events={
                "user-service": [
                    "00:11 UTC rollout to user-service v4.1.0 completed on 100% of pods",
                    "00:09 UTC release guard flagged elevated startup failures on user-service",
                ]
            },
            max_steps=16,
        ),
        make_scenario(
            scenario_id="easy-gateway-config-flags",
            tier=TaskTier.EASY,
            template_id="gateway-config-flags",
            root_cause_service="api-gateway",
            root_cause_category=RootCauseCategory.CONFIG_ERROR,
            correct_fix_action=ActionType.ROLLBACK_DEPLOY,
            correct_fix_version="v3.2.1",
            description="A gateway config flag rollout is rejecting valid traffic at the edge before requests reach downstream services.",
            initial_statuses={
                "api-gateway": ServiceStatus.DOWN,
                "auth-service": ServiceStatus.HEALTHY,
                "user-service": ServiceStatus.HEALTHY,
                "payment-service": ServiceStatus.HEALTHY,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.HEALTHY,
            },
            initial_versions={**BASE_VERSIONS, "api-gateway": "v3.2.8"},
            change_events={
                "api-gateway": [
                    "00:13 UTC edge config bundle rolled out with a stricter authz flag set",
                    "00:08 UTC synthetic checks began failing on otherwise healthy routes",
                ],
            },
            rollout_status={"api-gateway": "rollout 100% complete, automated rollback paused"},
            trace_signals={
                "api-gateway": [
                    "trace edge-request-14: rejected in gateway policy evaluation before upstream fan-out",
                    "trace edge-request-12: 503 returned from gateway with no downstream spans emitted",
                ],
            },
            config_signals={
                "api-gateway": [
                    "config diff shows edge.authz.strict_mode enabled without the matching route allowlist update",
                    "gateway policy bundle changed request rejection behavior before any downstream handoff",
                ],
            },
            max_steps=16,
        ),
        make_scenario(
            scenario_id="easy-payment-oom-loop",
            tier=TaskTier.EASY,
            template_id="payment-oom-loop",
            root_cause_service="payment-service",
            root_cause_category=RootCauseCategory.OOM_CRASH,
            correct_fix_action=ActionType.RESTART_SERVICE,
            acceptable_fix_actions=[ActionType.SCALE_UP],
            acceptable_fix_replicas=[3],
            description="Payment workers are crash-looping from memory spikes, causing checkout failures while the rest of the stack stays healthy.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.HEALTHY,
                "user-service": ServiceStatus.HEALTHY,
                "payment-service": ServiceStatus.DOWN,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.HEALTHY,
            },
            change_events={
                "payment-service": [
                    "00:16 UTC checkout surge triggered a payment worker crash loop",
                ],
            },
            trace_signals={
                "payment-service": [
                    "trace checkout-21: request path reached payment-service and terminated on worker restart",
                    "trace checkout-19: upstream spans normal until payment authorization step timed out",
                ],
            },
            max_steps=16,
            public=False,
        ),
    ],
    TaskTier.MEDIUM: [
        make_scenario(
            scenario_id="medium-db-cascade",
            tier=TaskTier.MEDIUM,
            template_id="db-cascade",
            root_cause_service="db-postgres",
            root_cause_category=RootCauseCategory.DEPENDENCY_FAIL,
            correct_fix_action=ActionType.RESTART_SERVICE,
            description="A database outage is cascading into downstream service degradation.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.HEALTHY,
                "user-service": ServiceStatus.DEGRADED,
                "payment-service": ServiceStatus.DEGRADED,
                "db-postgres": ServiceStatus.DOWN,
                "cache-redis": ServiceStatus.HEALTHY,
            },
            change_events={
                "db-postgres": [
                    "00:25 UTC primary database maintenance window ended with failed post-checks",
                ],
                "payment-service": [
                    "00:18 UTC downstream timeout alarms opened in payment-service",
                ],
            },
            max_steps=20,
        ),
        make_scenario(
            scenario_id="medium-payment-config",
            tier=TaskTier.MEDIUM,
            template_id="payment-config",
            root_cause_service="payment-service",
            root_cause_category=RootCauseCategory.CONFIG_ERROR,
            correct_fix_action=ActionType.ROLLBACK_DEPLOY,
            correct_fix_version="v5.4.1",
            description="A payment-service config rollout broke checkout traffic and polluted gateway alerts.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.HEALTHY,
                "user-service": ServiceStatus.HEALTHY,
                "payment-service": ServiceStatus.DOWN,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.HEALTHY,
            },
            initial_versions={**BASE_VERSIONS, "payment-service": "v5.4.9"},
            red_herring_services=["api-gateway"],
            change_events={
                "payment-service": [
                    "00:12 UTC configuration rollout finished for payment-service v5.4.9",
                    "00:10 UTC runtime validation warning opened on payment-service",
                ],
                "api-gateway": [
                    "00:07 UTC gateway saturation alarm opened while checkout retries increased",
                ],
            },
            max_steps=20,
        ),
        make_scenario(
            scenario_id="medium-auth-cache-chain",
            tier=TaskTier.MEDIUM,
            template_id="auth-cache-chain",
            root_cause_service="cache-redis",
            root_cause_category=RootCauseCategory.DEPENDENCY_FAIL,
            correct_fix_action=ActionType.RESTART_SERVICE,
            acceptable_fix_actions=[ActionType.SCALE_UP],
            acceptable_fix_replicas=[3],
            description="Redis instability is causing auth failures, which in turn degrades the gateway.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.DEGRADED,
                "user-service": ServiceStatus.HEALTHY,
                "payment-service": ServiceStatus.HEALTHY,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.DOWN,
            },
            change_events={
                "cache-redis": [
                    "00:20 UTC cache-redis node replacement left one shard under-provisioned",
                ],
                "auth-service": [
                    "00:16 UTC auth-service token validation errors climbed after cache misses surged",
                ],
            },
            max_steps=20,
        ),
        make_scenario(
            scenario_id="medium-user-db-deadlock",
            tier=TaskTier.MEDIUM,
            template_id="user-db-deadlock",
            root_cause_service="db-postgres",
            root_cause_category=RootCauseCategory.DB_DEADLOCK,
            correct_fix_action=ActionType.RESTART_SERVICE,
            description="A deadlock wave in Postgres is degrading user-service writes and creating misleading gateway symptoms.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.HEALTHY,
                "user-service": ServiceStatus.DEGRADED,
                "payment-service": ServiceStatus.HEALTHY,
                "db-postgres": ServiceStatus.DOWN,
                "cache-redis": ServiceStatus.HEALTHY,
            },
            red_herring_services=["api-gateway"],
            change_events={
                "db-postgres": [
                    "00:24 UTC lock wait alarms opened after a bulk profile migration job overlapped with live writes",
                ],
                "user-service": [
                    "00:17 UTC user write latency crossed SLO while reads remained mostly healthy",
                ],
            },
            rollout_status={"user-service": "application rollout stable, no recent deploy anomalies"},
            trace_signals={
                "user-service": [
                    "trace profile-save-09: app span stalled on postgres commit for 4.2s",
                    "trace profile-save-04: request path healthy until database transaction lock acquisition",
                ],
            },
            max_steps=20,
        ),
        make_scenario(
            scenario_id="medium-cache-bad-deploy",
            tier=TaskTier.MEDIUM,
            template_id="cache-bad-deploy",
            root_cause_service="cache-redis",
            root_cause_category=RootCauseCategory.BAD_DEPLOY,
            correct_fix_action=ActionType.ROLLBACK_DEPLOY,
            correct_fix_version="v7.2.4",
            description="A Redis rollout destabilized a shard and now auth and user traffic degrade through cache misses and slow fallbacks.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.DEGRADED,
                "user-service": ServiceStatus.DEGRADED,
                "payment-service": ServiceStatus.HEALTHY,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.DOWN,
            },
            initial_versions={**BASE_VERSIONS, "cache-redis": "v7.3.1"},
            change_events={
                "cache-redis": [
                    "00:20 UTC cache-redis v7.3.1 rolled onto the primary shard set",
                    "00:15 UTC cache warmup failed on one shard after the deploy completed",
                ],
            },
            rollout_status={"cache-redis": "rollout 50% complete, one shard auto-paused by controller"},
            trace_signals={
                "auth-service": [
                    "trace auth-token-15: repeated cache fetch failures caused fallback latency inflation",
                ],
                "user-service": [
                    "trace profile-read-07: request stayed healthy until cache lookup span failed and DB fallback expanded",
                ],
            },
            max_steps=20,
            public=False,
        ),
    ],
    TaskTier.HARD: [
        make_scenario(
            scenario_id="hard-payment-red-herrings",
            tier=TaskTier.HARD,
            template_id="payment-red-herrings",
            root_cause_service="payment-service",
            root_cause_category=RootCauseCategory.BAD_DEPLOY,
            correct_fix_action=ActionType.ROLLBACK_DEPLOY,
            correct_fix_version="v5.4.1",
            description="A bad payment-service deploy is the primary outage while Redis is also under memory pressure and unrelated alerts distract the responder.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.DEGRADED,
                "user-service": ServiceStatus.HEALTHY,
                "payment-service": ServiceStatus.DOWN,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.DEGRADED,
            },
            initial_versions={**BASE_VERSIONS, "payment-service": "v5.5.0"},
            secondary_root_causes={"cache-redis": RootCauseCategory.MEMORY_LEAK},
            secondary_fix_actions={"cache-redis": ActionType.SCALE_UP},
            secondary_fix_replicas={"cache-redis": 4},
            red_herring_services=["api-gateway"],
            change_events={
                "payment-service": [
                    "00:13 UTC phased rollout to payment-service v5.5.0 completed",
                    "00:11 UTC startup failures observed on fresh payment-service instances",
                ],
                "cache-redis": [
                    "00:08 UTC cache-redis memory growth alarm opened during the same incident window",
                ],
                "api-gateway": [
                    "00:06 UTC gateway retry storm warning opened from checkout traffic",
                ],
            },
            max_steps=24,
        ),
        make_scenario(
            scenario_id="hard-db-deadlock-noise",
            tier=TaskTier.HARD,
            template_id="db-deadlock-noise",
            root_cause_service="db-postgres",
            root_cause_category=RootCauseCategory.DB_DEADLOCK,
            correct_fix_action=ActionType.RESTART_SERVICE,
            description="Database deadlocks are the primary outage while cache memory pressure causes a concurrent auth incident and extra alert noise.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.DEGRADED,
                "user-service": ServiceStatus.DEGRADED,
                "payment-service": ServiceStatus.DEGRADED,
                "db-postgres": ServiceStatus.DOWN,
                "cache-redis": ServiceStatus.DEGRADED,
            },
            secondary_root_causes={"cache-redis": RootCauseCategory.MEMORY_LEAK},
            secondary_fix_actions={"cache-redis": ActionType.SCALE_UP},
            secondary_fix_replicas={"cache-redis": 4},
            red_herring_services=["auth-service"],
            change_events={
                "db-postgres": [
                    "00:22 UTC lock queue depth exceeded safe threshold on primary database",
                ],
                "cache-redis": [
                    "00:15 UTC cache-redis capacity alert opened during the lock incident",
                ],
                "auth-service": [
                    "00:09 UTC auth-service warning opened but user impact remained inconclusive",
                ],
            },
            max_steps=24,
        ),
        make_scenario(
            scenario_id="hard-auth-memleak-rollup",
            tier=TaskTier.HARD,
            template_id="auth-memleak-rollup",
            root_cause_service="auth-service",
            root_cause_category=RootCauseCategory.MEMORY_LEAK,
            correct_fix_action=ActionType.SCALE_UP,
            correct_fix_replicas=5,
            acceptable_fix_actions=[ActionType.RESTART_SERVICE],
            description="A memory leak in auth-service is the primary outage while payment-service is also down from a bad deploy and user-service warns loudly.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.DEGRADED,
                "user-service": ServiceStatus.DEGRADED,
                "payment-service": ServiceStatus.DOWN,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.HEALTHY,
            },
            initial_versions={**BASE_VERSIONS, "payment-service": "v5.5.0"},
            secondary_root_causes={"payment-service": RootCauseCategory.BAD_DEPLOY},
            secondary_fix_actions={"payment-service": ActionType.ROLLBACK_DEPLOY},
            secondary_fix_versions={"payment-service": "v5.4.1"},
            red_herring_services=["user-service"],
            change_events={
                "auth-service": [
                    "00:18 UTC auth-service memory trend breached sustained leak threshold",
                ],
                "payment-service": [
                    "00:14 UTC payment-service rollout to v5.5.0 completed with partial health-check failures",
                ],
                "user-service": [
                    "00:05 UTC user-service warning opened after upstream auth timeouts increased",
                ],
            },
            max_steps=24,
        ),
        make_scenario(
            scenario_id="hard-gateway-config-canary",
            tier=TaskTier.HARD,
            template_id="gateway-config-canary",
            root_cause_service="api-gateway",
            root_cause_category=RootCauseCategory.CONFIG_ERROR,
            correct_fix_action=ActionType.ROLLBACK_DEPLOY,
            correct_fix_version="v3.2.1",
            description="A gateway canary config is the primary incident while auth-service is separately under memory pressure and downstream alerts obscure the edge failure.",
            initial_statuses={
                "api-gateway": ServiceStatus.DOWN,
                "auth-service": ServiceStatus.DEGRADED,
                "user-service": ServiceStatus.DEGRADED,
                "payment-service": ServiceStatus.HEALTHY,
                "db-postgres": ServiceStatus.HEALTHY,
                "cache-redis": ServiceStatus.HEALTHY,
            },
            initial_versions={**BASE_VERSIONS, "api-gateway": "v3.2.8"},
            secondary_root_causes={"auth-service": RootCauseCategory.MEMORY_LEAK},
            secondary_fix_actions={"auth-service": ActionType.SCALE_UP},
            secondary_fix_replicas={"auth-service": 4},
            red_herring_services=["user-service"],
            change_events={
                "api-gateway": [
                    "00:12 UTC gateway canary promoted a stricter config package to all edge pods",
                ],
                "auth-service": [
                    "00:09 UTC auth-service memory slope warning opened under elevated login volume",
                ],
            },
            rollout_status={
                "api-gateway": "canary promoted from 10% to 100% in 6 minutes",
                "auth-service": "stable release, resource saturation rising",
            },
            trace_signals={
                "api-gateway": [
                    "trace edge-checkout-11: request rejected at gateway filter stage with no upstream spans",
                    "trace edge-login-03: edge policy span failed before auth-service was invoked",
                ],
                "auth-service": [
                    "trace login-42: auth span slow but still completing when called directly",
                ],
            },
            config_signals={
                "api-gateway": [
                    "config diff shows gateway.canary_policy promoted globally with an incomplete exception list",
                    "edge config package changed policy evaluation while downstream release versions stayed stable",
                ],
            },
            max_steps=24,
        ),
        make_scenario(
            scenario_id="hard-user-db-rollup",
            tier=TaskTier.HARD,
            template_id="user-db-rollup",
            root_cause_service="db-postgres",
            root_cause_category=RootCauseCategory.DB_DEADLOCK,
            correct_fix_action=ActionType.RESTART_SERVICE,
            description="A primary database deadlock incident collides with a bad user-service rollout, forcing the responder to separate the real blocker from a convincing secondary fault.",
            initial_statuses={
                "api-gateway": ServiceStatus.DEGRADED,
                "auth-service": ServiceStatus.HEALTHY,
                "user-service": ServiceStatus.DOWN,
                "payment-service": ServiceStatus.DEGRADED,
                "db-postgres": ServiceStatus.DOWN,
                "cache-redis": ServiceStatus.HEALTHY,
            },
            initial_versions={**BASE_VERSIONS, "user-service": "v4.1.0"},
            secondary_root_causes={"user-service": RootCauseCategory.BAD_DEPLOY},
            secondary_fix_actions={"user-service": ActionType.ROLLBACK_DEPLOY},
            secondary_fix_versions={"user-service": "v4.0.2"},
            red_herring_services=["payment-service"],
            change_events={
                "db-postgres": [
                    "00:23 UTC write lock saturation crossed emergency thresholds on postgres primary",
                ],
                "user-service": [
                    "00:18 UTC user-service rollout to v4.1.0 introduced noisy startup faults",
                ],
                "payment-service": [
                    "00:07 UTC payment-service alarms opened from transaction queue buildup",
                ],
            },
            rollout_status={"user-service": "rollout complete, rollback candidate available"},
            trace_signals={
                "payment-service": [
                    "trace checkout-71: payment path stalled on shared postgres transaction commit",
                ],
                "user-service": [
                    "trace profile-mutate-31: request failed on both app bootstrap instability and blocked DB commit",
                ],
            },
            max_steps=24,
            public=False,
        ),
    ],
}


SCENARIOS_BY_ID = {scenario.scenario_id: scenario for scenarios in SCENARIOS_BY_TIER.values() for scenario in scenarios}


def _public_task_id_for_index(tier: TaskTier, index: int) -> str:
    return f"{tier.value}-{index:02d}"


PUBLIC_TASK_ID_BY_SCENARIO_ID = {
    scenario.scenario_id: _public_task_id_for_index(scenario.tier, index)
    for tier in TaskTier
    for index, scenario in enumerate(SCENARIOS_BY_TIER[tier], start=1)
}
SCENARIO_ID_BY_PUBLIC_TASK_ID = {
    public_task_id: scenario_id for scenario_id, public_task_id in PUBLIC_TASK_ID_BY_SCENARIO_ID.items()
}
PUBLIC_TEMPLATE_ID_BY_TEMPLATE_ID = {
    template_id: f"family-{index:02d}"
    for index, template_id in enumerate(sorted({scenario.template_id for scenario in SCENARIOS_BY_ID.values()}), start=1)
}


def public_task_id_for(task_id: str) -> str:
    return PUBLIC_TASK_ID_BY_SCENARIO_ID.get(task_id, task_id)


def public_template_id_for(template_id: str | None) -> str | None:
    if template_id is None:
        return None
    return PUBLIC_TEMPLATE_ID_BY_TEMPLATE_ID.get(template_id, template_id)


def resolve_task_id(task_id: str) -> str:
    if task_id in SCENARIOS_BY_ID:
        return task_id
    if task_id in SCENARIO_ID_BY_PUBLIC_TASK_ID:
        return SCENARIO_ID_BY_PUBLIC_TASK_ID[task_id]
    raise KeyError(f"Unknown task_id: {task_id}")


def _public_task_name(scenario: IncidentScenario) -> str:
    return f"{scenario.tier.value.title()} Incident {PUBLIC_TASK_ID_BY_SCENARIO_ID[scenario.scenario_id].split('-')[-1]}"


def _public_task_description(scenario: IncidentScenario) -> str:
    impacted = sum(1 for status in scenario.initial_statuses.values() if status != ServiceStatus.HEALTHY)
    article = "an" if scenario.tier == TaskTier.EASY else "a"
    return (
        f"Investigate {article} {scenario.tier.value} production incident affecting {impacted} service"
        f"{'' if impacted == 1 else 's'}. Use logs, metrics, dependency checks, and recovery validation to identify and fix the primary issue."
    )


def _public_service_focus(scenario: IncidentScenario) -> list[str]:
    return []


def _public_grader_name(task_id: str) -> str:
    return f"grade_{task_id.replace('-', '_')}"

TASKS = [
    TaskDefinition(
        task_id=PUBLIC_TASK_ID_BY_SCENARIO_ID[scenario.scenario_id],
        tier=scenario.tier,
        name=_public_task_name(scenario),
        description=_public_task_description(scenario),
        max_steps=scenario.max_steps,
        grader=_public_grader_name(PUBLIC_TASK_ID_BY_SCENARIO_ID[scenario.scenario_id]) if scenario.public else None,
        template_id=public_template_id_for(scenario.template_id),
        supports_seed_variants=True,
        service_focus=_public_service_focus(scenario),
        action_space=list(ActionType),
        observation_space_description="Observation is partially observable: statuses are symptom-biased, versions and dependencies must be discovered, and logs/metrics are only revealed through targeted actions.",
    )
    for scenario in SCENARIOS_BY_ID.values()
]


def get_scenario(tier: TaskTier | None = None, task_id: str | None = None) -> IncidentScenario:
    if task_id:
        return deepcopy(SCENARIOS_BY_ID[resolve_task_id(task_id)])
    if tier is None:
        tier = TaskTier.EASY
    return deepcopy(SCENARIOS_BY_TIER[tier][0])


def materialize_seeded_scenario(base: IncidentScenario, seed: int = 0) -> IncidentScenario:
    scenario = deepcopy(base)
    scenario.seed = seed
    if seed == 0:
        return scenario

    rng = Random(f"{scenario.scenario_id}:{seed}")

    if scenario.root_cause_category in {RootCauseCategory.BAD_DEPLOY, RootCauseCategory.CONFIG_ERROR}:
        current = scenario.initial_versions[scenario.root_cause_service]
        if current.startswith("v"):
            parts = current[1:].split(".")
            if parts and parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + seed)
                scenario.initial_versions[scenario.root_cause_service] = "v" + ".".join(parts)
        scenario.change_events.setdefault(scenario.root_cause_service, []).append(
            f"00:0{rng.randint(1, 9)} UTC seeded rollout variant {seed} changed the active release train"
        )
        scenario.rollout_status[scenario.root_cause_service] = (
            scenario.rollout_status.get(scenario.root_cause_service, "rollout active")
            + f" · seeded variant {seed}"
        )

    if scenario.root_cause_category == RootCauseCategory.MEMORY_LEAK and scenario.correct_fix_replicas is not None:
        scenario.correct_fix_replicas = min(6, scenario.correct_fix_replicas + (seed % 2))
        scenario.change_events.setdefault(scenario.root_cause_service, []).append(
            f"00:1{rng.randint(0, 8)} UTC seeded traffic shape variant {seed} raised sustained concurrency"
        )
        scenario.trace_signals.setdefault(scenario.root_cause_service, []).append(
            f"trace seed-{seed}: sustained concurrency variant increased queueing on {scenario.root_cause_service}"
        )

    if scenario.secondary_root_causes:
        eligible_red_herrings = [service for service in SERVICES if service not in {scenario.root_cause_service, *scenario.secondary_root_causes.keys()}]
        rng.shuffle(eligible_red_herrings)
        scenario.red_herring_services = eligible_red_herrings[: max(1, len(scenario.red_herring_services))]

    scenario.description = f"{scenario.description} Seed variant {seed} adjusts recent changes and misleading signals."
    return scenario


def list_tasks() -> list[TaskDefinition]:
    visible_task_ids = {
        PUBLIC_TASK_ID_BY_SCENARIO_ID[scenario.scenario_id]
        for scenario in SCENARIOS_BY_ID.values()
        if scenario.public
    }
    return sorted(
        [task for task in TASKS if task.task_id in visible_task_ids],
        key=lambda task: (task.tier.value, task.task_id),
    )


def list_scenarios(tier: TaskTier | None = None, include_hidden: bool = True) -> list[IncidentScenario]:
    scenarios = SCENARIOS_BY_ID.values() if tier is None else SCENARIOS_BY_TIER[tier]
    return [deepcopy(scenario) for scenario in scenarios if include_hidden or scenario.public]
