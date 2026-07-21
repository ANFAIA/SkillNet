"""ORM models. Importing this package registers every table on Base.metadata."""

from src.models.access_token import AccessToken
from src.models.base import Base, TimestampMixin, UUIDMixin
from src.models.chat_message import ChatMessage
from src.models.chat_session import ChatSession
from src.models.course import ContentStatus, Course
from src.models.document import Document, DocumentStatus
from src.models.document_chunk import DocumentChunk
from src.models.enrollment import Enrollment, EnrollmentStatus
from src.models.exercise import Exercise, ExerciseType
from src.models.exercise_attempt import ExerciseAttempt
from src.models.generation_job import (
    GenerationJob,
    GenerationOutput,
    GenerationStep,
)
from src.models.lesson import Lesson
from src.models.lesson_progress import LessonProgress
from src.models.module import Module
from src.models.organization import Organization
from src.models.user import LearningProfile, User, UserRole

__all__ = [
    "Base",
    "UUIDMixin",
    "TimestampMixin",
    "AccessToken",
    "Organization",
    "User",
    "UserRole",
    "LearningProfile",
    "Document",
    "DocumentStatus",
    "DocumentChunk",
    "Course",
    "ContentStatus",
    "Module",
    "Lesson",
    "LessonProgress",
    "Exercise",
    "ExerciseType",
    "Enrollment",
    "EnrollmentStatus",
    "ExerciseAttempt",
    "GenerationJob",
    "GenerationOutput",
    "GenerationStep",
    "ChatSession",
    "ChatMessage",
]
