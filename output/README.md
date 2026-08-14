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
