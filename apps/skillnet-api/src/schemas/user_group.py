"""Contracts for flat people groups."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UserGroupWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        clean = " ".join(value.split())
        if not clean:
            raise ValueError("must not be blank")
        return clean


class UserGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    #: Everyone in the group, deactivated accounts included — membership is not the same
    #: question as "who would this assignment enrol". The assignment result reports the
    #: difference, at the moment it matters.
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class UserGroupMembersUpdate(BaseModel):
    """One membership edit: who joins and who leaves, together.

    Both halves in one request because that is how the screen produces them — a page of
    ticks yields additions and removals at once — and two requests could half-apply.

    The caps are the transaction's size, not the group's: a group may hold any number of
    people, but one edit moves at most this many. That keeps a single request bounded
    without limiting what a group is.
    """

    add: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    remove: list[uuid.UUID] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def not_empty(self) -> "UserGroupMembersUpdate":
        if not self.add and not self.remove:
            raise ValueError("Provide at least one id in add or remove")
        return self


class UserGroupMembersResult(BaseModel):
    added_count: int
    removed_count: int
    member_count: int
