# Roadmap

> Updated: 2026-08-31. This roadmap separates the implemented baseline from active validation and
> later product directions. It describes outcomes, not a promise of dates.

SkillNet's direction is simple: turn existing knowledge into grounded, traceable training, then let
the experience change shape for the person learning without changing the knowledge or the standard
they must meet.

## Baseline available in the repository

### Knowledge to course

- Create a course from a topic or from PDF, DOCX, Markdown and TXT sources.
- Keep source grounding through course generation and preserve explicit source references where the
  activity contract supports them.
- Generate courses through the web UI and the external course-creation path.
- Preserve the static v1 path while opting individual validated courses into dynamic delivery.

### Learning experience

- Deliver grounded lessons and exercises. Probe contracts and routes exist, but pre-assessment is
  currently bypassed in learner delivery.
- Retrieve enrolled material and return provenance for course-specific tutor questions; answer
  general questions without forcing course citations.
- Compose controlled generated interfaces with OpenUI and a supported, version-pinned subset of
  Didact.
- Support click-to-explain and contextual exploration without leaving the learning flow.
- Generate supported media artifacts asynchronously and place eligible media inside an episode
  when the required AI, image and TTS providers are configured.

### Traceability and talent

- Record enrollments, attempts, node completion, mastery and learning events.
- Record skill levels from course mastery or explicit verification.
- Provide admin talent views for people, courses, progress and recorded skills.
- Provide programmatic skill, `who-knows`, gap and manual-verification APIs.
- Expose skill queries and complete course creation through `/ext/v1`.

### Deployment and interoperability

- Run as an organization or individual workspace.
- Self-host with Docker and an OpenAI-compatible model provider.
- Use SkillNet through the web application and REST API. Optional A2A and MCP adapters call the
  external API and start through their Compose profiles.
- Keep English and Spanish product surfaces in the same codebase.

The baseline being implemented does not mean every path has equal product maturity. The static path
is the compatibility floor. Dynamic episodes, generated media and adaptive behavior require more
validation under realistic sources, learners and model configurations.

## Active priorities

### 1. Make generated training trustworthy

- [ ] Evaluate course fidelity against representative company documents.
- [ ] Measure unsupported claims, missing critical knowledge and citation quality.
- [ ] Improve knowledge packs and component selection from the actual shape of each source.
- [ ] Keep deterministic fallbacks when generation or validation fails.
- [ ] Publish a small, repeatable quality benchmark with expected outputs.

### 2. Prove the complete workflow

- [ ] Make `idea/source → course → learner → progress → talent` reliable as one end-to-end path.
- [ ] Reduce unnecessary steps between creating, reviewing, publishing and taking a course.
- [ ] Keep generation progress understandable without exposing internal agent noise.
- [ ] Maintain a seeded demonstration that works without private data.
- [ ] Verify organization and individual setup paths from a clean installation.
- [ ] Decide whether and how to reactivate pre-assessment in learner delivery.

### 3. Validate adaptation instead of merely generating variation

- [ ] Compare two experiences built from the same knowledge and objective.
- [ ] Separate declared preference, immediate intent, engagement and measured effectiveness.
- [ ] Test whether an adaptation improves comprehension or completion before retaining it.
- [ ] Surface the existing inspect, edit and clear memory controls in the learner product.
- [ ] Extend retained memory beyond tutor personalization without letting free-form memory steer
  shared lesson renders unsafely.
- [ ] Avoid fixed learning-style labels; treat every preference as a revisable hypothesis.

### 4. Stabilize the learning surface

- [ ] Validate every supported Didact family in real course episodes.
- [ ] Keep titles, content density, transitions and responsive layout consistent.
- [ ] Make audio, podcast, infographic, slide and video states honest when providers are unavailable.
- [ ] Test tutor, explain and media flows with employee permissions, not only admin access.
- [ ] Preserve accessible keyboard, focus and reduced-motion behavior.

### 5. Harden traceability and interoperability

- [ ] Verify that skill evidence can be traced back to attempts, rendered material and source.
- [ ] Clarify the difference between completion, mastery and a recorded skill in every surface.
- [ ] Harden API keys, rate limits, errors and timeouts on `/ext/v1`.
- [ ] Keep MCP and A2A as thin clients of the external API rather than parallel business logic.
- [ ] Document backup, upgrade and model-change procedures for self-hosted deployments.

## Next product horizon

These directions build on the active priorities. They are not committed releases.

### Living knowledge

- Detect when a source changes and identify affected course nodes.
- Propose grounded updates while preserving a human decision point.
- Show learners which version of the knowledge their training used.

### Richer sources and outputs

- Accept more source modalities, including useful audio and video ingestion.
- Improve podcast and visual-material quality from grounded content.
- Make generated media part of the learning mission, not a detached content gallery.

### Better talent understanding

- Move from a list of completions to evidence-backed capability profiles.
- Turn the existing programmatic gap and `who-knows` capabilities into richer admin experiences
  without pretending that a score captures a whole person.
- Make talent data portable through open interfaces instead of trapping it in the application.

### Personalization over time

- Extend the existing editable learner memory from tutor use into evaluated learning experiences.
- Distinguish what the learner wants now from what has helped across sessions.
- Suggest adaptations under user control instead of silently locking the person into a profile.

## Research horizon

### Three levels of generated interface

1. **Fixed screen:** the structure is fixed and the content changes.
2. **Controlled composition:** the model chooses from approved components through a compact,
   validated interface language. This is the practical center of SkillNet today.
3. **Open generation:** the model can build a new simulation or interaction when no approved
   component fits. Use only where quality, latency, cost and reliability justify it.

As models improve, the boundary between these levels will move. The roadmap does not assume that
the most generative level is automatically the best one.

### Software that accompanies the learner

- Agents that can act across longer learning journeys with explicit permission.
- Interfaces that reorganize around the current task without hiding their reasoning or controls.
- Learning experiences that travel through external chats and agents instead of requiring one
  closed super-application.

## Principles

1. **Grounding before generation.** A richer interface cannot compensate for unsupported content.
2. **Quality before breadth.** Do not add a modality or component until its failure mode is honest.
3. **Same knowledge, different path.** Adapt the experience without moving the objective or evidence bar.
4. **Intent is not memory.** Reacting to a request now is different from knowing what helps over time.
5. **Personalization is a hypothesis.** Learners must be able to inspect and correct it; the system never defines them.
6. **Controlled generation first.** Components and schemas are the reliable default; open generation earns its place.
7. **Traceability is part of learning.** Progress and skills must point back to evidence.
8. **Open and self-hosted by design.** Organizations control their knowledge, models and data.

## Design records

- [v1 scope and compatibility](design/v1-scope.md)
- [v2 dynamic courses](design/v2-dynamic-courses.md)
- [Learning experience architecture](design/learning-experience-architecture.md)
- [Personalization architecture](design/personalization-architecture.md)
- [Didact integration](design/didact-integration.md)
- [Media artifacts](design/media-artifacts.md)
- [Admin library and talent](design/admin-library-and-talent.md)
- [External API and MCP](design/mcp-external-api.md)
- [Vision](design/vision.md)
