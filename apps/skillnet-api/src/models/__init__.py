"""ORM models. Importing this package registers every table on Base.metadata."""

from src.models.access_token import AccessToken
from src.models.api_key import ApiKey
from src.models.audit_log import AUDIT_ACTIONS, AuditLog
from src.models.activity_definition import ActivityDefinition, ActivityFamily, ActivityState
from src.models.base import Base, TimestampMixin, UUIDMixin
from src.models.chat_message import ChatMessage
from src.models.chat_session import ChatSession
from src.models.course import (
    ArtifactGeneratePolicy,
    ContentStatus,
    Course,
    CourseDeliveryMode,
    CourseGenerationState,
    CourseImageSourcePolicy,
    CourseNavigationMode,
    CourseSchemaStatus,
    CourseTutorStyle,
)
from src.models.course_artifact_generator import CourseArtifactGenerator
from src.models.course_node import (
    CRITICALITY_THRESHOLDS,
    CourseNode,
    NodeCriticality,
)
from src.models.course_node_prerequisite import CourseNodePrerequisite
from src.models.course_skill import CourseSkill
from src.models.document import Document, DocumentOrigin, DocumentStatus
from src.models.document_chunk import DocumentChunk
from src.models.enrollment import Enrollment, EnrollmentStatus
from src.models.exercise import Exercise, ExerciseType
from src.models.exercise_attempt import ExerciseAttempt
from src.models.generation_job import (
    GenerationJob,
    GenerationOutput,
    GenerationStep,
)
from src.models.learner_activity_state import LearnerActivityState
from src.models.learner_node_state import (
    SCAFFOLD_BANDS,
    ErrorKind,
    LearnerNodeState,
    NodeState,
)
from src.models.learner_profile import (
    EMPTY_FORMAT_VECTOR,
    FORMAT_VECTOR_DIMENSIONS,
    LearnerExperience,
    LearnerProfile,
)
from src.models.learning_event import LearningEvent
from src.models.learning_experience import (
    ExperienceAttempt,
    ExperienceIntent,
    ExperienceVariant,
    ImplementationBinding,
    NormalizedEvidence,
)
from src.models.lesson import Lesson
from src.models.lesson_progress import LessonProgress
from src.models.media_artifact import (
    MediaArtifact,
    MediaArtifactStatus,
    MediaKind,
)
from src.models.llm_usage_log import USE_CASES, LlmUsageLog
from src.models.module import Module
from src.models.node_attempt import BLOOM_LEVELS, NodeAttempt
from src.models.node_feedback import DIFFICULTY_VALUES, NodeFeedback
from src.models.node_knowledge_pack import (
    NodeKnowledgePackRecord,
    NodeKnowledgePackStatus,
)
from src.models.course_folder import CourseFolder
from src.models.node_probe import NodeProbe
from src.models.node_render import NodeRender, NodeRenderStatus, UiFormat
from src.models.node_render_view import NodeRenderView
from src.models.organization import Organization, WorkspaceMode
from src.models.skill import Skill
from src.models.skill_category import SkillCategory
from src.models.source_image import SourceImage, SourceImageKind
from src.models.term_explanation import (
    TERM_CACHEABLE_MAX_LENGTH,
    TERM_CACHEABLE_MAX_TOKENS,
    TERM_MAX_LENGTH,
    TermExplanation,
)
from src.models.user import LearningProfile, User, UserRole
from src.models.user_group import UserGroup, UserGroupMember
from src.models.user_skill import SkillLevel, UserSkill

__all__ = [
    "Base",
    "UUIDMixin",
    "TimestampMixin",
    "AccessToken",
    "ApiKey",
    "Organization",
    "WorkspaceMode",
    "User",
    "UserRole",
    "LearningProfile",
    "Document",
    "DocumentOrigin",
    "DocumentStatus",
    "DocumentChunk",
    "Course",
    "CourseFolder",
    "ContentStatus",
    "ArtifactGeneratePolicy",
    "CourseArtifactGenerator",
    "CourseSkill",
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
    "Skill",
    "SkillCategory",
    "SkillLevel",
    "UserSkill",
    "ChatSession",
    "ChatMessage",
    # --- v2 dynamic courses ---
    "CourseDeliveryMode",
    "CourseGenerationState",
    "CourseImageSourcePolicy",
    "CourseNavigationMode",
    "CourseSchemaStatus",
    "CourseTutorStyle",
    "CourseNode",
    "CourseNodePrerequisite",
    "NodeCriticality",
    "CRITICALITY_THRESHOLDS",
    "LearnerProfile",
    "LearnerExperience",
    "FORMAT_VECTOR_DIMENSIONS",
    "EMPTY_FORMAT_VECTOR",
    "LearnerActivityState",
    "LearnerNodeState",
    "NodeState",
    "ErrorKind",
    "SCAFFOLD_BANDS",
    "LearningEvent",
    "ExperienceIntent",
    "ExperienceVariant",
    "ImplementationBinding",
    "ExperienceAttempt",
    "NormalizedEvidence",
    "NodeRender",
    "UiFormat",
    "NodeRenderStatus",
    "NodeRenderView",
    "NodeProbe",
    "NodeAttempt",
    "BLOOM_LEVELS",
    "NodeFeedback",
    "DIFFICULTY_VALUES",
    "NodeKnowledgePackRecord",
    "NodeKnowledgePackStatus",
    "TermExplanation",
    "TERM_MAX_LENGTH",
    "TERM_CACHEABLE_MAX_LENGTH",
    "TERM_CACHEABLE_MAX_TOKENS",
    "LlmUsageLog",
    "USE_CASES",
    "AuditLog",
    "AUDIT_ACTIONS",
    "ActivityDefinition",
    "ActivityFamily",
    "ActivityState",
    # --- rich media artifacts (NotebookLM spine) ---
    "MediaArtifact",
    "MediaKind",
    "MediaArtifactStatus",
    # --- named lists of people, for assigning training in bulk ---
    "UserGroup",
    "UserGroupMember",
    # --- images extracted from source documents ---
    "SourceImage",
    "SourceImageKind",
]
