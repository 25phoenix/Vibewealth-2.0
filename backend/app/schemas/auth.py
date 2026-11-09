"""Explicit request and safe response schemas for HTTP authentication."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str
    display_name: str | None = Field(default=None, max_length=120)
    account_type: Literal["cash", "bank", "wallet"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None


class CsrfTokenResponse(BaseModel):
    csrf_token: str
