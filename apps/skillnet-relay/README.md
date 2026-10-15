# skillnet-relay

A small service that receives bug reports from SkillNet instances and files them as GitHub
issues. It exists so the GitHub token lives in one place, on one server, and never in the code
or in anyone's copy of the app.

An instance sends a report to `POST /v1/reports`. The relay asks a model whether it's a real
report, rewrites it without personal details, checks the open issues for a duplicate, and then
opens an issue or comments on the existing one. The instance polls `GET /v1/reports/{receipt}`
to show the person what happened.

## Run it

```bash
docker build -f docker/relay.Dockerfile -t skillnet-relay .
docker run -d --env-file apps/skillnet-relay/.env -v relay-data:/data -p 8000:8000 skillnet-relay
```

Copy `.env.example` to `.env` first. `GITHUB_TOKEN` needs Issues: read and write on the one
repository. Give `LLM_API_KEY` its own key with a spend limit. Run a single worker: reports
are queued in the process and counted in one SQLite file.

## What it limits

- 10 reports an hour per address, 20 a day per instance, 200 a day in total.
- 5,000 characters per report.
- The text of a report is deleted after 30 days. The verdict and the issue link stay.
- `ENABLED=false` refuses every report without a redeploy.

The instance id is a random value each instance makes up for itself. It groups reports and
catches repeats, but it proves nothing, which is why the address is limited too.

## Tests

```bash
uv run pytest
```
