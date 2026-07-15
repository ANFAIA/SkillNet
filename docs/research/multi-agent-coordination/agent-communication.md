# Communication between agents

## The problem

A single agent working for one person is the easy case. The problems begin when agents **communicate across people** · my agent and my neighbor's, or a team where everyone runs their own and they have to trade knowledge to get work done. The instant two agents belonging to different people talk, a question appears that a lone agent never faces: when my agent asks yours for something, what may yours reveal, and what may mine accept? Each agent sits on a body of knowledge that is not all shareable · some of it private to its owner, some shared for one task and not the next.

Today's agent protocols do not answer this. A2A, and the stack around it like MCP for tools, handle how agents find and authenticate each other · proving an agent is who it claims · and then hand the harder question, what one may reveal to another, back to each implementation. In practice the boundary ends up living as a **soft norm**: a line in a `CLAUDE.md`, a "don't share this" note, a skill that says "use only the public catalog." That prose is **probabilistic**. It describes a boundary; it does not enforce one; whether it is honored depends on the model that reads it. As agents increasingly sit between people and their knowledge, that is a great deal to leave to goodwill · and it is the same wall this research already hit from the classification side: privacy is a human decision, not a property of the text, and a probabilistic reader cannot be trusted to police it.

So the question worth asking is this: **can the boundary that governs what crosses between agents be made deterministic** · decided by a rule, outside the agent, the same way every time · and hold even between two agents that were never introduced?

## The shape of the answer

The decision has to come off the agent's goodwill and onto something the agent cannot bend. The move is to attach it to the **data**: each piece of knowledge carries a label, each requester carries what it is allowed to hold, and what may cross is a plain comparison between the two, made at the door rather than argued inside the agent.

```yaml
---
compartment: jose:budget
---
```

The comparison is set inclusion · you may receive a piece if your compartments contain its. Where the soft layer *describes* a boundary, this one *decides*. It rests on three pieces, taken in turn: what may cross, what did cross, and where the agents meet.

## 1. The protocol · what may cross

Access is normally granted to a *relationship*: this agent may reach that resource. That is what A2A assumes, and it works when the two were introduced and provisioned in advance · fine inside a single company, impossible between agents meeting for the first time. Putting the permission on the **data** removes the introduction. A piece carries its compartments, a requester carries theirs, and what may cross is the inclusion between them · no audience named, nothing wired per pair. Between my agent and a neighbor's I never met, the piece states its own terms, the requester brings its own claims, and the boundary resolves them on the spot.

The obvious worry is that a requester carrying its own labels could simply lie about them. It cannot, because a label is asserted by the **owner** of that compartment, not written by the asker. My neighbor's agent can present "Jose granted me `jose:budget`," and that holds only because Jose signed it, or wrote it somewhere only Jose can write. You can carry a claim; you cannot forge whose it is. This is the reason the label rides with the data while the authority stays with the owner · together they are what make a carried claim trustworthy without anyone having been registered beforehand.

Two further properties make this more than relabeling. A piece **derived** from others inherits the *union* of their labels: a summary built from two compartments can cross only to someone who holds both, so the boundary follows the knowledge as the agent reworks it, not only where it was first filed. And because the check sits at the door · on the way into the agent's context and on the way out · the firmest guarantee turns out to be the simplest: a piece the agent never receives is one it cannot pass on. That is deliberate. You cannot trust a probabilistic agent to withhold what it has already been given, so the control never asks it to; it decides what the agent is given in the first place. Control lives at the boundary, as the coordination notes already argue, and the label is what lets that boundary decide deterministically instead of case by case.

## 2. Traceability · what did cross

A soft norm leaves no trace of whether it was obeyed. If an agent ignores "don't share this," nothing in the system notices, and there is nothing to point to afterward. A deterministic boundary changes that simply by being the one place everything passes through: every crossing can be written down · what was read, what was emitted, which label authorized it, and in which direction.

The record is kept at the boundary, not by the agent, for the same reason the decision is · a probabilistic component cannot be trusted to report honestly on itself. On its own the record prevents nothing; its value is reach. It covers the cases that cannot be prevented deterministically, and the clearest of those is aggregation: several pieces, each individually within someone's reach, that together reveal something none of them did alone. A per-piece rule cannot see that coming. A record can show it afterward · this requester pulled these pieces, in this window, and their combination crossed a line. What cannot be blocked becomes at least **detectable and attributable**, which is the difference between an incident you can investigate and one you never learn about.

## 3. The workspace · where the agents meet

All of this has to live somewhere. The workspace is the shared space where several people and their agents meet · and, crucially, do not share everything in it. Labels carve one space into private and shared regions: being stored in the same place is not the same as being visible. My private notes, my neighbor's private notes, and the part we work on together all sit in the same workspace, and the labels · not separate folders, not separate servers · decide who sees which.

It is also where "who holds which compartments" lives, and it lives in a deliberately un-centralized way. There is no global directory of everyone's clearances to build and keep in sync. Each owner declares only their own compartments · a small list they control, over their own namespace · and that is enough, because a requester only ever needs to prove the compartments relevant to the piece in front of it. Nobody has to hold the whole picture.

Two things, then, define the space: the **protocol** (what may cross) and the **traceability** (what did). Everything else · how each person configures, runs, or orchestrates their own agents inside it · is left open on purpose. The workspace is less a particular tool than a place where these boundaries hold regardless of the tools each side brings to it.

## Why it matters here

The closed, single-owner case barely needs any of this · a folder and a habit usually do the job. What forces it is the open, shared case that agent-to-agent communication creates: a platform where many organizations and people hold overlapping-but-not-identical knowledge, teams that must share to get work done without exposing everything, agents acting on behalf of different people at the same time. There, a norm written per relationship neither scales nor binds, while a label that travels with the data does both. It is, in the end, the enforcement side of what the semantic-boundaries research concluded · the human decides what is private, and the machine's only job is to hold that line, the same way every time.

## Decisions taken, paths set aside

- Inside a space that is already trusted, the boundary is enforced by write-controlled labels · only an owner writes their own · not by cryptography. Defending against a compromised host is a separate, heavier problem, set aside here.
- No central directory of who-knows-what. Each owner declares only their own compartments; there is nothing global to agree on or maintain.
- Identity · proving you are who you say · is treated as an external dependency, not part of this. The model needs only a verified identifier and the compartments it carries; how those are proven is out of scope.

## Open questions

- **Aggregation** · pieces individually within reach that combine into something more. Per-piece checks miss it (also open in the main coordination notes).
- **Crossing a trust boundary** · a boundary holds only where the runtime is controlled. Once a piece is inside someone else's runtime, the guarantee lapses.
- **Over-classification** · a cautious union drifts toward marking everything maximally restricted. When it is safe to lower a label again is unresolved.

See the [coordination notes](README.md) for the surrounding model · mandates, boundary customs, and the five protocols.

## Concrete implementation

[DBP (Data Boundary Protocol)](https://github.com/JoseEstevez520/DBP) is a reference implementation of these ideas. It provides deterministic boundary checks, label-based compartment access, heritage (label union on derived data), an immutable audit trace, and R7 escalation for human-in-the-loop overrides. Implemented in Python with 292 tests, a 16-agent deployment system, and performance benchmarks (>50K checks/sec).
