from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, Optional

from env.incidents import get_scenario, materialize_seeded_scenario
from env.models import (
    Action,
    ActionType,
    EpisodeResult,
    IncidentScenario,
    Observation,
    Reward,
    RewardBreakdown,
    RootCauseCategory,
    ServiceMetrics,
    ServiceStatus,
    TaskTier,
)
from env.services import build_service_states, generate_alerts, generate_logs, isoformat, recompute_service_health, utc_now

SERVICE_OWNERS = {
    "api-gateway": "edge-platform@company.test",
    "auth-service": "identity-oncall@company.test",
    "user-service": "profile-platform@company.test",
    "payment-service": "payments-oncall@company.test",
    "db-postgres": "storage-primary@company.test",
    "cache-redis": "cache-infra@company.test",
}

RUNBOOK_HINTS = {
    RootCauseCategory.OOM_CRASH: "Runbook: inspect restart churn, memory saturation, and whether a restart or scale-out restores healthy capacity.",
    RootCauseCategory.DEPENDENCY_FAIL: "Runbook: identify the first unhealthy upstream dependency before fixing downstream symptoms.",
    RootCauseCategory.BAD_DEPLOY: "Runbook: compare release history, startup failures, and rollback eligibility before changing runtime capacity.",
    RootCauseCategory.MEMORY_LEAK: "Runbook: verify sustained memory growth, then scale or recycle the leaking service while validating recovery.",
    RootCauseCategory.CONFIG_ERROR: "Runbook: confirm rollout timing, config bundle drift, and safe rollback target.",
    RootCauseCategory.DB_DEADLOCK: "Runbook: check blocked transactions, lock queues, and recovery impact on downstream services.",
}


@dataclass
class RewardFlags:
    ping_bonus_awarded: bool = False
    metrics_bonus_awarded: bool = False
    root_cause_bonus_awarded: bool = False
    fix_bonus_awarded: bool = False
    mitigation_bonus_awarded: bool = False
    diagnosis_bonus_awarded: bool = False


@dataclass
class EpisodeState:
    scenario: IncidentScenario
    services: Dict[str, object]
    step_number: int = 0
    done: bool = False
    action_counter: Counter = field(default_factory=Counter)
    reward_flags: RewardFlags = field(default_factory=RewardFlags)
    reward_history: list[Reward] = field(default_factory=list)
    final_diagnosis: Optional[Action] = None
    discovered_dependencies: dict[str, list[str]] = field(default_factory=dict)
    inspected_actions: dict[str, set[str]] = field(default_factory=dict)
    version_revealed: set[str] = field(default_factory=set)
    recovery_validated: bool = False
    drift_level: int = 0
    deploy_inspections: set[str] = field(default_factory=set)
    trace_inspections: set[str] = field(default_factory=set)
    runbook_checked: set[str] = field(default_factory=set)
    config_checked: set[str] = field(default_factory=set)
    traffic_drained: set[str] = field(default_factory=set)
    failed_over_services: set[str] = field(default_factory=set)
    first_fix_step: Optional[int] = None
    first_mitigation_step: Optional[int] = None


