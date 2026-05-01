"""Schemas for authenticated account settings flows."""

from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.auth import validate_password_strength


class SettingsProfileUpdate(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    full_name: str = Field(default="", max_length=200)
    email: EmailStr
    phone: str = Field(default="", max_length=50)
    address: str = Field(default="", max_length=200)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9_-]{3,30}", normalized):
            raise ValueError("Username may only contain letters, numbers, underscores, and hyphens.")
        return normalized

    @field_validator("full_name", "phone", "address")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        return (value or "").strip()


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password_strength(value)

    @model_validator(mode="after")
    def validate_passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        if self.current_password == self.new_password:
            raise ValueError("New password must be different from your current password")
        return self


class AccountDeleteRequest(BaseModel):
    confirmation: str
    current_password: str = Field(..., min_length=1)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if normalized != "DELETE":
            raise ValueError('Type DELETE to confirm account deletion.')
        return normalized
