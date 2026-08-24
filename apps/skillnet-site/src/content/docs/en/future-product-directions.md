---
title: "Future product directions"
order: 36
section: "v2"
---

# Agreed future directions

> **Status: index of product ideas and plans that emerged in conversation.** This is not
> a dated roadmap and does not turn these directions into scope for the current version.

## 1. Expanding the audience without splitting the product

A single downloadable SkillNet with two future modes:

- `organization`: company, class, academy, team, or another group with an owner and
  participants;
- `individual`: a single person administers their own space and studies their own
  courses, with no employees or talent features.

`class` is not a third mode and `user` is not used as a mode name. The current
company/employee product is preserved. Full design:
[audience-modes.md](audience-modes.md).

## 2. Replacing and improving the mascot

The current mascot will change in the future. It must be a replaceable visual layer and
must not contain the chat, voice, or node-reading logic inside it.

It also remains pending to improve how it understands node state and when it
intervenes, because current behavior doesn't work well. The concrete solution must be
validated before being fixed. Brilliant's companion can serve as a targeted reference
for investigating that behavior, not as a general direction for the courses.

Agreed boundary:
[conversational-modalities.md](conversational-modalities.md).

## 3. Podcast Studio with NotebookLM-like quality

Start from the Audio Overviews experience: sources, focus, format, duration, language,
background generation, transcription, and references. The implementation will be
agnostic, modular, and configurable.

The default design may use two voices, but it will work with one or more depending on
the provider's capabilities. Grounding, editorial planning, script, review, voices, and
finishing will be replaceable stages.

Full plan: [podcast-studio-plan.md](podcast-studio-plan.md).

## 4. Audio as chat input

The person will be able to send a voice note to the chat. SkillNet transcribes it and
responds in text. It doesn't trigger TTS or open a call.

```text
audio -> transcription -> chat -> text
```

Agreed boundary:
[conversational-modalities.md](conversational-modalities.md).

## 5. Live voice conversations

Realtime will be a separate feature for talking by voice. Even if GPT Realtime is one
option, the integration must stay behind an abstraction to support other providers.

Its interface, concrete use cases, and implementation priority haven't been fixed yet.
Agreed boundary:
[conversational-modalities.md](conversational-modalities.md).

## 6. Separation of modalities

Web, audio, and video are cumulative modalities, not exclusive variants of a screen.
Multimedia generation stays on-demand and separate from OpenUI composition.

Architecture design:
[delivery-modalities.md](delivery-modalities.md).

## Status summary

| Direction | Status |
|---|---|
| `organization` and `individual` | Documented direction; not implemented |
| New mascot and better node reading | Direction defined; solution pending |
| Agnostic Podcast Studio | Plan documented |
| Audio in chat with text response | Behavior agreed; future |
| Agnostic Realtime conversation | Direction agreed; future |
| Web/audio/video modalities | Architecture documented; partial implementation |

This index should be updated when a direction is dropped, changed, or moves into an
implementation phase. It should not be used as an automatic list of promised features.
