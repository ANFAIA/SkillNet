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
    def setUp(self) -> None:
        self.fixture = load_fixture()

    def test_fixture_is_a_valid_two_domain_contract(self) -> None:
        validate_fixture(self.fixture)

        self.assertEqual(
            [domain["domain_id"] for domain in self.fixture["domains"]],
            ["gestion-tickets", "sql"],
        )
        self.assertEqual(self.fixture["status"], "contract-only")

    def test_expected_contract_passes_without_claiming_future_implementation(self) -> None:
        report = run(self.fixture)

        self.assertTrue(report["benchmark_ready"])
        self.assertFalse(report["latency_gate_active"])
        for domain in report["domains"]:
            expected = domain["evaluations"]["episodic_contract"]
            self.assertTrue(expected["passed"])
            self.assertEqual(expected["specimen_kind"], "expected-output-contract")
            self.assertEqual(expected["latency"]["status"], "placeholder")

    def test_reference_screen_scheme_exposes_cross_domain_evidence_gap(self) -> None:
        report = run(self.fixture)

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


if __name__ == "__main__":
    unittest.main()
