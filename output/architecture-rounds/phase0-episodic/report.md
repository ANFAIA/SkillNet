# Phase 0 - ScreenScheme versus episodic contract

- Benchmark ready: **PASS**
- Status: `implementation-connected-phase0`
- Latency gate active: `true`
- Latency gate scope: `deterministic_direct_episode_planning`
- Disclaimer: Reference specimens remain trajectory oracles; only deterministic direct_episode planning is connected to real code and timed.

| Domain | ScreenScheme | Episodic expected contract |
|---|---:|---:|
| Recuperar entradas no recibidas en Crocantickets | FAIL | PASS |
| LEFT JOIN con valores NULL | FAIL | PASS |

## Real implementation round

| Case | Result | Legacy fallback | p50 ms | p95 ms |
|---|---:|---:|---:|---:|
| recognition-ready | PASS | - | 2.3264 | 2.8590 |
| ticket-critical-support | PASS | - | 2.3923 | 2.8344 |
| sql-execution-support | PASS | - | 9.2231 | 10.9055 |

The active latency gate measures deterministic `direct_episode` planning only. It
does not measure LLM generation, activity authoring, persistence, browser work or
total learner-visible latency.
