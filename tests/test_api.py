from __future__ import annotations

from pathlib import Path
import unittest

from api.server import (
    HTTPException,
    ResetRequest,
    RuntimeBaselineRequest,
    RuntimeBenchmarkRequest,
    RuntimeCompareRequest,
    RuntimeConfig,
    StepRequest,
    compare_session,
    get_benchmark,
    get_benchmark_history,
    get_replay,
    get_tasks,
    list_sessions,
    reset_environment,
    run_runtime_baseline,
    run_runtime_benchmark,
    run_runtime_compare,
    state_environment,
    step_environment,
)
from env.models import Action
from env.models import TaskTier


class ApiContractTests(unittest.TestCase):
    def test_tasks_endpoint_returns_catalog(self) -> None:
        payload = get_tasks()

        self.assertEqual(len(payload), 12)
        first = payload[0]
        self.assertRegex(first["task_id"], r"^(easy|medium|hard)-\d{2}$")
        self.assertRegex(first["name"], r"^(Easy|Medium|Hard) Incident \d{2}$")
        self.assertRegex(first["template_id"], r"^family-\d{2}$")
        self.assertNotIn("auth-service", first["name"])
        self.assertNotIn("oom", first["task_id"])
        self.assertNotIn("oom", first["template_id"])
        self.assertNotIn("bad_deploy", first["description"])
        self.assertEqual(first["service_focus"], [])

    def test_reset_and_state_flow(self) -> None:
        payload = reset_environment(ResetRequest(tier=TaskTier.EASY, task_id="easy-01", seed=2))

        self.assertIn("session_id", payload)
        self.assertIn("observation", payload)
        self.assertEqual(payload["task_id"], "easy-01")
        self.assertIn("unknowns", payload["observation"])
        self.assertIn("validation_status", payload["observation"])
        self.assertIn("trace_spans", payload["observation"])
        self.assertIn("rollout_status", payload["observation"])
        self.assertIn("incident_ticket", payload["observation"])
        self.assertIn("lifecycle_stage", payload["observation"])
        self.assertIn("business_impact", payload["observation"])
        self.assertIn("traffic_status", payload["observation"])
        self.assertIn("queue_status", payload["observation"])
        self.assertIn("feature_flags", payload["observation"])
        self.assertIn("regional_status", payload["observation"])
        self.assertIn("telemetry_warnings", payload["observation"])
        self.assertIn("service_owners", payload["observation"])
        self.assertIn("runbook_hints", payload["observation"])
        self.assertIn("deploy_history", payload["observation"])
        self.assertIn("config_findings", payload["observation"])

        state = state_environment(payload["session_id"])
        self.assertEqual(state["session_id"], payload["session_id"])
        self.assertEqual(state["result"]["scenario_id"], "easy-01")

    def test_benchmark_endpoint_returns_aggregate_report(self) -> None:
        payload = get_benchmark(seeds_per_scenario=2)

        self.assertEqual(payload["scenario_count"], 30)
        self.assertEqual(payload["public_scenario_count"], 24)
        self.assertEqual(payload["holdout_scenario_count"], 6)
        self.assertIn("tier_summaries", payload)
        self.assertEqual(len(payload["tier_summaries"]), 3)
        self.assertIn("family_breakdown", payload)
        self.assertIn("hardest_scenarios", payload)
        self.assertIn("analytics_summary", payload)
        self.assertIn("benchmark_id", payload)

    def test_replay_endpoint_returns_session_history(self) -> None:
        payload = reset_environment(ResetRequest(tier=TaskTier.EASY, task_id="easy-01", seed=1))
        step_environment(
            StepRequest(
                session_id=payload["session_id"],
                action=Action(action_type="ping_service", service="auth-service"),
            )
        )

        replay = get_replay(payload["session_id"])

        self.assertEqual(replay["seed"], 1)
        self.assertEqual(replay["scenario_id"], "easy-01")
        self.assertEqual(replay["result"]["scenario_id"], "easy-01")
        self.assertGreaterEqual(len(replay["replay_steps"]), 2)
        self.assertIn("judge_summary", replay)
        replay_path = Path("/home/ziyan01/VScode/artifacts/replays") / f"{payload['session_id']}.json"
        self.assertTrue(replay_path.exists())

    def test_sessions_and_comparison_endpoints(self) -> None:
        payload = reset_environment(ResetRequest(tier=TaskTier.EASY, task_id="easy-01", seed=0))
        step_environment(
            StepRequest(
                session_id=payload["session_id"],
                action=Action(action_type="ping_service", service="auth-service"),
            )
        )

        sessions = list_sessions()
        self.assertTrue(any(item["session_id"] == payload["session_id"] for item in sessions))

        comparison = compare_session(payload["session_id"])
        self.assertIn("human", comparison)
        self.assertIn("scripted", comparison)
        self.assertEqual(comparison["scenario_id"], "easy-01")

    def test_benchmark_history_endpoint_lists_saved_runs(self) -> None:
        created = get_benchmark(seeds_per_scenario=1)
        history = get_benchmark_history()
        self.assertTrue(any(item["benchmark_id"] == created["benchmark_id"] for item in history))

    def test_step_unknown_session_returns_404(self) -> None:
        with self.assertRaises(HTTPException) as exc:
            step_environment(
                StepRequest(
                    session_id="does-not-exist",
                    action=Action(action_type="ping_service", service="auth-service"),
                )
            )
        self.assertEqual(exc.exception.status_code, 404)

    def test_benchmark_provider_field_defaults_to_mode(self) -> None:
        payload = get_benchmark(seeds_per_scenario=1)
        self.assertEqual(payload["provider"], payload["mode"])

    def test_hidden_task_ids_are_not_accessible_via_api(self) -> None:
        for task_id in ("easy-05", "medium-05", "hard-05"):
            with self.assertRaises(HTTPException) as exc:
                reset_environment(ResetRequest(tier=TaskTier.EASY, task_id=task_id, seed=0))
            self.assertEqual(exc.exception.status_code, 404)

    def test_runtime_baseline_endpoint_supports_scripted_runs(self) -> None:
        payload = run_runtime_baseline(
            RuntimeBaselineRequest(
                tier=TaskTier.EASY,
                task_id="easy-01",
                seed=0,
                runtime=RuntimeConfig(provider="scripted"),
            )
        )
        self.assertEqual(payload["mode"], "scripted")
        self.assertEqual(payload["task_id"], "easy-01")

    def test_runtime_benchmark_endpoint_supports_scripted_runs(self) -> None:
        payload = run_runtime_benchmark(RuntimeBenchmarkRequest(runtime=RuntimeConfig(provider="scripted")))
        self.assertEqual(payload["mode"], "scripted")
        self.assertEqual(payload["scenario_count"], 15)

    def test_runtime_compare_endpoint_returns_human_and_selected(self) -> None:
        payload = reset_environment(ResetRequest(tier=TaskTier.EASY, task_id="easy-01", seed=0))
        comparison = run_runtime_compare(
            RuntimeCompareRequest(
                session_id=payload["session_id"],
                runtime=RuntimeConfig(provider="scripted"),
            )
        )
        self.assertIn("human", comparison)
        self.assertIn("selected", comparison)


if __name__ == "__main__":
    unittest.main()
