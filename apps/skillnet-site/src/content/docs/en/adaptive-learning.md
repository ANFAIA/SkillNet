---
title: "Adaptive learning"
order: 37
section: "extensibility"
---

# Adaptive learning and presentation preferences

**Date:** 2026-08-11
**Status:** product decision and design direction; the causal instrumentation described here is not fully implemented.
**Applies to:** dynamic v2 courses, the component catalog, and a future external library.

## 1. Thesis

SkillNet must respect what the learner asks for and, within that preference, combine strategies that
help them understand, practice, and transfer knowledge.

> The customer governs presentation. The system adapts teaching; it does not fight the customer's
> choice.

If a person wants images, audio, video, or text, they must receive them whenever the kit and the
source can produce them. The response is not to invalidate that choice, but to **compose**:

```text
explicit preference: image
    + strategy: retrieval
    + activity: identify errors in a scene
    + feedback: informative
```

## 2. Four distinct layers

| Layer | Question | Examples | Authority |
|---|---|---|---|
| Explicit preference | How do they want to receive it? | image, audio, text, video | The user governs |
| Accessibility | What do they need to operate the content? | keyboard, contrast, less motion | Hard opt-in constraint |
| Pedagogical strategy | What must they do to learn it? | retrieve, explain, compare, decide | Adaptive designer |
| Component | What interaction implements the strategy? | choice, ordering, dialogue, map | Catalog/library |

A table, image, or audio clip are presentations. A quiz can implement retrieval, but it can also be
a surface-level check. The renderer does not know the pedagogical intent on its own.

## 3. Evolution of `format_vector`

The current vector (`text`, `exercise`, `code`, `data`) records usage affinity, not learning.
It is not removed without better data; it is reclassified as an inferred preference and separated
from the effect:

```json
{
  "presentation_preferences": {
    "declared": ["image", "audio"],
    "inferred": {"text": 0.3, "exercise": 0.7}
  },
  "learning_effects": {
    "retrieval_practice": {
      "immediate_delta": 0.10,
      "retention_delta": 0.16,
      "transfer_delta": 0.08,
      "samples": 12,
      "confidence": 0.64
    }
  }
}
```

Rules:

1. A declared preference prevails over the inferred one.
2. Inference ranks compatible options; it never removes the requested modality.
3. `learning_effects` is not updated from isolated clicks; it needs comparable results.
4. Engagement, immediate mastery, retention, and transfer are not collapsed prematurely.
5. Every adaptive decision records reason, sample size, and confidence.

## 4. Educational taxonomy

The component library must not be the pedagogical ontology. SkillNet first selects the educational
function and then asks the library for a component capable of implementing it.

| Axis | Initial values |
|---|---|
| Function | explain, retrieve, diagnose, practice, transfer, reflect |
| Knowledge | factual, conceptual, procedural, conditional, interpersonal |
| Cognitive action | recognize, recall, order, classify, explain, decide, produce |
| Interaction | choice, text-entry, order, match, dialogue, map, simulation |
| Presentation | text, table, image, audio, video, diagram |

This extends `ContentFunction` from
[`arquitectura-componentes-funcional.md`](/en/docs/arquitectura-componentes-funcional): that layer
describes the shape of the source (`CONTRASTAR`, `PROCEDIMENTAR`); this one adds the learner's
action and the observable outcome.

## 5. Contract with the external library

The current components will be gradually replaced. The backend does not import internal React
names nor know their implementation. The boundary is a versioned descriptor:

```json
{
  "component_id": "scenario.dialogue",
  "version": 1,
  "pedagogical_functions": ["practice", "transfer"],
  "knowledge_types": ["conditional", "interpersonal"],
  "cognitive_actions": ["decide", "explain"],
  "presentations": ["text", "audio"],
  "qti_interaction": "extendedTextInteraction",
  "xapi_interaction": "long-fill-in",
  "requirements": ["branching_script"],
  "accessibility": {"keyboard": true, "drag_alternative": null},
  "events": ["started", "answered", "requested_hint", "completed"],
  "props_schema": {}
}
```

- The library publishes the catalog, schemas, renderer, and event adapters.
- SkillNet retains pedagogical policy, profile, cache, generation, and evaluation.
- `component_id` is stable and versioned; the React name is not persisted.
- The old and new renderers coexist until equivalent golden specs exist.
- A component declines if data or media are missing; it never invents relationships absent from
  the source.
- QTI/xAPI are interoperability mappings, not the full internal model.

Design references:

