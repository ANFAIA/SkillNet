---
title: "Library and talent (admin)"
order: 19
section: "extensibility"
---

# Admin library and talent registry

**Status:** product decision and initial implementation
**Scope:** course organization and basic training traceability
**Out of scope:** personalization, job roles, candidate recommendation, and competency graphs

## Goal

SkillNet separates two administrative questions:

- **Library:** what courses the organization has and how they're found.
- **Talent:** what courses each person has assigned or completed, and what skills they've
  obtained.

This first version is deliberately record-keeping. It doesn't attempt to infer job
performance or decide whether a person is fit for a role.

## Library

Courses can belong to an optional administrative folder. Folders are flat in this first
version and don't control permissions, generation, publishing, or enrollment.

The content screen offers:

- search by title or description;
- filter by folder and status;
- virtual views "All" and "Unorganized";
- creation, renaming, and safe deletion of folders;
- moving a course between folders.

A folder containing courses is not implicitly deleted, nor does it delete its courses.

## Course skills

During schema pre-generation, the same quick response that proposes its nodes returns
between two and six observable course skills. A skill is expressed as an action
("Configure a locker"), not as a topic ("Locker").

Suggestions are editable and don't create taxonomy until the admin confirms the course.
When persisted:

1. an existing organization skill is reused when its normalized name matches;
2. a new one is created when it doesn't exist;
3. the course's `course_skills` relationship is atomically replaced.

At this stage, skills belong to the course, not to individual nodes. `course_nodes.skill_id`
is kept for compatibility, but it's not part of this product flow.

## Talent registry

Course completion grants the user its `course_skills` via the existing `user_skills`
mechanism. The initial interface can present skill possession without turning the internal
`low | medium | high` levels into a precise measurement claim.

The admin can view:

- **People:** assigned, in progress, completed, progress, and skills.
- **Person detail:** courses with status/progress and skills with their originating course
  when the source is a completion.
- **Courses:** participants and aggregate status.
- **Skills:** related people and courses.

No second progress system is added. Talent projects enrollments, dynamic progress, and
existing `user_skills`.

## Architectural boundaries

- Folders organize courses; they don't organize or grant skills.
- Skills describe what a course grants; they don't modify render personalization.
- Talent is a projection of existing data; it doesn't write progress or mastery.
- Routes always enforce the authenticated organization's scope.
- Skill resolution and creation live in the service, not in React components or routes.
- Replacing a course's skills is a complete, atomic operation to avoid partial states.

## Deferred evolution

Criteria, evidence, relationships, validity, job profiles, or explainable queries can be
added later. None of these concepts should be anticipated with generic fields in this
version. A future need will be modeled as a separate layer on top of the current registry.
