---
title: "Audience modes"
order: 18
section: "extensibility"
---

# Audience modes: Organization and Individual

> **Status: implemented (first vertical).** The mode is a stable deployment capability,
> `organizations.workspace_mode` (migration 0017), fixed when the organization is created
> from `WORKSPACE_MODE` (default `organization`) and never inferred from the number of
> users. The document still describes the product direction; what has already been built
> is summarized below under "Implementation status". It does not imply creating a
> commercial website, a multi-tenant SaaS, or two separate products.

## Decision

SkillNet will have a single product core and two usage modes:

| Internal mode | Product label | For whom | Space owner |
|---|---|---|---|
| `organization` | **Company** / **Organization** | Companies, teams, classes, academies, associations, and other groups | An admin person manages content and participants |
| `individual` | **Individual** | A single person who installs and uses SkillNet for themselves | The same person administers their content and learns |

There is no separate mode for `class`. A class is a use case of `organization`: it has a
responsible person, a set of participants, shared content, and collective tracking. The
differences between a company and a class belong to language, templates, and configuration,
not to the core architecture.

Nor will the second mode be called `user`. Every person in the system is a user; using that
term for an installation type would make the code, the documentation, and the marketing
ambiguous.

## What stays common

Both modes share the flow that constitutes the product:

1. onboarding one's own documents;
2. turning them into courses and reference material;
3. learning via adapted experiences;
4. retaining progress, preferences, and personal memory;
5. regenerating or updating learning when sources change.

Generation, the adaptive runtime, exercises, tutoring, source traceability, and profile
persistence must not fork by mode. Differences are resolved via visible capabilities and
permissions, not by maintaining two applications.

## Experience by mode

### Organization

Keeps the current product and its main roles:

- an admin person uploads documents and reviews generated content;
- can invite participants, assign courses, and view collective progress;
- has access to a shared library, skills, talent, and team reports;
- each participant keeps their progress and receives a personalized experience;
- the organization controls deployment configuration and its data.

The specific label can change per vertical (`Company`, `Class`, `Academy`, or `Team`)
without altering the internal mode.

### Individual

The person is simultaneously the space's owner and the learner:

- uploads their own documents;
- creates, reviews, and publishes courses for themselves;
- configures the model and deployment the way an admin would;
- retains progress, preferences, history, and personalization across courses;
- sees no employee management, talent, collective assignments, or organization reports;
- doesn't need to create secondary users to complete their own content.

`Individual` is not a throwaway or memory-less edition. Personalization and persistence are
precisely part of its value: SkillNet learns how that person studies and uses that
information in their later courses.

## Recommended technical model

The extension doesn't require removing `organizations` or introducing multi-tenancy. Each
deployment keeps a single organization row:

- in `organization` mode, it represents the company, class, or team;
- in `individual` mode, it represents the owner's personal space.

When implemented, the mode can be stored as a stable deployment capability, e.g.
`workspace_mode = organization | individual`. It should not be repeatedly inferred from the
number of users.

The frontend can derive navigation and available features from that value. The API must
still enforce permissions server-side: hiding a section is not an authorization mechanism.

The first setup should ask only for the usage mode and the data needed to create the owner.
Switching from `individual` to `organization` can be supported as a non-destructive
extension; the reverse path requires handling participants, assignments, and collective
data and therefore should not be assumed to be automatic.

## Horizontal product, vertical marketing

SkillNet remains a horizontal product: it turns one's own knowledge into adaptive learning.
Commercial segmentation doesn't need to become technical segmentation.

There can be several landings or vertical narratives on the same product:

| Page or campaign | Problem it tells | Product mode |
|---|---|---|
| Companies | Onboarding, procedures, and internal knowledge | `organization` |
| Academies or classes | Own teaching material and student tracking | `organization` |
| Consultancies | Delivering training based on client documentation | `organization` |
| Individual | Studying one's own documents with memory and adaptation | `individual` |

These pages can use different examples, images, testimonials, and calls to action. They
must not promise exclusive features that would require forking the product. A vertical is
an entry point and a marketing priority, not an independent edition.

## Common storytelling

The core story must work in both modes and start from knowledge, not from the org chart:

> SkillNet turns the documents you already have into learning that adapts to each person.

It then gets specific by audience:

- **Company:** your organization's knowledge becomes training for every team member.
- **Individual:** your documents become courses that remember how you learn.

This preserves a single brand and prevents the extension from diluting the initial market.
Marketing can keep concentrating budget and messaging on SMBs, even though the downloadable
software covers more use cases.

## Out of scope for this decision

- offering SkillNet as a hosted or multi-tenant SaaS;
- creating a different application per vertical;
- building a marketing website now;
- immediately renaming existing roles, tables, or routes;
- designing billing, licensing, or pricing per mode;
- turning `class` into a separate root entity.

## Criteria for a future implementation

The extension will be well resolved if:

1. an individual installation can complete the entire cycle without encountering HR or
   headcount-management concepts;
2. an organization installation retains all current features;
3. content, progress, and personalization use the same services in both modes;
4. adding a new marketing vertical doesn't require modifying the domain model;
5. a person can extend their individual space to an organization without losing their
   courses or history;
6. data isolation and ownership remain those of a self-hosted, single-organization
   deployment.

## Boundary of new features

Audio in chat, live conversations, the mascot, and podcasts can be reused in both modes.
This decision does not by itself add more features to the enterprise product. The direction
note is in [conversational-modalities.md](conversational-modalities.md).

## Implementation status

First vertical built (keeps `organization` intact by default):

- **Data.** `organizations.workspace_mode` (enum `workspace_mode`, migration 0017), default
  `organization`. No multi-tenancy: one row per deployment, as before.
- **Bootstrap.** `bootstrap.ensure_organization` reads `WORKSPACE_MODE` (env, default
  `organization`) only when creating the organization; existing deployments keep their
  value.
- **API.** The mode travels to the client in `GET /auth/me` (`workspace_mode`) and in
  `GET /settings`. Collective surfaces — employees (create/list/reset), talent, stats,
  course assignment, and the skills catalog — go through the `require_organization_workspace`
  dependency, which responds **404** in `individual`: those concepts don't exist there.
  Authorization stays on the server; hiding it in the SPA is UX.
- **Frontend.** Navigation is derived from the mode (`useWorkspaceMode`). In `individual` the
  owner is an `admin` who also learns: the sidebar omits Employees and Talent, "Content" is
  presented as "My courses", and the company dashboard is replaced by a personal home. The
  owner goes through the learner onboarding once to get a profile and personalization.
- **Roles.** No new role: `individual` reuses `admin` as owner-learner.
- **Seed.** `individual` mode is set via `WORKSPACE_MODE=individual` in `.env` before the
  first boot, or via the `/setup` wizard. (The old dedicated seed
  `src.seed_demo_individual`, built on the now-removed bakery, was removed.)

First boot via UI: `GET /setup/status` + `POST /setup` (public, closed as soon as a user
exists) and the `/setup` wizard in the SPA choose the mode and create the owner
(auto-login → onboarding). The `.env` (`WORKSPACE_MODE` + `ADMIN_EMAIL/PASSWORD`) remains the
equivalent headless path.

Pending (next phases): polish the owner onboarding, and the non-destructive
`individual → organization` extension.