- [QTI 3.0 Best Practices](https://www.imsglobal.org/spec/qti/v3p0/impl)
- [H5P semantics.json](https://h5p.org/semantics)
- [xAPI specification](https://github.com/adlnet/xAPI-Spec)

### What is adopted from the references and what is not

| Reference | Use in SkillNet | Decision |
|---|---|---|
| QTI 3.0 | interaction vocabulary and future compatibility | Map it; do not turn it into the internal IR |
| H5P semantics | precedent for declarative, validatable schemas | Inspire the descriptor; do not import content types |
| xAPI | interaction names and corporate export | Reporting adapter, not the pedagogical model |
| `dnd-kit` | accessible operation of drag interactions | External library's responsibility; not added here |
| Ink/inkjs | compact representation of branching scenarios | Evaluate as an authoring format, without making it a runtime requirement |
| Sandpack | sandboxed execution for technical training | Only if a real use case for code courses appears |
| FSRS | review scheduling | Not adopted while spaced repetition is out of scope |

These references guide contracts and tests; they do not justify adding dependencies to SkillNet
before the external library or a real product case needs them.

## 6. Initial strategies

- Retrieval: answer without immediately re-reading the solution.
- Self-explanation: explain why a decision is correct.
- Comparison: discriminate between close cases.
- Worked example: especially when introducing procedures to novices.
- Decision scenario: conditional and interpersonal knowledge.
- Order/execute: reconstruct procedures.
- Mapping or drawing: when spatial structure is a real part of the knowledge.

Fiorella and Mayer describe eight generative strategies — summarizing, mapping, drawing, imagining,
self-testing, self-explaining, teaching, and enacting — as vocabulary, not as an obligation to use
all of them:

- [Eight Ways to Promote Generative Learning](https://link.springer.com/article/10.1007/s10648-015-9348-9)
- [Improving Students' Learning With Effective Learning Techniques](https://journals.sagepub.com/doi/10.1177/1529100612453266)
- [The Power of Feedback Revisited](https://www.frontiersin.org/articles/10.3389/fpsyg.2019.03087/full)
- [Does Simulation-Based Training Improve Learning?](https://onlinelibrary.wiley.com/doi/10.1111/j.1744-6570.2011.01190.x)

Useful feedback informs what failed, why, and what the next step is. Praise, points, or a bare
`Correct/Incorrect` without information are not the unit being optimized.

## 7. Events and outcomes

Events keep treatment, component, and presentation separate:

```json
{
  "verb": "answered",
  "node_id": "...",
  "strategy": "retrieval_practice",
  "component_id": "assessment.order",
  "presentation": ["image"],
  "result": {"success": false, "attempt": 1, "duration_ms": 42000, "hints": 0},
  "context": {"variant": "B", "exploration": true}
}
```

Separate outcomes: engagement, immediate mastery, delayed retention, and transfer. SkillNet does
not invent artificial reviews just to measure: it can obtain delayed evidence from later courses,
retries, real tasks, or recertifications, should those come to exist.

## 8. Necessary experiments

### Explicit preference + mixing

For someone who chooses images, keep them across all variants:

| Variant | Treatment |
|---|---|
| A | image + explanation |
| B | image + retrieval |
| C | image + scenario |

This way we learn which strategy helps without disobeying the preference.

### Within-learner crossover

Apply different treatments to equivalent objectives and cross them afterward. This reduces
confounding from difficulty, prior knowledge, and topic.

### Preference versus outcome

Store declared preference, usage, and outcome separately. A discrepancy does not remove the
preference: it indicates it should be mixed with another strategy.

### Ablations of the current model

1. Cold/warm state with an empty vector.
2. Cold/warm state with a populated vector.
3. Same state, different role.
4. Same role, different experience.
5. Same profile with/without `short_blocks`.

Measure 3-5 renders of the same profile before attributing a difference to the treatment.

### Accessibility

This is tested as compliance, not as uplift. Every drag feature offers a non-drag operation,
per WCAG 2.2 2.5.7:

- [Understanding Dragging Movements](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html)

## 9. Spaced repetition

**Out of scope for the current product.** Courses are typically short, and there is no case that
justifies a scheduler, a daily queue, FSRS, streaks, or a review table.

This is reopened only with product evidence: long programs, periodic recertification, safety
knowledge that must be maintained for months, or explicit hiring of continuous training. In the
meantime, attempts and events are kept, but a spaced-repetition experience is not built. Older
mentions in v1 documents are historical plans, not current roadmap.

## 10. Recommended order

1. Formalize the taxonomy and the library's versioned descriptor.
2. Map current components to function, knowledge, action, and interaction.
3. Separate declared preference from inferred `format_vector`.
4. Instrument strategy, component, presentation, and variant in events.
5. Run mixing tests while keeping the requested modality.
6. Add `learning_effects` only with sufficient comparisons.
7. Replace renderers gradually via golden specs; no big-bang migration.

The executable separation between objective, cognitive mission, representation, component, and
support, along with its cache invariants and migration plan, is defined in
[`personalization-architecture.md`](/en/docs/personalization-architecture).

The results that justify these decisions, including reverted experiments, are kept in the
``personalization experiments notebook``.
