#!/usr/bin/env python3
"""Unit tests for Chapter 8 Demo: single-request evidence card."""

from __future__ import annotations

import unittest

from trace_one_request import TraceError, build_card, compute_gaps, correlate


def client(**overrides) -> dict:
    rec = {
        "request_id": "req-demo-001",
        "request_sent_ms": 0.0,
        "first_chunk_received_ms": 210.0,
        "response_finished_ms": 480.0,
        "retries": 0,
        "error": None,
    }
    rec.update(overrides)
    return rec


def server(**overrides) -> dict:
    rec = {
        "request_id": "req-demo-001",
        "queue_ms": 200.0,
        "scheduled_to_first_token_ms": 130.0,
        "generation_ms": 140.0,
        "e2e_ms": 480.0,
        "terminal_state": "finished",
    }
    rec.update(overrides)
    return rec


class TestCorrelation(unittest.TestCase):
    def test_matching_ids_are_ok(self):
        self.assertEqual(correlate(client(), server())["status"], "ok")

    def test_mismatched_ids_break_the_chain(self):
        result = correlate(client(), server(request_id="req-other"))
        self.assertEqual(result["status"], "broken")
        self.assertIn("evidence chain is cut", result["reason"])

    def test_missing_server_id_is_unknown_not_ok(self):
        result = correlate(client(), server(request_id=None))
        self.assertEqual(result["status"], "unknown")

    def test_missing_client_id_is_broken(self):
        self.assertEqual(correlate(client(request_id=""), server())["status"],
                         "broken")


class TestGaps(unittest.TestCase):
    def test_case_one_difference_splits_to_zero(self):
        """8.8 case 1: 9.48 s client, 0.48 s server, nothing left unattributed."""
        attempts = [
            {"outcome": "cancelled", "duration_ms": 3000.0, "backoff_ms": 1000.0},
            {"outcome": "cancelled", "duration_ms": 3000.0, "backoff_ms": 2000.0},
            {"outcome": "finished", "duration_ms": 480.0, "backoff_ms": 0.0},
        ]
        gaps = compute_gaps(
            client(response_finished_ms=9480.0), server(e2e_ms=480.0), attempts
        )
        self.assertAlmostEqual(gaps["difference_ms"], 9000.0)
        self.assertAlmostEqual(gaps["attributed"]["cancelled_attempts_ms"], 6000.0)
        self.assertAlmostEqual(gaps["attributed"]["client_backoff_ms"], 3000.0)
        self.assertAlmostEqual(gaps["unattributed_ms"], 0.0)

    def test_leftover_is_not_named(self):
        gaps = compute_gaps(client(response_finished_ms=560.0), server(), [])
        self.assertAlmostEqual(gaps["unattributed_ms"], 80.0)
        self.assertNotIn("network_ms", gaps)
        self.assertIn("no observed boundary, no name", gaps["note"])

    def test_missing_server_total_gives_no_difference(self):
        gaps = compute_gaps(client(), server(e2e_ms=None), [])
        self.assertIsNone(gaps["difference_ms"])

    def test_missing_client_total_is_an_error(self):
        with self.assertRaises(TraceError):
            compute_gaps(client(response_finished_ms=None), server(), [])


class TestCard(unittest.TestCase):
    def test_five_blocks_present(self):
        card = build_card(model="m", client=client(), server=server(),
                          collected_at="2026-09-21T10:00:00+0800")
        for block in ("identity", "client", "server", "correlation", "gaps"):
            self.assertIn(block, card)

    def test_card_surfaces_a_broken_correlation(self):
        card = build_card(model="m", client=client(),
                          server=server(request_id="req-other"),
                          collected_at="2026-09-21T10:00:00+0800")
        self.assertEqual(card["correlation"]["status"], "broken")


if __name__ == "__main__":
    unittest.main()
