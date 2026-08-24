---
title: "Multi-agent coordination"
order: 57
section: "research"
---

# Multi-Agent Coordination

## A new problem

There's a paradigm shift happening. AI coding agents generate enormous amounts of code. Projects that used to take weeks appear in hours. Repositories grow faster than any team can review. Hosting platforms hit rate limits because agents make too many requests. Repos break under the volume of automated changes.

This is the reality of working with agents today, and it works reasonably well for **one person with one agent**. But the moment you scale to a team (multiple people, each with their own agents, working on the same codebase or knowledge base), everything breaks down. Whose agent has priority? What happens when two agents modify the same file? How do you prevent one person's agent from accessing another person's private context?

There is no system for this. Git tracks code changes but knows nothing about agent intent. RBAC controls access to resources but not to knowledge context. MCP connects agents to tools but says nothing about coordination between agents. The gap is **governance for teams of agents**.

This research explores that gap, from the specific problem of authority ("whose agent is this?") to the broader question of how multiple humans and multiple agents coexist on shared projects.

---

## Exploring organizational structures

The first question was: **what structures do people use in the real world to organize authority?** We explored several models to see which one fits the reality of multiple humans working with multiple agents.

**Trees (hierarchies).** The simplest model. One boss at the top, branches below. But agents don't have a single boss. When two people use the same agent, the tree breaks because a node can't hang from two parents.

**Graphs.** More flexible than trees because they allow multiple connections. But a graph alone doesn't say anything about authority, permissions, or who decides what. It's a data structure, not a governance model.

**Holons.** A recursive structure where each human is the root of their own tree, with agents branching below. Three interaction points: declare intent, approve promotion, decide by exception. This seemed promising because it resolves the bottleneck by design. You enter at three points, not watching a screen.

But holons break the moment a sub-agent serves two users. A tree with a node hanging from two parents is not a tree. "Whose holon is this?" has no answer, and without an owner: who approves its promotions? What permissions does it operate under? To whom does it escalate?

## The discovery: mandates over ownership

The exploration led to a key realization. The foundational error in all these structures was modeling authority as **belonging** (the agent is someone's property) when it should be modeled as a **relationship** (the agent acts on someone's behalf, for a specific purpose).

- "Whose is it?" forces a single owner.
- "On whose behalf does it act, and for what purpose?" admits multiple principals without contradiction.

The primary design unit becomes the **mandate**: on whose behalf does this agent act, with what permissions, toward what goal, within what limits.

- An agent can carry **multiple mandates** simultaneously.
- A sub-agent serving two users carries two mandates, one from each.
- Its **authority is the intersection** of what both mandates allow.

| Concept | With Mandates |
|---------|---------------|
| **Permissions** | Intersection of mandates, not inheritance from an owner |
| **Promotion** | Approved by all affected principals, not a single owner |
| **Escalation** | Escalates to whoever corresponds based on which mandate triggered the exception |
| **Structure** | A network of mandates, not a tree with a human vertex |

### The Irreducible Limit

When two mandates contradict (A wants one thing, B wants the opposite), the intersection of permissions does not say what to do, only what is allowed. Architecture distributes permissions and detects conflicts, but **does not decide between opposing wills**. That remains with the humans. Same problem any human mediator faces.

### Formal Representation (Open)

How should mandates be formally represented?

- **Tuple:** `(principal, agent, objective, permissions, limits)`
- **Graph:** Nodes are agents and humans, edges are mandates with attributes
- **Contract:** A declarative document specifying terms

The versioning unit shifts accordingly: not the artifact (Git) or the intention alone, but the **mandate** (who authorized what, for what purpose, within what limits).

### Asynchronous Work

The "human watching a screen" model is a design artifact, not a natural law. The alternative: agents run in the background, deliver results with hierarchical summaries (10-second overview -> 1-minute detail -> full trace), a tray of pending decisions, and escalation by exception. The human becomes a director who reviews in batches and decides at fork points.

> "A summary is a lossy compression. Whoever controls what gets compressed controls what you review." The complete trace must always be available.

---

## Part 2: Compartmentalized Access

### The Problem

Multiple people work with multiple agents. They do not share their entire knowledge base. The overlaps are asymmetric:

```
Person A:  knows {X, Y}
Person B:  knows {X}
Person C:  knows {X, Y, Z}
```

Factory models (hierarchical tree) fail because overlaps are not hierarchical. Clean room models (shared center) fail because there is no center.

### Three Axes

**1. Compartments (need-to-know): ESSENTIAL.** Horizontal and non-hierarchical. A compartment is a labeled body of knowledge. Access is not granted by rank or trust, but because the specific task requires it.

**2. Dissemination: ADD WHEN NEEDED.** Directional. A piece from compartment X can carry a label "shareable with Person B" or "does not leave my domain." Only needed when there are exceptions within a compartment.

**3. Clearance Level: PROBABLY NOT NECESSARY.** In most multi-agent scenarios, the problem is about partitions (who knows what), not degrees (how secret something is).

### Translation to Agent Systems

**Boot (Read-In).** Launch an agent with only the compartments its task requires. **Advantage over humans:** An agent can be instantiated without access to certain knowledge. Need-to-know becomes perfect, not approximate.

**Boundary (Customs).** When the agent emits something outward, a control point checks dissemination labels. **Critical:** This check lives at the BOUNDARY, not inside the agent. You cannot trust a probabilistic agent to self-censor reliably.

