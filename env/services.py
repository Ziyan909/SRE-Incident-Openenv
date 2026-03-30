from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from env.models import ActionType, IncidentScenario, LogEntry, ServiceMetrics, ServiceState, ServiceStatus


BASE_METRICS = {
    ServiceStatus.HEALTHY: ServiceMetrics(
        cpu_percent=32.0,
        memory_percent=48.0,
        error_rate=0.01,
        latency_ms=85.0,
        restart_count=0,
        replicas=2,
    ),
    ServiceStatus.DEGRADED: ServiceMetrics(
        cpu_percent=74.0,
        memory_percent=78.0,
        error_rate=0.24,
        latency_ms=420.0,
        restart_count=0,
        replicas=2,
    ),
    ServiceStatus.DOWN: ServiceMetrics(
        cpu_percent=0.0,
        memory_percent=0.0,
        error_rate=1.0,
        latency_ms=5000.0,
        restart_count=0,
        replicas=2,
    ),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat()


def build_service_states(scenario: IncidentScenario) -> Dict[str, ServiceState]:
    now = utc_now()
    states: Dict[str, ServiceState] = {}
    for service, status in scenario.initial_statuses.items():
        states[service] = ServiceState(
            name=service,
            status=status,
            metrics=deepcopy(BASE_METRICS[status]),
            version=scenario.initial_versions[service],
            last_deploy=isoformat(now - timedelta(hours=3)),
            dependencies=list(scenario.dependency_graph.get(service, [])),
        )
    return states


def _service_is_fixed(service: str, state: ServiceState, scenario: IncidentScenario) -> bool:
    if service == scenario.root_cause_service:
        fix_action = scenario.correct_fix_action
        fix_version = scenario.correct_fix_version
        fix_replicas = scenario.correct_fix_replicas
        acceptable_actions = set(scenario.acceptable_fix_actions)
        acceptable_versions = set(scenario.acceptable_fix_versions)
        acceptable_replicas = scenario.acceptable_fix_replicas
    elif service in scenario.secondary_root_causes:
        fix_action = scenario.secondary_fix_actions.get(service)
        fix_version = scenario.secondary_fix_versions.get(service)
        fix_replicas = scenario.secondary_fix_replicas.get(service)
        acceptable_actions = set()
        acceptable_versions = set()
        acceptable_replicas = []
    else:
        return False

    fixed_by_rollback = fix_action is not None and fix_action.value == "rollback_deploy" and fix_version is not None and state.version == fix_version
    fixed_by_restart = fix_action is not None and fix_action.value == "restart_service" and state.metrics.restart_count > 0
    fixed_by_scale = (
        fix_action is not None
        and fix_action.value == "scale_up"
        and fix_replicas is not None
        and state.metrics.replicas >= fix_replicas
    )
    acceptable_by_rollback = ActionType.ROLLBACK_DEPLOY in acceptable_actions and state.version in acceptable_versions
    acceptable_by_restart = ActionType.RESTART_SERVICE in acceptable_actions and state.metrics.restart_count > 0
    acceptable_by_scale = bool(acceptable_replicas) and ActionType.SCALE_UP in acceptable_actions and state.metrics.replicas >= min(acceptable_replicas)
    return fixed_by_rollback or fixed_by_restart or fixed_by_scale or acceptable_by_rollback or acceptable_by_restart or acceptable_by_scale


def _incident_messages(service: str, category: str, current_version: str) -> List[str]:
    if category == "oom_crash":
        return [
            "Worker exited unexpectedly after sustained memory growth",
            "Process supervisor restarted one replica after a fatal runtime event",
            "Requests dropped while the service pool was below healthy capacity",
        ]
    if category == "dependency_fail":
        return [
            "Dependency calls are timing out under normal traffic",
            "Connection attempts are backing up behind an exhausted pool",
            "Read and write operations are stalling upstream request handlers",
        ]
    if category == "bad_deploy":
        return [
            f"Release {current_version} is failing startup health checks on fresh instances",
            f"Bootstrap aborted during {service} initialization after the latest rollout",
            "The previous known-good release remains available for rollback",
        ]
    if category == "memory_leak":
        return [
            "Resident memory is climbing steadily across long-lived workers",
            "The service is trending toward eviction pressure under steady traffic",
            "Capacity pressure dropped slightly after replica turnover, then returned",
        ]
    if category == "config_error":
        return [
            "Runtime configuration validation failed during bootstrap",
            "One or more feature flags are incompatible in this release train",
            "The previous deployment loaded without configuration faults",
        ]
    if category == "db_deadlock":
        return [
            "Transaction lock acquisition is stalling beyond expected thresholds",
            "Long-running writes are blocking user-facing mutations",
            "Blocked sessions are saturating the connection pool",
        ]
    return [
        "Service operating within expected SLO",
        "No recent fatal errors detected",
        "Traffic routed normally",
    ]


def recompute_service_health(states: Dict[str, ServiceState], scenario: IncidentScenario) -> None:
    for service, state in states.items():
        explicit_status = scenario.initial_statuses.get(service, ServiceStatus.HEALTHY)
        if service == scenario.root_cause_service or service in scenario.secondary_root_causes:
            if _service_is_fixed(service, state, scenario):
                state.status = ServiceStatus.HEALTHY
            else:
                state.status = explicit_status
        elif any(states[dep].status != ServiceStatus.HEALTHY for dep in state.dependencies):
            state.status = ServiceStatus.DEGRADED
        elif service in scenario.red_herring_services:
            state.status = ServiceStatus.DEGRADED
        else:
            state.status = ServiceStatus.HEALTHY
        baseline = deepcopy(BASE_METRICS[state.status])
        baseline.restart_count = state.metrics.restart_count
        baseline.replicas = state.metrics.replicas
        state.metrics = baseline


def generate_alerts(states: Dict[str, ServiceState]) -> List[str]:
    alerts: List[str] = []
    for service, state in states.items():
        if state.status == ServiceStatus.DOWN:
            alerts.append(f"SEV-1: {service} is failing health checks and dropping most traffic")
        elif state.status == ServiceStatus.DEGRADED:
            alerts.append(f"SEV-2: {service} latency is elevated and error budgets are burning")
    return alerts


def generate_logs(service: str, states: Dict[str, ServiceState], scenario: IncidentScenario, lines: int) -> List[LogEntry]:
    now = utc_now()
    messages: List[str]
    if service in {scenario.root_cause_service, *scenario.secondary_root_causes.keys()} and _service_is_fixed(service, states[service], scenario):
        messages = [
            "Recent restarts are complete and the error budget burn rate is falling",
            "Health checks are passing across the active replica set",
            "New requests are completing without elevated failure signals",
        ]
    elif service == scenario.root_cause_service:
        messages = _incident_messages(service, scenario.root_cause_category.value, states[service].version)
    elif service in scenario.secondary_root_causes:
        messages = _incident_messages(service, scenario.secondary_root_causes[service].value, states[service].version)
    elif service in scenario.red_herring_services:
        messages = [
            "Background compaction is slower than usual but still completing",
            "Cache miss ratio is elevated, although fallback paths remain available",
            "A maintenance warning is noisy but not conclusively user-impacting",
        ]
    else:
        messages = [
            "Service operating within expected SLO",
            "No recent fatal errors detected",
            "Traffic routed normally",
        ]

    entries: List[LogEntry] = []
    for idx, message in enumerate(messages[: max(1, min(lines, 3))]):
        entries.append(
            LogEntry(
                timestamp=isoformat(now - timedelta(minutes=idx + 1)),
                level="ERROR" if "failed" in message.lower() or "crash" in message.lower() or "not reachable" in message.lower() else "WARN",
                service=service,
                message=message,
            )
        )
    return entries
