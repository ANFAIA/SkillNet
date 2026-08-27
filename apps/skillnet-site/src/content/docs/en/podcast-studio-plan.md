---
title: "Podcast studio plan"
order: 49
section: "extensibility"
---

# Provider-agnostic Podcast Studio plan

> **Status: partly implemented.** Podcast generation exists (`src/routes/media.py`,
> `src/routes/tts.py`, voices in `config.py`) and the public seed produces one podcast per
> course. What remains a plan is the full studio this page describes: configurable
> multi-voice scripting, mixing and a style catalogue.

## Goal

Use NotebookLM's Audio Overviews as a product reference for generating source-based podcasts, but
implement the capability as an open, modular, configurable pipeline. No format, model, provider,
or number of voices is a fixed part of SkillNet's core.

## Starting experience

The first experience can keep the controls familiar from NotebookLM:

- source selection;
- optional guidance on the focus;
- format;
- duration;
- language;
- background generation;
- playback with transcript and associated sources.

NotebookLM is the initial reference, not a dependency or a product boundary. Its public
documentation describes those controls and the generation of Audio Overviews from sources:
[Generate Audio Overview in NotebookLM](https://support.google.com/notebooklm/answer/16212820).

## Architecture

```text
PodcastRequest
  -> SourceGrounder
  -> EditorialPlanner
  -> ScriptGenerator
  -> ScriptReviewer
  -> VoiceRenderer
  -> AudioPostProcessor
  -> PodcastArtifact
```

Each stage has its own contract and can be changed without modifying the others. The flow must
never call a provider directly from product logic.

### Common request

```text
PodcastRequest
  sources
  focus?
  format?
  duration?
  language?
  cast?
```

The request expresses what result the person wants. It does not include model names, voice
identifiers, or parameters specific to a given API.

### Providers by capability

A voice adapter declares what it can actually do:

```text
VoiceCapabilities
  max_speakers
  native_dialogue
  available_voices
  max_input_length
```

The renderer adapts the plan to those capabilities:

- one voice available: narration;
- two voices available: conversation;
- more voices available and requested: format with a larger cast;
- native dialogue: the provider receives the dialogue;
- plain TTS: SkillNet synthesizes turns and assembles the result.

The absence of a capability shrinks the format; it does not prevent generating the podcast.

## Content quality

The main improvement over the current flow is separating preparation, writing, and review:

```text
sources -> editorial map -> structure -> script -> review -> audio
```

- The editorial map collects which ideas must appear and how they relate to the sources.
- The structure decides the order and development of the episode.
- The generator writes the script for the available cast.
- The reviewer detects lack of grounding, repetition, and unnatural dialogue and requests a
  correction before synthesis.

These stages are also replaceable. An installation can use the same model for all of them,
different models, or local implementations.

## Configuration

SkillNet ships a default design so the feature works without detailed configuration. As a starting
point:

```text
format: deep dive
duration: medium
language: the configured one
cast: two voices when the provider allows it; one when it doesn't
```

Configuration can be overridden at deployment and per generation. Defaults should never become
internal assumptions baked into the pipeline.

## Relationship to what exists

The current producer already has grounding, formats, a validated script, Text-to-Dialogue, and
per-turn fallback. The evolution should keep that producer behind the new contract and
progressively split its responsibilities; it does not require discarding it.

The modality continues to be generated on demand and in the background per
[delivery-modalities.md](/en/docs/delivery-modalities). The podcast remains separate from chat,
Realtime, and the mascot per
[conversational-modalities.md](/en/docs/conversational-modalities).

## Phases

1. Introduce the request, plan, and capability contracts without changing the current output.
2. Separate editorial map, script, and review.
3. Automatically adapt the cast to the provider's capabilities.
4. Expose the controls for sources, focus, format, duration, and language.
5. Improve synthesis and finishing through optional modules.

## Design criteria

- works with one or several speakers;
- no provider is mandatory;
- every stage can be replaced;
- a usable default configuration exists;
- sources are preserved during planning and writing;
- generation remains asynchronous;
- switching providers does not modify courses or artifacts already created.

## Not yet decided

- default providers and models;
- specific voices;
- exact parameters for each format;
- advanced editing controls;
- cost or generation limits per installation.
