---
title: "Library and talent (admin)"
order: 19
section: "extensibility"
---

# Admin library and talent record

**Status:** product decision and initial implementation
**Scope:** course organization and basic training traceability
**Out of scope:** personalization, positions, candidate recommendation, and skill graphs

## Goal

SkillNet separates two administrative questions:

- **Library:** what courses the organization has and how they are found.
- **Talent:** what courses each person has assigned or completed, and what skills they have gained.

This first version is deliberately a record-keeping one. It does not attempt to infer job
performance or decide whether a person is a good fit for a position.

## Library

Courses can belong to an optional administrative folder. Folders are flat in this first version
and do not control permissions, generation, publishing, or enrollment.

The content screen offers:

- search by title or description;
- filter by folder and status;
- virtual views "All" and "Unorganized";
- creation, renaming, and safe deletion of folders;
- moving a course between folders.

A folder that contains courses is not implicitly deleted, nor does it delete its courses.

## Course skills

During schema pre-generation, the same quick response that proposes its nodes also returns
between two and six observable course skills. A skill is expressed as an action ("Configure a
locker"), not as a topic ("Locker").

Suggestions are editable and do not create taxonomy until the administrator confirms the course.
When persisted:

1. an existing organization skill is reused when its normalized name matches;
2. a new one is created when it does not exist;
3. the course's `course_skills` relation is replaced atomically.

At this stage skills belong to the course, not to individual nodes. `course_nodes.skill_id` is
kept for compatibility, but it is not part of this product flow.

## Talent record

Completing a course grants the user its `course_skills` via the existing `user_skills` mechanism.
The initial interface can present skill possession without turning the internal `low | medium |
high` levels into a precise measurement claim.

The administrator can query:

- **People:** assigned, in progress, completed, progress, and skills.
- **Person detail:** courses with status/progress, and skills with their originating course when
  the source is a completion.
- **Courses:** participants and aggregate status.
- **Skills:** related people and courses.

No second progress system is added. Talent projects enrollments, dynamic progress, and existing
`user_skills`.

## Architectural boundaries

- Folders organize courses; they do not organize or grant skills.
- Skills describe what a course grants; they do not modify render personalization.
- Talent is a projection of existing data; it does not write progress or mastery.
- Routes always apply the authenticated organization's scope.
- Skill resolution and creation live in the service, not in React components or routes.
- Replacing a course's skills is a complete, atomic operation to avoid partial states.

## Deferred evolution

Criteria, evidence, relationships, validity, job profiles, or explainable queries may be added
later. None of those concepts should be anticipated with generic fields in this version. A future
need will be modeled as a separate layer on top of the current record.
