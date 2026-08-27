# Course packages

A **course package** is a directory that installs as a complete, validated dynamic course
with no LLM call and no API key.

It exists because the expensive half of a course is not the screens — it is the knowledge
packs. Those are minutes of model time and real money per course, and until a package could
carry them they lived on exactly one machine and died with it. Regenerating the same course
on a second machine costs the same again and, because generation is not deterministic, does
not even produce the same course.

A package is two things at once, and deliberately the same format for both:

- **What a person writes.** Author the graph and the packs by hand and install them, with no
  model involved anywhere. This is the way to get a course that is genuinely good on the
  source material rather than as good as whatever model was on the key that day.
- **What an existing course is frozen into.** Export a generated course, and it installs
  elsewhere in seconds.

What a package never carries is the screens. Those stay generated live by the runtime, per
learner, exactly as they are for a course created through the wizard. A package prepares the
material; personalisation still happens at serving time.

## Layout

```
<slug>/
    course.json          course metadata, shared source pointers, the node graph
    packs/<node>.json    the atoms of one node, named after the node's slug
```

There is no Markdown in the package. `knowledge_pack.markdown.render_markdown` projects the
dossier deterministically from the contract, so a stored copy would be a second version of
the same thing, free to disagree with the atoms it claims to describe.

## The format is a serialization of contracts that already exist

`packs/<node>.json` expands into `NodeKnowledgePack` (`src/knowledge_pack/contracts.py`);
the node entries in `course.json` carry the same fields `PUT /courses/{id}/schema` already
accepts.

This is the decision the rest of the design hangs from. There is **no second definition** of
what a pack is, so:

- A package written by hand is validated by exactly the code that validates a generated one.
  Nothing can be authored that the pipeline would refuse.
- The two cannot drift apart later, because there is only one of them.
- `lint` is not a separate ruleset that has to be kept in step — it is the contract.

## Everything mechanical is derived, not authored

The on-disk shape uses short field names and fills in the rest, so writing a package stays
about the teaching material:

| Filled in for you | From |
|---|---|
| `provenance`, both digests | the material, hashed canonically |
| `excerpt_hash` of a source | the source descriptor (document, heading, locator, revision) |
| `objective` | the node's `mission` and `source_functions` |
| `required_fact_refs`, `required_safety_refs` | read off `must_preserve` |
| node and course ids | derived from the slugs (see below) |
| `status: ready`, `reviewed_at` | the install |

Nobody writes a SHA-256 into a JSON file, and the required-fact lists are read off the atoms
rather than kept by hand — a duplicated list of atom ids goes stale the first time an atom is
renamed.

## Identity comes from the package, not from the instance

A package installs as the **same course id and the same node ids on every machine**. Ids are
`uuid5` over the package and node slugs, so they are stable without anyone typing a UUID.

Two things depend on this:

- **Re-installing updates instead of duplicating.** Idempotency needs no registry table: the
  identity *is* the key.
- **A pre-generated screen still matches after the package moves.** `node_renders.cache_key`
  is keyed partly on `node_id`, so ids minted per install would throw away every warmed
  render the moment a package changed machines.

The pack's `node_id` is that UUID rather than the readable slug, because generated packs
carry `node_id=str(node.id)` and a second convention for one field is how two answers to the
same question get born.

**An exported package pins its ids explicitly** (`uuid` on the course and on each node) and
those win over the derived ones. An exported course's nodes already exist — their ids are in
the render cache key and in every learner's state — so re-installing must land on the course
that is already there, not on a new one wearing the same title.

One limitation follows from global ids: a package installs under one identity per instance,
so the same package cannot be installed into two organizations of one deployment. The
installer refuses that rather than corrupting either.

## Nodes are updated in place, never dropped and re-created

Deleting a node takes its learner state, attempts and renders with it. A node the package no
longer declares is **archived** instead, which is reversible; deleting it is not.

## Provenance is carried, never re-minted

An exported pack keeps the provenance of the pack it came from, and the database row is
labelled with the generator the pack itself claims — not with a constant. Round-tripping a
generated course through a package must not relabel its material as hand-written: that field
is the one thing that answers, months later, where the content came from.

Superseding is by node, not by fingerprint. After an install a node has exactly one `ready`
pack, so there is never a pair of them with nothing to say which one the course teaches from.

## What does not travel

Enrolments, progress, render history, `node_render_views` and chats. They belong to the
instance that produced them, not to the course.

Media (podcasts, infographics, extracted images) and document chunks with their embeddings
do not travel yet. Both are worth carrying later: media because it is the slowest thing to
produce and the only remaining reason a target machine needs a TTS or image key, and chunks
because without them the tutor loses its citations. A chunk bundle has to record the
embedding model it was built with — a 768-dimension bundle in a 384-dimension instance does
not fail, it silently degrades retrieval.

## Commands

See `RUNNING.md`. `lint` needs neither a database nor a key and runs on the host while a
package is being written; `export` and `install` run inside the container.

## Where the code lives

```
src/services/course_package/
    format.py     the on-disk shape <-> the contracts. The only place that knows both
    read.py       directory -> validated objects, accumulating every fault
    install.py    objects -> database, resolving organization and actor at install time
    export.py     database -> directory
scripts/course_package.py    the CLI
```

The engine is in `src/services/` rather than in the script so the application can install a
package too. `org_demo_seed` already pre-bakes a course for a brand-new organization the same
way; a package is that idea with the course moved out of Python and onto disk.
