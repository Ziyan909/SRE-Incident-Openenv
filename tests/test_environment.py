from __future__ import annotations

import unittest

from env.environment import SREIncidentEnv
from env.models import Action, TaskTier


class EnvironmentBehaviorTests(unittest.TestCase):
    def test_initial_observation_hides_versions_and_dependencies(self) -> None:
        env = SREIncidentEnv(tier=TaskTier.MEDIUM, task_id="medium-db-cascade")

        observation = env.state()

        self.assertTrue(all(service.version == "unknown" for service in observation.services.values()))
        self.assertTrue(all(service.dependencies == [] for service in observation.services.values()))
        self.assertGreater(len(observation.change_events), 0)
        self.assertGreater(len(observation.trace_spans), 0)
        self.assertGreater(len(observation.rollout_status), 0)

    def test_check_dependencies_reveals_only_target_service_dependencies(self) -> None:
        env = SREIncidentEnv(tier=TaskTier.MEDIUM, task_id="medium-db-cascade")

        observation, _reward = env.step(Action(action_type="check_dependencies", service="user-service"))

        self.assertEqual(observation.services["user-service"].dependencies, ["db-postgres", "cache-redis"])
        self.assertEqual(observation.services["payment-service"].dependencies, [])

    def test_fix_credit_requires_investigation(self) -> None:
        env = SREIncidentEnv(tier=TaskTier.MEDIUM, task_id="medium-db-cascade")

        _observation, reward = env.step(Action(action_type="restart_service", service="db-postgres"))

        self.assertEqual(reward.total, 0.0)
        self.assertFalse(env.result().solved)
        self.assertEqual(env.state().services["db-postgres"].status.value, "degraded")

    def test_hard_mode_requires_ping_validation(self) -> None:
        env = SREIncidentEnv(tier=TaskTier.HARD, task_id="hard-payment-red-herrings")

        env.step(Action(action_type="read_logs", service="payment-service", lines=3))
        env.step(Action(action_type="check_metrics", service="payment-service"))
        env.step(Action(action_type="rollback_deploy", service="payment-service", target_version="v5.4.1"))
        env.step(Action(action_type="check_metrics", service="payment-service"))
        observation, reward = env.step(
            Action(
                action_type="submit_diagnosis",
                root_cause_service="payment-service",
                root_cause_category="bad_deploy",
                fix_description="Rolled back the unhealthy deploy.",
            )
        )

        self.assertIn("explicit ping", observation.action_result)
        self.assertLess(reward.total, 0.0)
        self.assertFalse(env.result().solved)

        env.step(Action(action_type="ping_service", service="payment-service"))
        env.step(
            Action(
                action_type="submit_diagnosis",
                root_cause_service="payment-service",
                root_cause_category="bad_deploy",
                fix_description="Rolled back the unhealthy deploy.",
            )
        )
        self.assertTrue(env.result().solved)

    def test_alternative_mitigation_can_still_solve_when_validated(self) -> None:
        env = SREIncidentEnv(tier=TaskTier.EASY, task_id="easy-auth-oom")

        env.step(Action(action_type="ping_service", service="auth-service"))
        env.step(Action(action_type="check_metrics", service="auth-service"))
        env.step(Action(action_type="scale_up", service="auth-service", replicas=3))
        env.step(Action(action_type="ping_service", service="auth-service"))
        _observation, reward = env.step(
            Action(
                action_type="submit_diagnosis",
                root_cause_service="auth-service",
                root_cause_category="oom_crash",
                fix_description="Scaled out auth-service to stabilize memory pressure and restore availability.",
            )
        )

        self.assertGreaterEqual(reward.total, 0.1)
        self.assertTrue(env.result().solved)

    def test_submit_requires_validation_after_mitigation(self) -> None:
        env = SREIncidentEnv(tier=TaskTier.EASY, task_id="easy-auth-oom")

        env.step(Action(action_type="ping_service", service="auth-service"))
        env.step(Action(action_type="check_metrics", service="auth-service"))
        observation, reward = env.step(Action(action_type="scale_up", service="auth-service", replicas=3))
        self.assertIn("mitigated", observation.action_result)

        observation, reward = env.step(
            Action(
                action_type="submit_diagnosis",
                root_cause_service="auth-service",
                root_cause_category="oom_crash",
                fix_description="Scaled out auth-service to mitigate memory pressure.",
            )
        )

        self.assertIn("validated", observation.action_result)
        self.assertLess(reward.total, 0.0)
        self.assertFalse(observation.episode_done)

    def test_wrong_service_with_right_category_does_not_earn_positive_diagnosis_score(self) -> None:
        env = SREIncidentEnv(tier=TaskTier.EASY, task_id="easy-auth-oom")

        _observation, reward = env.step(
            Action(
                action_type="submit_diagnosis",
                root_cause_service="payment-service",
                root_cause_category="oom_crash",
                fix_description="Incorrectly blamed payment-service.",
            )
        )

        self.assertLessEqual(reward.total, 0.0)

    def test_same_seed_produces_same_variant(self) -> None:
        first = SREIncidentEnv(tier=TaskTier.EASY, task_id="easy-01", seed=4).state()
        second = SREIncidentEnv(tier=TaskTier.EASY, task_id="easy-01", seed=4).state()

        self.assertEqual(first.change_events, second.change_events)
        self.assertEqual(first.rollout_status, second.rollout_status)
        self.assertEqual(first.trace_spans, second.trace_spans)

    def test_new_operational_actions_surface_context(self) -> None:
        env = SREIncidentEnv(tier=TaskTier.EASY, task_id="easy-gateway-config-flags")

        observation, _reward = env.step(Action(action_type="inspect_deploy", service="api-gateway"))
        self.assertTrue(any("rollout" in line or "deploy" in line for line in observation.deploy_history))

        observation, _reward = env.step(Action(action_type="diff_config", service="api-gateway"))
        self.assertGreater(len(observation.config_findings), 0)

        observation, _reward = env.step(Action(action_type="check_runbook", service="api-gateway"))
        self.assertGreater(len(observation.runbook_hints), 0)
        self.assertIn(observation.lifecycle_stage, {"investigating", "triage"})
        self.assertGreater(len(observation.feature_flags), 0)
        self.assertGreater(len(observation.telemetry_warnings), 0)

    def test_business_impact_and_traffic_controls_are_reported(self) -> None:
        env = SREIncidentEnv(tier=TaskTier.EASY, task_id="easy-auth-oom")

        observation = env.state()
        self.assertGreater(len(observation.business_impact), 0)
        self.assertGreater(len(observation.traffic_status), 0)
        self.assertGreater(len(observation.queue_status), 0)
        self.assertGreater(len(observation.regional_status), 0)

        observation, _reward = env.step(Action(action_type="drain_traffic", service="auth-service"))
        self.assertIn("mitigated", observation.lifecycle_stage)
        self.assertTrue(any("traffic drain" in line for line in observation.traffic_status))

    def test_result_analytics_are_exposed(self) -> None:
        env = SREIncidentEnv(tier=TaskTier.EASY, task_id="easy-auth-oom")

        env.step(Action(action_type="ping_service", service="auth-service"))
        env.step(Action(action_type="check_metrics", service="auth-service"))
        env.step(Action(action_type="restart_service", service="auth-service"))
        env.step(Action(action_type="ping_service", service="auth-service"))
        env.step(
            Action(
                action_type="submit_diagnosis",
                root_cause_service="auth-service",
                root_cause_category="oom_crash",
                fix_description="Restarted auth-service after confirming the failure mode.",
            )
        )
        analytics = env.result().analytics
        self.assertIn("mitigation_speed", analytics)
        self.assertIn("evidence_quality", analytics)
        self.assertGreaterEqual(analytics["recovery_certainty"], 1.0)


if __name__ == "__main__":
    unittest.main()