class SREIncidentEnv:
    def __init__(self, tier: TaskTier = TaskTier.EASY, task_id: str | None = None, seed: int = 0):
        self.tier = tier
        self.task_id = task_id
        self.seed = seed
        self._episode: Optional[EpisodeState] = None
        self.reset(tier=tier, task_id=task_id, seed=seed)

    def reset(self, tier: Optional[TaskTier] = None, task_id: str | None = None, seed: Optional[int] = None) -> Observation:
        if tier is not None:
            self.tier = tier
        if task_id is not None:
            self.task_id = task_id
        if seed is not None:
            self.seed = seed
        scenario = materialize_seeded_scenario(get_scenario(self.tier, self.task_id), self.seed)
        self.tier = scenario.tier
        self.task_id = scenario.scenario_id
        services = build_service_states(scenario)
        recompute_service_health(services, scenario)
        self._episode = EpisodeState(scenario=scenario, services=services)
        return self.state()

    def state(self) -> Observation:
        episode = self._require_episode()
        return Observation(
            step_number=episode.step_number,
            timestamp=isoformat(utc_now()),
            services=self._visible_services(),
            active_alerts=generate_alerts(episode.services),
            incident_ticket=self._incident_ticket(),
            lifecycle_stage=self._lifecycle_stage(),
            operator_notes=self._operator_notes(),
            service_owners=self._service_owner_contacts(),
            deploy_history=self._deploy_history(),
            runbook_hints=self._runbook_hints(),
            config_findings=self._config_findings(),
            business_impact=self._business_impact(),
            traffic_status=self._traffic_status(),
            queue_status=self._queue_status(),
            feature_flags=self._feature_flags(),
            regional_status=self._regional_status(),
            telemetry_warnings=self._telemetry_warnings(),
            change_events=self._change_events(),
            rollout_status=self._rollout_status(),
            trace_spans=self._trace_spans(),
            evidence_summary=self._evidence_summary(),
            unknowns=self._unknowns_summary(),
            validation_status=self._validation_status(),
            episode_done=episode.done,
        )

    def step(self, action: Action) -> tuple[Observation, Reward]:
        episode = self._require_episode()
        if episode.done:
            reward = Reward(total=0.0, breakdown=RewardBreakdown(), message="Episode already completed.")
            return self.state_with_result("Episode already completed.", reward, logs=[]), reward

        episode.step_number += 1
        key = self._action_key(action)
        episode.action_counter[key] += 1

        result = "Action executed."
        logs = []
        reward_breakdown = RewardBreakdown()

        if episode.action_counter[key] > 1:
            reward_breakdown.redundant_step_penalty -= 0.05

        if action.action_type == ActionType.PING_SERVICE:
            result = self._handle_ping(action, reward_breakdown)
        elif action.action_type == ActionType.CHECK_METRICS:
            result = self._handle_metrics(action, reward_breakdown)
        elif action.action_type == ActionType.READ_LOGS:
            logs, result = self._handle_logs(action)
        elif action.action_type == ActionType.INSPECT_DEPLOY:
            result = self._handle_inspect_deploy(action, reward_breakdown)
        elif action.action_type == ActionType.QUERY_TRACES:
            result = self._handle_query_traces(action, reward_breakdown)
        elif action.action_type == ActionType.CHECK_RUNBOOK:
            result = self._handle_check_runbook(action)
        elif action.action_type == ActionType.DIFF_CONFIG:
            result = self._handle_diff_config(action, reward_breakdown)
        elif action.action_type == ActionType.DRAIN_TRAFFIC:
            result = self._handle_drain_traffic(action, reward_breakdown)
        elif action.action_type == ActionType.FAILOVER_REGION:
            result = self._handle_failover_region(action, reward_breakdown)
        elif action.action_type == ActionType.CHECK_DEPENDENCIES:
            result = self._handle_dependencies(action)
        elif action.action_type == ActionType.RESTART_SERVICE:
            result = self._handle_restart(action, reward_breakdown)
        elif action.action_type == ActionType.ROLLBACK_DEPLOY:
            result = self._handle_rollback(action, reward_breakdown)
        elif action.action_type == ActionType.SCALE_UP:
            result = self._handle_scale(action, reward_breakdown)
        elif action.action_type == ActionType.SUBMIT_DIAGNOSIS:
            result = self._handle_submit(action, reward_breakdown)
        else:
            reward_breakdown.wrong_action_penalty -= 0.10
            result = "Unsupported action."

        recompute_service_health(episode.services, episode.scenario)
        self._apply_operational_drift()
        if episode.step_number >= episode.scenario.max_steps and not episode.done:
            episode.done = True
            result = f"{result} Max steps reached."

        total = sum(reward_breakdown.model_dump().values())
        total = max(-1.0, min(1.0, total))
        reward = Reward(total=total, breakdown=reward_breakdown, message=result)
        episode.reward_history.append(reward)
        return self.state_with_result(result, reward, logs), reward

    def result(self) -> EpisodeResult:
        episode = self._require_episode()
        total = sum(item.total for item in episode.reward_history)
        final_score = max(0.0, min(1.0, total))
        solved = (
            episode.final_diagnosis is not None
            and episode.final_diagnosis.root_cause_service == episode.scenario.root_cause_service
            and episode.final_diagnosis.root_cause_category == episode.scenario.root_cause_category
            and (episode.reward_flags.fix_bonus_awarded or episode.reward_flags.mitigation_bonus_awarded)
            and episode.recovery_validated
        )
        return EpisodeResult(
            scenario_id=episode.scenario.scenario_id,
            tier=episode.scenario.tier,
            steps_taken=episode.step_number,
            final_score=final_score,
            solved=solved,
            analytics=self._result_analytics(solved),
            reward_history=deepcopy(episode.reward_history),
            final_diagnosis=episode.final_diagnosis,
            grading_notes=self._grading_notes(solved),
        )

    def state_with_result(self, result: str, reward: Reward, logs: list) -> Observation:
        episode = self._require_episode()
        return Observation(
            step_number=episode.step_number,
            timestamp=isoformat(utc_now()),
            services=self._visible_services(),
            active_alerts=generate_alerts(episode.services),
            incident_ticket=self._incident_ticket(),
            lifecycle_stage=self._lifecycle_stage(),
            operator_notes=self._operator_notes(),
            service_owners=self._service_owner_contacts(),
            deploy_history=self._deploy_history(),
            runbook_hints=self._runbook_hints(),
            config_findings=self._config_findings(),
            business_impact=self._business_impact(),
            traffic_status=self._traffic_status(),
            queue_status=self._queue_status(),
            feature_flags=self._feature_flags(),
            regional_status=self._regional_status(),
            telemetry_warnings=self._telemetry_warnings(),
            change_events=self._change_events(),
            rollout_status=self._rollout_status(),
            trace_spans=self._trace_spans(),
            logs=logs,
            action_result=f"{result} Reward {reward.total:+.2f}.",
            evidence_summary=self._evidence_summary(),
            unknowns=self._unknowns_summary(),
            validation_status=self._validation_status(),
            episode_done=episode.done,
        )

    def _handle_ping(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        service = action.service or ""
        if service not in episode.services:
            breakdown.wrong_action_penalty -= 0.10
            return "Unknown service for ping."
        self._record_inspection(service, "ping")
        status = episode.services[service].status.value
        if service == episode.scenario.root_cause_service and not episode.reward_flags.ping_bonus_awarded:
            breakdown.exploration_bonus += 0.10
            episode.reward_flags.ping_bonus_awarded = True
        if status == "healthy":
            if self._can_validate_recovery(service, via="ping"):
                episode.recovery_validated = True
            return f"Ping result for {service}: healthy responses recovered within SLO."
        if status == "down":
            return f"Ping result for {service}: repeated timeouts and connection resets."
        return f"Ping result for {service}: intermittent responses with elevated latency."

    def _handle_metrics(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        service = action.service or ""
        if service not in episode.services:
            breakdown.wrong_action_penalty -= 0.10
            return "Unknown service for metrics."
        self._record_inspection(service, "metrics")
        metrics = episode.services[service].metrics
        if service == episode.scenario.root_cause_service and not episode.reward_flags.metrics_bonus_awarded:
            breakdown.correct_service_identified += 0.20
            episode.reward_flags.metrics_bonus_awarded = True
        if self._can_validate_recovery(service, via="metrics") and episode.services[service].status.value == "healthy":
            episode.recovery_validated = True
        return self._describe_metrics(service, metrics, action.window_seconds or 300)

    def _handle_logs(self, action: Action) -> tuple[list, str]:
        episode = self._require_episode()
        service = action.service or ""
        if service not in episode.services:
            return [], "Unknown service for log read."
        self._record_inspection(service, "logs")
        episode.version_revealed.add(service)
        logs = generate_logs(service, episode.services, episode.scenario, action.lines or 50)
        if self._can_validate_recovery(service, via="logs") and episode.services[service].status.value == "healthy":
            episode.recovery_validated = True
        return logs, f"Fetched {len(logs)} log lines for {service}."

    def _handle_dependencies(self, action: Action) -> str:
        episode = self._require_episode()
        service = action.service or ""
        if service not in episode.services:
            return "Unknown service for dependency check."
        deps = episode.services[service].dependencies
        episode.discovered_dependencies[service] = list(deps)
        self._record_inspection(service, "dependencies")
        if not deps:
            return f"{service} has no dependencies."
        return f"{service} depends on: {', '.join(deps)}."

    def _handle_inspect_deploy(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        service = action.service or episode.scenario.root_cause_service
        if service not in episode.services:
            breakdown.wrong_action_penalty -= 0.10
            return "Unknown service for deploy inspection."
        episode.deploy_inspections.add(service)
        self._record_inspection(service, "deploy")
        if service == episode.scenario.root_cause_service and episode.scenario.root_cause_category in {
            RootCauseCategory.BAD_DEPLOY,
            RootCauseCategory.CONFIG_ERROR,
        }:
            breakdown.exploration_bonus += 0.05
        status = episode.scenario.rollout_status.get(service, "no deploy anomaly surfaced")
        return f"Deploy inspection for {service}: {status}."

    def _handle_query_traces(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        service = action.service or episode.scenario.root_cause_service
        if service not in episode.services:
            breakdown.wrong_action_penalty -= 0.10
            return "Unknown service for trace query."
        episode.trace_inspections.add(service)
        self._record_inspection(service, "traces")
        if service == episode.scenario.root_cause_service:
            breakdown.exploration_bonus += 0.05
        traces = episode.scenario.trace_signals.get(service)
        if traces:
            return f"Trace query for {service}: {traces[0]}"
        return f"Trace query for {service}: no decisive trace anomaly surfaced."

    def _handle_check_runbook(self, action: Action) -> str:
        episode = self._require_episode()
        service = action.service or episode.scenario.root_cause_service
        if service not in episode.services:
            return "Unknown service for runbook lookup."
        episode.runbook_checked.add(service)
        self._record_inspection(service, "runbook")
        category = episode.scenario.root_cause_category if service == episode.scenario.root_cause_service else episode.scenario.secondary_root_causes.get(service, episode.scenario.root_cause_category)
        return RUNBOOK_HINTS[category]

    def _handle_diff_config(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        service = action.service or episode.scenario.root_cause_service
        if service not in episode.services:
            breakdown.wrong_action_penalty -= 0.10
            return "Unknown service for config diff."
        episode.config_checked.add(service)
        self._record_inspection(service, "config")
        if service == episode.scenario.root_cause_service and episode.scenario.root_cause_category == RootCauseCategory.CONFIG_ERROR:
            breakdown.exploration_bonus += 0.05
        findings = episode.scenario.config_signals.get(service)
        if findings:
            return f"Config diff for {service}: {findings[0]}"
        return f"Config diff for {service}: no material configuration drift surfaced."

    def _handle_drain_traffic(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        service = action.service or ""
        if service not in episode.services:
            breakdown.wrong_action_penalty -= 0.10
            return "Unknown service for traffic drain."
        episode.traffic_drained.add(service)
        if service == episode.scenario.root_cause_service:
            if not episode.reward_flags.mitigation_bonus_awarded:
                breakdown.acceptable_fix_applied += 0.15
                episode.reward_flags.mitigation_bonus_awarded = True
                episode.first_mitigation_step = episode.step_number
                episode.recovery_validated = False
            return f"Traffic drained away from {service}; user impact softened while a permanent fix is still needed."
        breakdown.wrong_action_penalty -= 0.05
        return f"Traffic drained away from {service}; limited operational value so far."

    def _handle_failover_region(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        service = action.service or episode.scenario.root_cause_service
        if service not in episode.services:
            breakdown.wrong_action_penalty -= 0.10
            return "Unknown service for regional failover."
        episode.failed_over_services.add(service)
        if service == episode.scenario.root_cause_service:
            if not episode.reward_flags.mitigation_bonus_awarded:
                breakdown.acceptable_fix_applied += 0.15
                episode.reward_flags.mitigation_bonus_awarded = True
                episode.first_mitigation_step = episode.step_number
                episode.recovery_validated = False
            return f"Regional failover initiated for {service}; customer impact eased, but root-cause remediation remains open."
        breakdown.wrong_action_penalty -= 0.05
        return f"Regional failover initiated for {service}; impact reduction is inconclusive."

    def _handle_restart(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        service = action.service or ""
        if service not in episode.services:
            breakdown.wrong_action_penalty -= 0.10
            return "Unknown service for restart."
        state = episode.services[service]
        if state.status == "healthy":
            breakdown.wrong_action_penalty -= 0.10
            state.metrics.restart_count += 1
            return f"Restarted healthy service {service}; no improvement expected."

        state.metrics.restart_count += 1
        if service == episode.scenario.root_cause_service and episode.scenario.correct_fix_action == ActionType.RESTART_SERVICE:
            if not self._has_required_investigation(service):
                return f"Restarted {service}; service may recover, but the fix was applied before sufficient investigation."
            if not episode.reward_flags.fix_bonus_awarded:
                breakdown.correct_fix_applied += 0.30
                episode.reward_flags.fix_bonus_awarded = True
                episode.first_fix_step = episode.step_number
                episode.recovery_validated = False
            return f"Restarted {service}; service recovered."
        if service == episode.scenario.root_cause_service and ActionType.RESTART_SERVICE in episode.scenario.acceptable_fix_actions:
            if not self._has_required_investigation(service):
                return f"Restarted {service}; mitigation may help, but it was applied before sufficient investigation."
            if not episode.reward_flags.mitigation_bonus_awarded:
                breakdown.acceptable_fix_applied += 0.20
                episode.reward_flags.mitigation_bonus_awarded = True
                episode.first_mitigation_step = episode.step_number
                episode.recovery_validated = False
            return f"Restarted {service}; service stabilized, but a more permanent remediation may still be warranted."
        if service in episode.scenario.secondary_root_causes and episode.scenario.secondary_fix_actions.get(service) == ActionType.RESTART_SERVICE:
            return f"Restarted {service}; a secondary fault improved, but the primary incident remains."

        breakdown.wrong_action_penalty -= 0.15
        return f"Restarted {service}; issue persists because this is a downstream symptom."

    def _handle_rollback(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        service = action.service or ""
        if service not in episode.services:
            breakdown.wrong_action_penalty -= 0.10
            return "Unknown service for rollback."
        target_version = action.target_version
        if target_version is None:
            breakdown.wrong_action_penalty -= 0.10
            return "Rollback requested without a target version."
        episode.services[service].version = target_version
        if (
            service == episode.scenario.root_cause_service
            and episode.scenario.correct_fix_action == ActionType.ROLLBACK_DEPLOY
            and target_version == episode.scenario.correct_fix_version
        ):
            if not self._has_required_investigation(service):
                return f"Rolled back {service} to {target_version}; change applied before the root cause was fully investigated."
            if not episode.reward_flags.fix_bonus_awarded:
                breakdown.correct_fix_applied += 0.30
                episode.reward_flags.fix_bonus_awarded = True
                episode.first_fix_step = episode.step_number
                episode.recovery_validated = False
            return f"Rolled back {service} to {target_version}; deploy issue cleared."
        if (
            service == episode.scenario.root_cause_service
            and ActionType.ROLLBACK_DEPLOY in episode.scenario.acceptable_fix_actions
            and target_version in episode.scenario.acceptable_fix_versions
        ):
            if not self._has_required_investigation(service):
                return f"Rolled back {service} to {target_version}; mitigation was applied before the root cause was sufficiently investigated."
            if not episode.reward_flags.mitigation_bonus_awarded:
                breakdown.acceptable_fix_applied += 0.20
                episode.reward_flags.mitigation_bonus_awarded = True
                episode.first_mitigation_step = episode.step_number
                episode.recovery_validated = False
            return f"Rolled back {service} to {target_version}; service stabilized with an acceptable mitigation."
        if (
            service in episode.scenario.secondary_root_causes
            and episode.scenario.secondary_fix_actions.get(service) == ActionType.ROLLBACK_DEPLOY
            and target_version == episode.scenario.secondary_fix_versions.get(service)
        ):
            return f"Rolled back {service} to {target_version}; a secondary fault improved, but the primary incident remains."
        breakdown.wrong_action_penalty -= 0.15
        return f"Rolled back {service} to {target_version}; no root-cause improvement."

    def _handle_scale(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        service = action.service or ""
        if service not in episode.services:
            breakdown.wrong_action_penalty -= 0.10
            return "Unknown service for scale up."
        target_replicas = action.replicas
        if target_replicas is None:
            target_replicas = episode.services[service].metrics.replicas + 1
        if target_replicas <= episode.services[service].metrics.replicas:
            breakdown.wrong_action_penalty -= 0.10
            return (
                f"Scale up requested for {service} to {target_replicas} replicas, "
                "but the target is not higher than the current replica count."
            )
        episode.services[service].metrics.replicas = target_replicas
        if service == episode.scenario.root_cause_service and episode.scenario.root_cause_category in {
            RootCauseCategory.OOM_CRASH,
            RootCauseCategory.MEMORY_LEAK,
        }:
            if (
                episode.scenario.correct_fix_action == ActionType.SCALE_UP
                and episode.scenario.correct_fix_replicas is not None
                and episode.services[service].metrics.replicas >= episode.scenario.correct_fix_replicas
            ):
                if not self._has_required_investigation(service):
                    return f"Scaled {service} to {episode.services[service].metrics.replicas} replicas, but the change was made before enough evidence was gathered."
                if not episode.reward_flags.fix_bonus_awarded:
                    breakdown.correct_fix_applied += 0.30
                    episode.reward_flags.fix_bonus_awarded = True
                    episode.first_fix_step = episode.step_number
                    episode.recovery_validated = False
                return f"Scaled {service} to {episode.services[service].metrics.replicas} replicas; service stabilized."
            if (
                ActionType.SCALE_UP in episode.scenario.acceptable_fix_actions
                and episode.scenario.acceptable_fix_replicas
                and episode.services[service].metrics.replicas >= min(episode.scenario.acceptable_fix_replicas)
            ):
                if not self._has_required_investigation(service):
                    return f"Scaled {service} to {episode.services[service].metrics.replicas} replicas, but the change was made before enough evidence was gathered."
                if not episode.reward_flags.mitigation_bonus_awarded:
                    breakdown.acceptable_fix_applied += 0.20
                    episode.reward_flags.mitigation_bonus_awarded = True
                    episode.first_mitigation_step = episode.step_number
                    episode.recovery_validated = False
                return f"Scaled {service} to {episode.services[service].metrics.replicas} replicas; the incident is mitigated even if deeper remediation may still be needed."
            breakdown.wrong_action_penalty -= 0.15
            return f"Scaled {service}, but the root issue still needs a corrective fix."
        if (
            service in episode.scenario.secondary_root_causes
            and episode.scenario.secondary_fix_actions.get(service) == ActionType.SCALE_UP
            and episode.scenario.secondary_fix_replicas.get(service) is not None
            and episode.services[service].metrics.replicas >= episode.scenario.secondary_fix_replicas[service]
        ):
            return (
                f"Scaled {service} to {episode.services[service].metrics.replicas} replicas; "
                "a secondary fault improved, but the primary incident remains."
            )
        breakdown.wrong_action_penalty -= 0.10
        return f"Scaled {service}; capacity increased but the incident remains."

    def _handle_submit(self, action: Action, breakdown: RewardBreakdown) -> str:
        episode = self._require_episode()
        correct_service = action.root_cause_service == episode.scenario.root_cause_service
        correct_category = action.root_cause_category == episode.scenario.root_cause_category
        explanation_present = bool(action.fix_description and action.fix_description.strip())

        if correct_service and correct_category and episode.reward_flags.fix_bonus_awarded and not episode.recovery_validated:
            breakdown.wrong_action_penalty -= 0.10
            if episode.scenario.tier == TaskTier.HARD:
                return "Diagnosis withheld until recovery is validated with an explicit ping against the repaired service."
            return "Diagnosis withheld until recovery is validated with an explicit check."

        episode.done = True
        episode.final_diagnosis = action

        if correct_category and not episode.reward_flags.root_cause_bonus_awarded:
            breakdown.correct_root_cause += 0.30
            episode.reward_flags.root_cause_bonus_awarded = True
        if explanation_present and correct_service and correct_category and not episode.reward_flags.diagnosis_bonus_awarded:
            breakdown.correct_diagnosis_text += 0.10
            episode.reward_flags.diagnosis_bonus_awarded = True
        if not (correct_service and correct_category):
            breakdown.wrong_action_penalty -= 0.20
            return "Submitted incorrect diagnosis."
        return "Submitted correct diagnosis."

    def _action_key(self, action: Action) -> str:
        return "|".join(
            [
                action.action_type.value,
                action.service or "",
                action.target_version or "",
                action.root_cause_service or "",
                action.root_cause_category.value if action.root_cause_category else "",
            ]
        )

    def _require_episode(self) -> EpisodeState:
        if self._episode is None:
            raise RuntimeError("Environment not initialized")
        return self._episode

    def _record_inspection(self, service: str, inspection_type: str) -> None:
        episode = self._require_episode()
        episode.inspected_actions.setdefault(service, set()).add(inspection_type)

    def _has_required_investigation(self, service: str) -> bool:
        episode = self._require_episode()
        actions = episode.inspected_actions.get(service, set())
        direct_checks = {"ping", "metrics", "logs"} & actions
        return len(actions) >= 2 and bool(direct_checks)

    def _can_validate_recovery(self, service: str, via: str) -> bool:
        episode = self._require_episode()
        if service != episode.scenario.root_cause_service or not (
            episode.reward_flags.fix_bonus_awarded or episode.reward_flags.mitigation_bonus_awarded
        ):
            return False
        if episode.scenario.tier == TaskTier.HARD:
            return via == "ping"
        return via in {"ping", "metrics", "logs"}

    def _visible_services(self) -> Dict[str, object]:
        episode = self._require_episode()
        visible = deepcopy(episode.services)
        for service, state in visible.items():
            inspections = episode.inspected_actions.get(service, set())
            if service not in episode.version_revealed:
                state.version = "unknown"
            state.dependencies = list(episode.discovered_dependencies.get(service, []))
            if "metrics" not in inspections:
                state.metrics = self._masked_metrics(state.status.value, state.metrics.replicas, state.metrics.restart_count)
            if not inspections:
                state.status = ServiceStatus.HEALTHY if state.status == ServiceStatus.HEALTHY else ServiceStatus.DEGRADED
        return visible

    def _masked_metrics(self, status: str, replicas: int, restart_count: int) -> ServiceMetrics:
        if status == "healthy":
            return ServiceMetrics(
                cpu_percent=34.0,
                memory_percent=49.0,
                error_rate=0.02,
                latency_ms=92.0,
                restart_count=restart_count,
                replicas=replicas,
            )
        if status == "down":
            return ServiceMetrics(
                cpu_percent=67.0,
                memory_percent=71.0,
                error_rate=0.19,
                latency_ms=780.0,
                restart_count=restart_count,
                replicas=replicas,
            )
        return ServiceMetrics(
            cpu_percent=63.0,
            memory_percent=68.0,
            error_rate=0.14,
            latency_ms=460.0,
            restart_count=restart_count,
            replicas=replicas,
        )

    def _describe_metrics(self, service: str, metrics, window_seconds: int) -> str:
        cpu_band = "low" if metrics.cpu_percent < 40 else "elevated" if metrics.cpu_percent < 80 else "critical"
        memory_band = "stable" if metrics.memory_percent < 55 else "rising" if metrics.memory_percent < 80 else "near saturation"
        error_band = "minimal" if metrics.error_rate < 0.03 else "elevated" if metrics.error_rate < 0.2 else "severe"
        latency_band = "within SLO" if metrics.latency_ms < 140 else "degraded" if metrics.latency_ms < 800 else "severely degraded"
        return (
            f"{service} metrics over {window_seconds}s: cpu={cpu_band}, memory={memory_band}, "
            f"errors={error_band}, latency={latency_band}."
        )

    def _apply_operational_drift(self) -> None:
        episode = self._require_episode()
        if episode.reward_flags.fix_bonus_awarded or episode.reward_flags.mitigation_bonus_awarded:
            episode.drift_level = 0
            return
        next_level = min(3, episode.step_number // 3)
        if next_level <= episode.drift_level:
            return
        episode.drift_level = next_level
        for service in ("api-gateway", "user-service", "auth-service"):
            if service in episode.services and service not in {
                episode.scenario.root_cause_service,
                *episode.scenario.secondary_root_causes.keys(),
            }:
                if episode.services[service].status.value == "healthy":
                    episode.services[service].status = episode.services[service].status.DEGRADED
                    episode.services[service].metrics = self._drift_metrics(
                        "degraded",
                        episode.services[service].metrics.replicas,
                        episode.services[service].metrics.restart_count,
                    )
                    break
                if next_level >= 3 and episode.services[service].status.value == "degraded":
                    episode.services[service].status = episode.services[service].status.DOWN
                    episode.services[service].metrics = self._drift_metrics(
                        "down",
                        episode.services[service].metrics.replicas,
                        episode.services[service].metrics.restart_count,
                    )
                    break

    def _drift_metrics(self, status: str, replicas: int, restart_count: int) -> ServiceMetrics:
        if status == "down":
            return ServiceMetrics(
                cpu_percent=12.0,
                memory_percent=18.0,
                error_rate=0.92,
                latency_ms=3200.0,
                restart_count=restart_count,
                replicas=replicas,
            )
        return ServiceMetrics(
            cpu_percent=79.0,
            memory_percent=83.0,
            error_rate=0.28,
            latency_ms=690.0,
            restart_count=restart_count,
            replicas=replicas,
        )

    def _evidence_summary(self) -> list[str]:
        episode = self._require_episode()
        lines: list[str] = []
        for service in sorted(episode.inspected_actions):
            actions = ", ".join(sorted(episode.inspected_actions[service]))
            lines.append(f"{service}: inspected via {actions}")
        if episode.discovered_dependencies:
            lines.append(f"dependency maps discovered for {len(episode.discovered_dependencies)} service(s)")
        if episode.version_revealed:
            lines.append(f"versions revealed for {len(episode.version_revealed)} service(s)")
        if episode.deploy_inspections:
            lines.append(f"deploy history inspected for {len(episode.deploy_inspections)} service(s)")
        if episode.config_checked:
            lines.append(f"config diffs reviewed for {len(episode.config_checked)} service(s)")
        if episode.trace_inspections:
            lines.append(f"trace queries run for {len(episode.trace_inspections)} service(s)")
        if episode.reward_flags.fix_bonus_awarded:
            lines.append("candidate fix applied to the primary root cause")
        if episode.reward_flags.mitigation_bonus_awarded:
            lines.append("acceptable mitigation applied to the primary root cause")
        return lines

    def _change_events(self) -> list[str]:
        episode = self._require_episode()
        recent_events: list[str] = []
        for service, events in episode.scenario.change_events.items():
            for event in events:
                recent_events.append(f"{service}: {event}")
        recent_events.sort(reverse=True)
        return recent_events[:6]

    def _rollout_status(self) -> list[str]:
        episode = self._require_episode()
        if episode.scenario.rollout_status:
            return [f"{service}: {status}" for service, status in episode.scenario.rollout_status.items()]
        root = episode.scenario.root_cause_service
        if episode.scenario.root_cause_category in {RootCauseCategory.BAD_DEPLOY, RootCauseCategory.CONFIG_ERROR}:
            return [f"{root}: recent rollout remains the leading operational suspect"]
        return [f"{root}: no active rollout flag, incident likely tied to runtime behavior"]

    def _trace_spans(self) -> list[str]:
        episode = self._require_episode()
        visible_services = {
            service
            for service in episode.services
            if service in episode.inspected_actions or service == episode.scenario.root_cause_service
        }
        traces: list[str] = []
        for service, signals in episode.scenario.trace_signals.items():
            if service in visible_services or len(episode.inspected_actions) >= 2:
                traces.extend(signals[:2])
        if traces:
            return traces[:6]
        root = episode.scenario.root_cause_service
        if root in visible_services:
            return [f"trace {root}-fallback: request path concentrates failure symptoms around {root}"]
        return ["Trace samples unlock as you inspect implicated services and compare request paths."]

    def _grading_notes(self, solved: bool) -> list[str]:
        episode = self._require_episode()
        analytics = self._result_analytics(solved)
        notes: list[str] = []
        if episode.reward_flags.fix_bonus_awarded:
            notes.append("Primary fix matched the expected remediation path.")
        elif episode.reward_flags.mitigation_bonus_awarded:
            notes.append("An acceptable mitigation restored the primary incident, even though it differed from the canonical remediation.")
        else:
            notes.append("Primary fix credit was never earned.")
        if episode.recovery_validated:
            notes.append("Recovery was explicitly validated before the episode ended.")
        else:
            notes.append("Recovery validation was missing or incomplete.")
        if episode.final_diagnosis is None:
            notes.append("No final diagnosis was submitted.")
        elif solved:
            notes.append("Diagnosis matched the true root cause and category.")
        else:
            notes.append("Final diagnosis did not satisfy the true root cause requirements.")
        notes.append(
            "Analytics: "
            f"mitigation_speed={analytics['mitigation_speed']:.2f} "
            f"evidence_quality={analytics['evidence_quality']:.2f} "
            f"blast_radius={analytics['blast_radius_control']:.2f} "
            f"recovery_certainty={analytics['recovery_certainty']:.2f} "
            f"action_efficiency={analytics['action_efficiency']:.2f}"
        )
        return notes

    def _unknowns_summary(self) -> list[str]:
        episode = self._require_episode()
        unknowns: list[str] = []
        hidden_versions = [service for service in episode.services if service not in episode.version_revealed]
        hidden_dependencies = [service for service in episode.services if service not in episode.discovered_dependencies]
        if hidden_versions:
            unknowns.append(f"versions still hidden for {', '.join(hidden_versions[:3])}" + ("..." if len(hidden_versions) > 3 else ""))
        if hidden_dependencies:
            unknowns.append(f"dependencies still hidden for {', '.join(hidden_dependencies[:3])}" + ("..." if len(hidden_dependencies) > 3 else ""))
        uninspected = [service for service in episode.services if service not in episode.inspected_actions]
        if uninspected:
            unknowns.append(f"no direct investigation yet for {', '.join(uninspected[:3])}" + ("..." if len(uninspected) > 3 else ""))
        if episode.scenario.root_cause_category in {RootCauseCategory.BAD_DEPLOY, RootCauseCategory.CONFIG_ERROR} and episode.scenario.root_cause_service not in episode.deploy_inspections:
            unknowns.append("deploy history on the likely fault domain remains uninspected")
        if episode.scenario.root_cause_service not in episode.trace_inspections:
            unknowns.append("request-path trace evidence for the primary symptom path remains incomplete")
        return unknowns

    def _validation_status(self) -> str:
        episode = self._require_episode()
        if not (episode.reward_flags.fix_bonus_awarded or episode.reward_flags.mitigation_bonus_awarded):
            return "No primary fix has been credited yet."
        if episode.recovery_validated:
            return "Recovery validated."
        if episode.scenario.tier == TaskTier.HARD:
            return "Recovery not validated. Hard mode requires ping_service on the repaired root service."
        return "Recovery not validated. Use an explicit check on the repaired root service before diagnosing."

    def _lifecycle_stage(self) -> str:
        episode = self._require_episode()
        if episode.final_diagnosis is not None and episode.recovery_validated:
            return "closed"
        if episode.reward_flags.fix_bonus_awarded and episode.recovery_validated:
            return "validated"
        if episode.reward_flags.fix_bonus_awarded:
            return "permanent_fix_applied"
        if episode.reward_flags.mitigation_bonus_awarded:
            return "mitigated"
        if episode.inspected_actions:
            return "investigating"
        return "triage"

    def _config_findings(self) -> list[str]:
        episode = self._require_episode()
        findings: list[str] = []
        for service in sorted(episode.config_checked):
            for line in episode.scenario.config_signals.get(service, [])[:2]:
                findings.append(f"{service}: {line}")
        if not findings and episode.scenario.root_cause_category == RootCauseCategory.CONFIG_ERROR:
            findings.append("Config drift remains possible, but no explicit diff has been requested yet.")
        return findings[:6]

    def _business_impact(self) -> list[str]:
        episode = self._require_episode()
        unhealthy = [service for service, state in episode.services.items() if state.status != ServiceStatus.HEALTHY]
        checkout_impacted = "payment-service" in unhealthy or "api-gateway" in unhealthy
        auth_impacted = "auth-service" in unhealthy or "api-gateway" in unhealthy
        regional_blast = "regional" if episode.failed_over_services else "single-region concentrated"
        lines = [
            f"Customer-visible services impacted: {len(unhealthy)}",
            f"Auth success rate estimate: {'82%' if auth_impacted else '99%'}",
            f"Checkout completion estimate: {'61%' if checkout_impacted else '97%'}",
            f"Approximate revenue impact per 15m: {'high' if checkout_impacted else 'low'}",
            f"Blast radius estimate: {regional_blast}",
        ]
        return lines

    def _traffic_status(self) -> list[str]:
        episode = self._require_episode()
        lines: list[str] = []
        for service in sorted(episode.traffic_drained):
            lines.append(f"{service}: traffic drain active; local load reduced while remediation continues")
        for service in sorted(episode.failed_over_services):
            lines.append(f"{service}: regional failover active; user traffic served from backup capacity")
        if not lines:
            lines.append("No emergency traffic controls are active.")
        return lines

    def _queue_status(self) -> list[str]:
        episode = self._require_episode()
        root = episode.scenario.root_cause_service
        queue_depth = "elevated" if episode.services[root].status != ServiceStatus.HEALTHY else "draining"
        lines = [f"{root}: work queue backlog is {queue_depth}."]
        if "payment-service" in episode.services:
            lines.append(
                "payment-service: checkout job queue "
                + ("growing under retry load." if episode.services["payment-service"].status != ServiceStatus.HEALTHY else "is near steady-state.")
            )
        return lines

    def _feature_flags(self) -> list[str]:
        episode = self._require_episode()
        lines: list[str] = []
        if episode.scenario.root_cause_category in {RootCauseCategory.BAD_DEPLOY, RootCauseCategory.CONFIG_ERROR}:
            lines.append(f"{episode.scenario.root_cause_service}: release-related feature gate changed during the incident window.")
        if episode.scenario.root_cause_category == RootCauseCategory.CONFIG_ERROR:
            lines.append("Feature flag risk: policy rollout and config bundle may be out of sync.")
        if not lines:
            lines.append("No feature flag drift is confirmed yet.")
        return lines

    def _regional_status(self) -> list[str]:
        episode = self._require_episode()
        if episode.failed_over_services:
            return [f"{service}: backup region serving traffic while primary remediation continues." for service in sorted(episode.failed_over_services)]
        if episode.traffic_drained:
            return ["Traffic remains pinned to the primary region, but partial drains are active on affected services."]
        return ["Primary region remains active. No cross-region failover is currently enabled."]

    def _telemetry_warnings(self) -> list[str]:
        episode = self._require_episode()
        warnings: list[str] = []
        if episode.scenario.root_cause_service not in episode.trace_inspections:
            warnings.append("Distributed traces may be incomplete until the likely symptom path is queried directly.")
        if episode.scenario.root_cause_category in {RootCauseCategory.BAD_DEPLOY, RootCauseCategory.CONFIG_ERROR} and episode.scenario.root_cause_service not in episode.deploy_inspections:
            warnings.append("Deployment dashboard data is stale relative to rollout state until an explicit deploy inspection is run.")
        if not warnings:
            warnings.append("Primary telemetry blind spots have been reduced for the current incident.")
        return warnings

    def _incident_ticket(self) -> str:
        episode = self._require_episode()
        return (
            f"INC-{episode.scenario.tier.value[:1].upper()}{episode.scenario.seed:02d}-{episode.scenario.scenario_id[-2:]} "
            f"| primary symptom path through {episode.scenario.root_cause_service}"
        )

    def _operator_notes(self) -> list[str]:
        episode = self._require_episode()
        impacted = [service for service, state in episode.services.items() if state.status != ServiceStatus.HEALTHY]
        notes = [
            f"Operator note: customer-facing impact currently spans {', '.join(impacted[:3])}" + ("..." if len(impacted) > 3 else ""),
            "Operator note: prioritize evidence gathering before broad remediation on healthy services.",
        ]
        if episode.scenario.secondary_root_causes:
            notes.append("Operator note: concurrent noise is present; separate the primary blocker from secondary faults.")
        return notes

    def _service_owner_contacts(self) -> list[str]:
        episode = self._require_episode()
        impacted = [service for service, state in episode.services.items() if state.status != ServiceStatus.HEALTHY]
        return [f"{service}: {SERVICE_OWNERS[service]}" for service in impacted[:4]]

    def _deploy_history(self) -> list[str]:
        episode = self._require_episode()
        lines: list[str] = []
        for service in sorted(episode.deploy_inspections):
            status = episode.scenario.rollout_status.get(service, "deploy history reviewed; no rollout blocker confirmed")
            lines.append(f"{service}: deploy inspection -> {status}")
        for service, events in episode.scenario.change_events.items():
            for event in events[:2]:
                lines.append(f"{service}: {event}")
        return lines[:6]

    def _runbook_hints(self) -> list[str]:
        episode = self._require_episode()
        hints = [RUNBOOK_HINTS[episode.scenario.root_cause_category]]
        for category in episode.scenario.secondary_root_causes.values():
            hints.append(RUNBOOK_HINTS[category])
        return hints[:3]

    def _result_analytics(self, solved: bool) -> dict[str, float]:
        episode = self._require_episode()
        first_intervention_step = episode.first_fix_step or episode.first_mitigation_step or episode.step_number or episode.scenario.max_steps
        mitigation_speed = max(0.0, min(1.0, 1 - ((first_intervention_step - 1) / episode.scenario.max_steps)))
        investigated_services = len(episode.inspected_actions)
        evidence_quality = min(
            1.0,
            (
                investigated_services * 0.15
                + len(episode.discovered_dependencies) * 0.15
                + len(episode.deploy_inspections) * 0.1
                + len(episode.trace_inspections) * 0.1
                + len(episode.config_checked) * 0.1
            ),
        )
        blast_radius_penalties = 0.15 * sum(1 for reward in episode.reward_history if reward.breakdown.wrong_action_penalty < 0)
        if episode.drift_level:
            blast_radius_penalties += 0.1 * episode.drift_level
        blast_radius_control = max(0.0, 1.0 - blast_radius_penalties)
        recovery_certainty = 1.0 if episode.recovery_validated else 0.35 if (episode.reward_flags.fix_bonus_awarded or episode.reward_flags.mitigation_bonus_awarded) else 0.0
        action_efficiency = max(0.0, 1 - (max(0, episode.step_number - max(3, investigated_services + 2)) / episode.scenario.max_steps))
        if solved:
            action_efficiency = min(1.0, action_efficiency + 0.1)
        return {
            "mitigation_speed": round(mitigation_speed, 3),
            "evidence_quality": round(evidence_quality, 3),
            "blast_radius_control": round(blast_radius_control, 3),
            "recovery_certainty": round(recovery_certainty, 3),
            "action_efficiency": round(action_efficiency, 3),
        }
