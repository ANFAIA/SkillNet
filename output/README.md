# Generation testing output

This directory stores reproducible evidence from the profile and course-generation
rounds. It is intentionally separate from production code.

Every network request has a finite timeout. Render and job polling also have a
deadline. A failed profile writes `journey.json` with the error and does not stop
the rest of the round.

Run one profile from the repository root:

```powershell
$env:SKILLNET_TEST_ADMIN_PASSWORD = "<local-admin-password>"
$env:SKILLNET_TEST_EMPLOYEE_PASSWORD = "<local-test-user-password>"
python output/harness/profile_run.py `
  --profile output/harness/profiles_r1.json `
  --config output/harness/round_r1.json `
  --out output/rounds/round-01/control-equilibrado
```

The orchestrator normally passes one JSON object per profile rather than the whole
array. Reports are generated with `analyze_round.py`.

## Offline architecture rounds (R1-R8)

`architecture_rounds.py` is a deterministic, keyless pre-implementation oracle for the
provider-neutral learning-experience architecture. It covers the neutral contract,
idempotent evidence-to-mastery, adapter fallback, multi-agent design-time generation,
variable rhythms, runtime selection without an LLM, a second-provider stub, and v1/v2
migration behavior.

Inspect the matrix without executing scenarios:

```powershell
python output/harness/architecture_rounds.py --mode dry-run
```

Execute every gate and write a machine-readable and human-readable report:

```powershell
python output/harness/architecture_rounds.py `
  --mode offline `
  --out output/architecture-rounds/latest
```

Run one or more focused rounds by repeating `--round`:

```powershell
python output/harness/architecture_rounds.py --round R2 --round R6
```

The offline suite does not claim production integration. As each architecture phase lands,
its scenario must be connected to the real adapter, transaction, persistence, or delivery
path and retain the same quantitative gate.
