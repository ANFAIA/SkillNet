"""Lesson routes: update lesson title/content for draft courses, and
mark lessons as completed by employees."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.deps.auth import AdminUser, CurrentUser
from src.deps.db import DBSession
from src.models import ContentStatus, EnrollmentStatus
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.lesson_progress_repo import LessonProgressRepository
from src.repositories.lesson_repo import LessonRepository
from src.schemas.course import LessonRead, LessonUpdate
from src.schemas.exercise import ExerciseRead
from src.services.enrollment_service import EnrollmentService

router = APIRouter(prefix="/lessons", tags=["Lessons"])


@router.put("/{lesson_id}", response_model=LessonRead)
async def update_lesson(
    admin: AdminUser,
    db: DBSession,
    lesson_id: uuid.UUID,
    body: LessonUpdate,
) -> LessonRead:
    repo = LessonRepository(db)
    lesson = await repo.get_with_course(lesson_id)
    if lesson is None or lesson.module.course.org_id != admin.org_id:
        raise NotFoundError("lessons", str(lesson_id))

    course = lesson.module.course
    if course.status != ContentStatus.DRAFT:
        raise ConflictError("Only draft courses can be edited")

    changes = body.model_dump(exclude_unset=True)
    if changes:
        lesson = await repo.update(lesson, **changes)
    await db.commit()

    exercises = [
        ExerciseRead(
            id=ex.id,
            type=ex.type.value,
            content=ex.content,
            position=ex.position,
        )
        for ex in lesson.exercises
    ]
    return LessonRead(
        id=lesson.id,
        title=lesson.title,
        content=lesson.content,
        position=lesson.position,
        exercises=exercises,
    )


@router.post("/{lesson_id}/complete", status_code=200)
async def complete_lesson(
    user: CurrentUser,
    db: DBSession,
    lesson_id: uuid.UUID,
) -> dict:
    """Record that the current user has completed a lesson.

    A lesson without exercises is marked complete immediately.  A lesson
    with exercises is only marked complete if every exercise has at least
    one passing attempt.  If that condition is not met the endpoint
    returns ``{"completed": false}`` without error.

    Also transitions the enrollment from ``assigned`` to ``in_progress``
    on the first lesson visit.
    """
    lesson_repo = LessonRepository(db)
    lesson = await lesson_repo.get_with_course_and_exercises(lesson_id)
    if lesson is None or lesson.module.course.org_id != user.org_id:
        raise NotFoundError("lessons", str(lesson_id))

    course = lesson.module.course
    enrollment_repo = EnrollmentRepository(db)
    exercise_repo = ExerciseRepository(db)
    enrollment = await enrollment_repo.get_by_user_and_course(user.id, course.id)
    if enrollment is None:
        raise ForbiddenError("You are not enrolled in this course")

    # Enforce sequential progression: the previous lesson (by module
    # position, then lesson position) must be completed before this one.
    course_repo = CourseRepository(db)
    full_course = await course_repo.get_detail(course.id, user.org_id)
    if full_course is not None:
        ordered = sorted(
            [
                (mod, les)
                for mod in full_course.modules
                for les in mod.lessons
            ],
            key=lambda pair: (pair[0].position, pair[1].position),
        )
        lesson_index = next(
            (i for i, (_, les) in enumerate(ordered) if les.id == lesson_id),
            None,
        )
        if lesson_index is not None and lesson_index > 0:
            prev_lesson = ordered[lesson_index - 1][1]
            progress_repo_check = LessonProgressRepository(db)
            prev_visited = await progress_repo_check.completed_lesson_ids(
                user_id=user.id, lesson_ids=[prev_lesson.id]
            )
            if prev_lesson.id not in prev_visited:
                raise ConflictError(
                    "You must complete the previous lesson before this one"
                )
            # Also check that the previous lesson's exercises are all passed.
            if prev_lesson.exercises:
                prev_ex_ids = [ex.id for ex in prev_lesson.exercises]
                prev_passed = await exercise_repo.passed_exercise_ids(
                    user_id=user.id, exercise_ids=prev_ex_ids
                )
                if not all(eid in prev_passed for eid in prev_ex_ids):
                    raise ConflictError(
                        "You must complete the previous lesson before this one"
                    )

    # Transition assigned -> in_progress on first lesson visit.
    if enrollment.status == EnrollmentStatus.ASSIGNED:
        enrollment.status = EnrollmentStatus.IN_PROGRESS
        enrollment.started_at = datetime.now(timezone.utc)

    # Check exercise requirements.
    lesson_exercise_ids = [ex.id for ex in lesson.exercises]
    if lesson_exercise_ids:
        passed = await exercise_repo.passed_exercise_ids(
            user_id=user.id, exercise_ids=lesson_exercise_ids
        )
        if not all(eid in passed for eid in lesson_exercise_ids):
            await db.commit()
            return {"completed": False, "reason": "exercises_pending"}

    # Upsert lesson progress.
    progress_repo = LessonProgressRepository(db)
    existing = await progress_repo.get_by_user_and_lesson(user.id, lesson_id)
    if existing is None:
        await progress_repo.create(user_id=user.id, lesson_id=lesson_id)

    # Recompute enrollment progress and auto-complete if 100%.
    course_repo = CourseRepository(db)
    svc = EnrollmentService(enrollment_repo, course_repo, exercise_repo, progress_repo)
    progress = await svc.compute_progress(enrollment=enrollment, org_id=user.org_id)
    if (
        progress is not None
        and progress >= 1.0
        and enrollment.status != EnrollmentStatus.COMPLETED
    ):
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = datetime.now(timezone.utc)
        enrollment.score = progress

    await db.commit()
    return {"completed": True, "progress": progress}
