<p align="center">
  <img src="assets/logo.png" alt="SkillNet" width="104">
</p>

<h1 align="center">Learning experiences, generated on the fly</h1>

<p align="center">
  <strong>SkillNet turns an idea or source into a course, a grounded tutor and an adaptive learning interface.</strong>
</p>

<p align="center">
  For one learner, a class, a team or an organization.
</p>

<p align="center">
  <a href="https://skillnet.es"><strong>Website</strong></a> ·
  <a href="https://skillnet.es/docs/">Documentation</a> ·
  <a href="RUNNING.md">Run locally</a> ·
  <a href="README.es.md">Español</a>
</p>

<p align="center">
  <a href="https://github.com/ANFAIA/SkillNet/actions/workflows/ci.yml"><img src="https://github.com/ANFAIA/SkillNet/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-2f6fed.svg" alt="Apache 2.0"></a>
</p>

## Start with an idea — or bring your sources

Learning does not always begin inside an organization or an existing document. Sometimes it starts
with a topic you want to understand. Sometimes the knowledge already lives in PDFs, manuals, notes
or conversations.

SkillNet supports both paths. Describe what you want to learn or teach, or upload PDF, DOCX,
Markdown and TXT material. It then builds a structured course with lessons, exercises, a tutor and
learning media. Uploaded material remains the grounding source; idea-based courses preserve their
model-generated provenance instead of presenting it as uploaded evidence.

## One foundation, different ways to learn

The knowledge, objectives and evaluation criteria stay stable. The explanation, example, activity,
medium and interface can change with the learner's preferences, experience, current state and
bounded interaction signals.

| The learning contract | The experience can adapt |
| --- | --- |
| Knowledge and sources | Explanations and examples |
| Objectives and evidence | Practice and support |
| Evaluation criteria | Medium, sequence and interface |

Responding to a request in the moment is not the same as learning what has helped a person over
time. SkillNet treats those signals as revisable evidence—not fixed “learning styles” and not a
claim that the system already knows the learner perfectly.

## What SkillNet does today

- **Creates complete courses** from a topic or PDF, DOCX, Markdown and TXT sources.
- **Answers with a course tutor** that retrieves enrolled sources and returns provenance.
- **Composes learning experiences** with [OpenUI](https://github.com/thesysdev/openui) and a
  supported, version-pinned subset of [Didact](https://github.com/JoseEstevez520/Didact).
- **Generates learning media** such as podcasts, infographics, slide decks and narrated videos when
  the corresponding providers are configured.
- **Records progress and skills** through enrollments, attempts, mastery and explicit verification.
- **Works at different scales** through individual and organization workspaces, from personal study
  to classes, teams and larger deployments.
- **Connects to other tools** through its REST API and optional A2A and MCP adapters.
- **Runs on your infrastructure** with Docker and an OpenAI-compatible model provider.

<details>
<summary><strong>Current boundaries</strong></summary>

The controlled runtime can already produce different experiences for different learner profiles
and states. Educational effectiveness and the quality of each adaptation still need more evidence.
Free-form memory steering shared lesson renders, proactive adaptation, automatic synchronization
when sources change and fully open-ended generated interfaces remain later directions—not current
promises.

</details>

## Run it locally

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec api python -m src.seed_learning_demo   # optional public demo
```

Open <http://localhost:3000>. The full [running guide](RUNNING.md) covers provider configuration,
keyless fixtures, demo data and troubleshooting.

## Explore

- [Vision](docs/design/vision.md) — why learning software should adapt to people.
- [Product](docs/design/product.md) — current scope and product direction.
- [Roadmap](docs/ROADMAP.md) — the next four priorities.
- [ANFAIA release snapshot](docs/releases/2026-09-01-anfaia.md) — what this version contains.
- [OpenUI adoption](docs/design/openui-adoption.md) — the controlled GenUI runtime.
- [Didact integration](docs/design/didact-integration.md) — how learning components enter SkillNet.
- [Contributing](CONTRIBUTING.md) — development setup, checks and conventions.

## Ecosystem

SkillNet is the main project. [Didact](https://github.com/JoseEstevez520/Didact),
[OpenUI](https://github.com/thesysdev/openui),
[mcp-md-reader](https://github.com/JoseEstevez520/mcp-md-reader),
[A2TL-Web](https://github.com/JoseEstevez520/a2tl-web),
[A2TL-Video](https://github.com/JoseEstevez520/a2tl-video),
[Curio](https://github.com/JoseEstevez520/curio) and
[DBP](https://github.com/JoseEstevez520/DBP) explore related parts of the same direction at different
levels; they are not all dependencies of the current runtime.

## License

SkillNet is open source under the [Apache 2.0 license](LICENSE). Security issues should follow
[SECURITY.md](SECURITY.md), never a public issue.
