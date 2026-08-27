"""Course packages: a directory that installs as a course, with no LLM call."""

from src.services.course_package.format import (
    HANDWRITTEN_GENERATOR,
    PACKAGE_FORMAT,
    PackageError,
)
from src.services.course_package.read import CoursePackage, PackageNode, read_package

__all__ = [
    "HANDWRITTEN_GENERATOR",
    "PACKAGE_FORMAT",
    "CoursePackage",
    "PackageError",
    "PackageNode",
    "read_package",
]
