from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


MemoryType = Literal["fact", "preference", "decision", "constraint", "goal", "lesson"]


class SessionCreate(BaseModel):
    title: str = Field(default="New conversation", max_length=120)
    owner_id: str = Field(default="demo-user", max_length=120)
    workspace_id: str = Field(default="default", max_length=120)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12_000)


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=3_000)
    memory_type: MemoryType = "fact"
    expires_at: datetime | None = None


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=3_000)
    memory_type: MemoryType | None = None
    expires_at: datetime | None = None
