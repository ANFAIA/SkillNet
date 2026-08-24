---
title: "Delivery modalities"
order: 34
section: "v2"
---

# Delivery modalities and experience structure

**Status:** architecture decision. Invisible selection of a single experience is the
current direction; game and free-form UI remain future extensions.

## Decision

A **modality** is the complete medium through which a person takes an experience:
web, audio, video, and in the future, game. A **structure** is the composition within
a modality. On web it can be a brief explanation, a worked example, practice,
a check, or transfer.

These are not tabs or options the person has to manage during the course. Preferences,
the goal, the pedagogical state, and the available capabilities form the agent's private
input. The agent chooses a single experience for that moment. The conceptual contract is:

```text
LearningExperience
  pedagogical intent
  candidate capabilities
    web structures: bounded slice
    audio?: when preferred and available
    video?: when preferred and available
    game?: future capability
  runtime decision -> one selected experience
```

Web is the current primary fallback. Audio and video preferences are additive as
signals: both can broaden the candidate set, but they don't force two outputs or show up
as navigation. The screen stays fixed while it's open. If a media selection can't be
served, the runtime falls back to the next approved variant and ultimately to web.

## Boundary with OpenUI

OpenUI receives a small subset of implementations compatible with the intent, pedagogical
state, accessibility, preferences, and client capabilities. It does not receive the entire
global catalog. The resolver narrows the space first and the agent decides within that
boundary; the frontend only renders the fixed result.

There is no shell with Web/Audio/Video tabs. The global catalog can grow without
proportionally increasing the prompt:

```text
global catalog -> capabilities/preferences -> intent shortlist -> runtime agent
                                                               -> one experience
```

Course generation prepares pedagogical contracts, definitions, and bindings that
streamline the experience, but doesn't attach pre-made audio or video to the course. If
the agent chooses a media experience, the runtime generates the representation on-time;
the corresponding producer resolves its output and the fallback remains approved in
advance.

## On-time generation

Audio and video are not discovered by querying the course's artifact library, nor are
they part of the course schema. Server-side selection goes through the same node
authorization and enrollment as web rendering. The modality endpoint is internal
infrastructure; it isn't an action or a selector exposed to the learner.

The media infrastructure persists the final result as a cache for polling, retries,
and reuse after a reload. That row is an internal runtime detail: it isn't an
authoring block, it doesn't appear as a pedagogical decision, and it doesn't let the
player mix results from the course's general panel.

## Versioned preferences

The v3 contract separates:

- `web_presentation`: `balanced | text | visual | data`;
- `modalities`: a set of `audio | video`;
- `interaction`, `detail`, and `images`: web structure settings.

v1 and v2 values normalize to v3. The old single `audio` value migrates to
`modalities=[audio]` and leaves the web presentation at `balanced`.

## Shared intermediate artifacts

A shared intermediate artifact layer across modalities is not introduced now.
Each producer keeps its own immutable definition and binding. This decision avoids
prematurely coupling audio, video, and web to a common format that doesn't yet have
enough use cases. It can be added later behind a versioned input contract, without
changing `LearningExperience` or the player boundary.

## Future extension: free-form UI and game

Level 3 will not be "add hundreds of components to the prompt." It will be a generic
implementation, e.g. `sandboxed.generated-ui@1`, selectable through the same binding as
any other experience. Its on-time or anticipated generation policy must be
explicit; either way it's served as an immutable, isolated output.
It is not currently registered or allowed.

Before enabling it, it must at minimum meet:

- isolated execution, no cookies or network by default;
- an explicit manifest of capabilities and CPU, memory, and time limits;
- immutable digest, provenance, and version;
- a normalized evidence port toward mastery, with no direct writes;
- verifiable accessibility and keyboard navigation;
- fallback to a structured experience if validation or execution fails;
- a review and publishing policy equivalent to other definitions.

A game will be another modality or implementation using that contract, not an
exception in the OpenUI agent. This allows evolving from closed components to
free-form experiences without breaking intent, evidence, history, personalization,
or fallback.

## Out of scope for now

- generating games;
- executing freely generated code;
- sharing scripts or intermediate representations between producers;
- showing a Web/Audio/Video selector to the learner;
- forcing audio or video production just because they're user preferences;
- using the course's general artifact library as the player's source.