**Record (Audit).** Every crossing leaves a trace: what piece, what label authorized it, in what direction.

```
Control is NOT inside the agent (unreliable).
It is at BOOT (what it can see) and at the BOUNDARY (what it can emit).
The agent in between can be as smart and fallible as it wants.
```

### Minimum Viable Model

```yaml
---
compartment: project_research
---
```

Pieces labeled with compartments + agents with allowed compartments + boot-time filter + boundary customs. That alone provides asymmetric access control.

---

## Part 3: Five Governance Protocols

Five protocols cover the full governance surface, listed in implementation priority order.

### Protocol 1: Sharing. What Crosses Between Agents and People

**Priority: CRITICAL. Current state: Hard layer exists (DBP). Soft layer remains open.**

The boundary between compartments is an adaptive filter:

| Level | What Happens |
|-------|-------------|
| PASS | Crosses as-is |
| PASS REDACTED | Crosses with sensitive data removed |
| PASS SUMMARIZED | The conclusion crosses, not the detail |
| PASS WITH NOTICE | Crosses but is logged |
| ASK | Escalates to the human |
| BLOCK | Only in clear, irreversible cases |

**Two-Layer Implementation:**

```
Hard layer (scanner):       Deterministic filter by labels -> fast, free, reliable
Soft layer (customs agent): Agent that reviews what passes -> detects aggregation, nuance
```

**Implementation:** [DBP (Data Boundary Protocol)](https://github.com/JoseEstevez520/DBP) provides the hard layer: deterministic label + clearance checks at the boundary, with automatic heritage for derived data. The soft layer (customs agent) and multi-user governance remain open.

### Protocol 2: Knowledge. What Each Agent Knows

**Priority: CRITICAL. Current state: _context.md and skills (partial).**

Defines what compartments an agent can access and what context is deliberately excluded. A code reviewer with a clean slate judges better than one loaded with the author's reasoning. Deliberate exclusion is a design decision, not an error.

### Protocol 3: Traces. What Gets Recorded

**Priority: Important. Current state: agentvcs (single-user) + git.**

Records what the agent did, why, what it read, what it shared, and what label authorized each crossing. Multi-user needs: access traces, dissemination traces, mandate traces.

### Protocol 4: Identity. Who Each Agent Is

**Priority: Useful. Current state: AGENTS.md and skills.**

What's missing: a formal identity that persists between sessions and that other agents or systems can query.

### Protocol 5: Escalation. When to Ask the Human

**Priority: Useful. Current state: Hooks and tool-call approval.**

Escalate when: information is unlabeled, aggregation is suspected, protocols conflict, or an action is irreversible. What's missing: clear criteria and asynchronous escalation when the human is not present.

---

## Reliability Through Isolation

When sub-agents are independent, error rates **multiply**:

```
1 agent with 1% error:       1% failure rate
3 independent agents:        0.01 x 0.01 x 0.01 = 0.0001% failure rate
```

The key word is **independent**: they do not share context. If the reviewer read the same material as the author, it carries the same bias.

The compartment model was initially motivated by access control. But the isolation it creates has a second property: it makes verification genuinely independent. **Isolation is not a security limitation. It is what makes verification work.**

**Caveat:** Error multiplication only holds under true independence. Shared training data biases or correlated failure modes raise the actual joint failure rate above naive multiplication.

---

## What Already Exists (Informally)

```
CLAUDE.md    -> identity + knowledge protocol
AGENTS.md    -> identity protocol (capabilities)
_context.md  -> knowledge protocol (project compartment)
Skills       -> knowledge protocol (per-task)
"Don't touch" -> sharing protocol (informal hard boundary)
Hooks        -> escalation protocol (deterministic validation)
Background   -> asynchronous work (partial)
Sub-agents   -> reliability through isolation (partial)
```

It works for one user. It does not scale to teams.

## Industry Gap

| Exists Today | Does Not Exist |
|-------------|----------------|
| RBAC (role-based permissions) | Per-task compartments for agents |
| OAuth scopes | Adaptive customs between agents |
| agentvcs (single-user) | Need-to-know applied to LLM context |
| MCP (tooling) | Control over what knowledge an agent sees |
| LangGraph (orchestration) | Multi-agent multi-user governance |

## Related work

[agentvcs](https://github.com/EvolvingAgentsLabs/agentvcs) (Apache-2.0) explores versioning for autonomous agents. It covers the single-user single-agent case; the multi-user coordination problem described here is a different layer.

[DBP (Data Boundary Protocol)](https://github.com/JoseEstevez520/DBP) (Apache-2.0) implements the deterministic boundary model explored in this research. It provides label-based compartments, set-inclusion boundary checks, heritage, immutable audit traces, and escalation for human override. See the [agent communication doc](agent-communication.md) for the conceptual model and the DBP repo for the reference implementation.

## Open Questions

1. How should mandates be formally represented? Tuple, graph, or contract?
2. How are mandate conflicts detected before they occur?
3. Who arbitrates contradictory mandates?
4. Are mandates static or do they evolve as work progresses?
5. How does it scale from 2 users to 500?
6. How does it integrate with agentvcs?
7. Do compartments map to work units or knowledge sources?
8. How is aggregation handled, specifically when pieces A and B are individually innocuous but reveal something sensitive combined?
9. What format should traces take?

---

## Deep dive

- [Communication between agents](agent-communication.md) · when my agent talks to my neighbor's, what may cross · making the boundary deterministic rather than an advisory norm, across the protocol, the traceability, and the workspace.
