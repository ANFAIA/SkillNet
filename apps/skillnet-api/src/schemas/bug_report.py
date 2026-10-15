"""Request/response schemas for bug reports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BugReportCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    page_path: str | None = Field(default=None, max_length=500)
    # Browser, screen width, theme and language, sent by the web app itself.
    environment: str | None = Field(default=None, max_length=300)


class BugReportQueued(BaseModel):
    id: uuid.UUID
    status: Literal["queued"] = "queued"


class BugReportRead(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    severity: str | None = None
    reason: str | None = None
    issue_url: str | None = None
    page_path: str | None = None
    environment: str | None = None
    created_at: datetime


class BugReportAdminRead(BugReportRead):
    body: str
    author_id: uuid.UUID | None = None


class BugReportDiscard(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
