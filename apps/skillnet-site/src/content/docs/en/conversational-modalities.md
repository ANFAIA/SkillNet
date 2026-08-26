---
title: "Conversational modalities"
order: 25
section: "core"
---

# Conversation, voice, and companionship

> **Status: future idea, no implementation commitment.**

## Direction

SkillNet may incorporate several features related to audio and companionship. They
must be kept separate so they can be improved or replaced without coupling the whole
application.

## Audio in chat

The person can send an audio message to the chat. SkillNet transcribes it and the
chat responds in text.

```text
audio -> transcription -> chat -> text response
```

This does not imply the chat responds with voice, nor that a live conversation is
started.

## Realtime conversation

Realtime is a distinct feature for holding a live voice conversation. Its integration
must sit behind an abstraction so as not to couple the rest of SkillNet to GPT
Realtime or to any particular provider.

## Mascot

The mascot visually represents the learning companion. It must not contain the chat,
voice, or node-reading logic inside it. It receives simple signals from the system
and its appearance can change without modifying those features.

The concrete way to improve how it interprets and accompanies nodes remains pending
design and validation.

## Podcasts

Podcast generation continues to be a separate feature. Both the generation studio and
the output quality will be improved, without turning the podcast into part of chat or
Realtime.

The modular, configurable plan is defined in
[podcast-studio-plan.md](/en/docs/podcast-studio-plan).

## Relationship to audience modes

These features can be part of SkillNet's common core when useful in a course. The
`organization` mode keeps the current company/employee focus. The `individual` mode,
if implemented in the future, will reuse the same features without employee or talent
management.

This document does not yet define additional use cases, evaluation flows, memory,
implementation priorities, or detailed interface behavior.
