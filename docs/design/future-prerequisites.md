# Future: prerequisite handling for learners

> Status: idea, not planned. Documenting for when the runtime learner experience is revisited.

## Current behavior

When a course node has prerequisites, the learner cannot access it until the prerequisite
nodes are completed. The system blocks access entirely.

## Proposed alternative

Instead of blocking, offer the learner a choice when they reach a node with unmet prerequisites:

1. **"Ya se esto"** — The learner marks the prerequisites as known and skips them.
   The system could optionally verify with a quick probe (the probe items already exist
   in the node model).

2. **"Quiero aprenderlo primero"** — The system generates a mini-course on-the-fly
   covering the prerequisite topics. This uses the same runtime render pipeline
   (POST /nodes/{id}/render) but scoped to just the prerequisite nodes.

3. **"Mostrame un resumen"** — A condensed version of the prerequisites, not a full
   course. Enough context to continue without doing the full prerequisite path.

## Why

- A bakery owner who already knows food safety should not sit through basics because
  the DAG says so.
- A new employee who genuinely does not know should get help, not just a wall.
- Different learners have different starting points. The prerequisite graph should be
  a guide, not a gate.

## Dependencies

- The prerequisite DAG model stays as-is (it still defines the recommended order).
- The probe system (course_nodes.probe_items) could serve as the "do you already know
  this?" verification.
- The runtime render pipeline already generates content per-node on demand, so
  generating a mini-course is just rendering the prerequisite nodes.

## Open questions

- Should "ya se esto" require passing a probe, or is the learner's word enough?
- Should the admin be able to configure this per-course (strict vs flexible prerequisites)?
- How does this affect mastery tracking and completion metrics?
