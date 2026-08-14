"""Tests for the Phase 0 cross-domain trajectory oracle."""

from __future__ import annotations

import copy
import re
import unittest

from output.harness.phase0_episode_benchmark import (
    evaluate_specimen,
    load_fixture,
    run,
    validate_fixture,
)


class Phase0EpisodeBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run(load_fixture())

    def setUp(self) -> None:
        self.fixture = load_fixture()

    def test_fixture_is_a_valid_two_domain_contract(self) -> None:
        validate_fixture(self.fixture)

        self.assertEqual(
            [domain["domain_id"] for domain in self.fixture["domains"]],
            ["gestion-tickets", "sql"],
        )
        self.assertEqual(self.fixture["status"], "implementation-connected-phase0")

    def test_expected_contract_passes_without_claiming_future_implementation(self) -> None:
        report = self.report

        self.assertTrue(report["benchmark_ready"])
        self.assertTrue(report["latency_gate_active"])
        self.assertEqual(
            report["latency_gate_scope"], "deterministic_direct_episode_planning"
        )
        for domain in report["domains"]:
            expected = domain["evaluations"]["episodic_contract"]
            self.assertTrue(expected["passed"])
            self.assertEqual(expected["specimen_kind"], "expected-output-contract")
            self.assertEqual(expected["latency"]["status"], "placeholder")

    def test_reference_screen_scheme_exposes_cross_domain_evidence_gap(self) -> None:
        report = self.report

        for domain in report["domains"]:
            baseline = domain["evaluations"]["screen_scheme"]
            self.assertFalse(baseline["passed"])
            self.assertLess(baseline["metrics"]["evidence_producible"], 1.0)
            self.assertLess(baseline["metrics"]["critical_error_coverage"], 1.0)
            self.assertEqual(baseline["metrics"]["transfer_task_covered"], 0.0)

    def test_oracle_rejects_unsupported_claims(self) -> None:
        domain = copy.deepcopy(self.fixture["domains"][0])
        specimen = domain["specimens"][1]
        specimen["claims"].append(
            {"text": "Invented menu option", "fact_refs": ["gt.not_in_source"]}
        )

        result = evaluate_specimen(
            domain,
            specimen,
            viewport_budget_px=self.fixture["viewport_budget_px"],
        )

        self.assertEqual(result["metrics"]["unsupported_claims"], 1.0)

    def test_oracle_detects_multiple_actions_and_viewport_overflow(self) -> None:
        domain = copy.deepcopy(self.fixture["domains"][1])
        specimen = domain["specimens"][1]
        specimen["units"][0]["learner_actions"].append("run_query")
        specimen["units"][1]["estimated_height_px"] = 801

        result = evaluate_specimen(
            domain,
            specimen,
            viewport_budget_px=self.fixture["viewport_budget_px"],
        )

        self.assertLess(result["metrics"]["dominant_action_rate"], 1.0)
        self.assertLess(result["metrics"]["viewport_budget_rate"], 1.0)

    def test_sql_transfer_requires_hidden_dataset_oracle_not_only_task_reference(self) -> None:
        domain = copy.deepcopy(self.fixture["domains"][1])
        specimen = domain["specimens"][1]
        specimen["transfer_result"]["ordered_rows"][1] = [11, 1]

        result = evaluate_specimen(
            domain,
            specimen,
            viewport_budget_px=self.fixture["viewport_budget_px"],
        )

        self.assertEqual(result["metrics"]["transfer_task_covered"], 0.0)

    def test_ticket_fixture_contains_no_email_address_or_buyer_pii(self) -> None:
        ticket_domain = self.fixture["domains"][0]
        serialized = str(ticket_domain)

        self.assertIsNone(re.search(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b", serialized))
        self.assertNotIn("customer_id", serialized)

    def test_real_round_uses_scored_and_unscored_episode_paths(self) -> None:
        rows = {
            row["case_id"]: row
            for row in self.report["implementation_round"]["rounds"]
        }

        self.assertEqual(rows["recognition-ready"]["actual_status"], "ready")
        for case_id in ("ticket-critical-support", "sql-execution-support"):
            self.assertEqual(rows[case_id]["actual_status"], "support_only")
            self.assertEqual(rows[case_id]["graph_route"], "support")
            self.assertIsNone(rows[case_id]["legacy_fallback_target"])
            self.assertTrue(rows[case_id]["outcome_gate_passed"])

    def test_latency_gate_is_only_for_deterministic_planning_without_llm(self) -> None:
        implementation = self.report["implementation_round"]

        self.assertTrue(implementation["latency_gate_active"])
        self.assertIn("LLM generation", implementation["excludes"])
        self.assertIn("total learner-visible latency", implementation["excludes"])
        for row in implementation["rounds"]:
            self.assertEqual(row["latency_ms"]["samples"], 30)
            self.assertGreaterEqual(row["latency_ms"]["p95"], row["latency_ms"]["p50"])
            self.assertTrue(row["latency_gate_passed"])


if __name__ == "__main__":
    unittest.main()
