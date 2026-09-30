from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str = Field(min_length=20)


class ResetPasswordRequest(TokenRequest):
    password: str = Field(min_length=12, max_length=128)


class ExchangeCodeRequest(BaseModel):
    code: str = Field(min_length=20)


class ProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)


class AvatarPatch(BaseModel):
    avatar_key: str | None = Field(default=None, max_length=1024)
    avatar_url: HttpUrl | None = None

    @model_validator(mode="after")
    def require_change(self):
        if "avatar_key" not in self.model_fields_set and "avatar_url" not in self.model_fields_set:
            raise ValueError("avatar_key or avatar_url is required")
        return self


class PromoteRequest(BaseModel):
    email: EmailStr
    reason: str | None = Field(default=None, max_length=500)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    role: str
    email_verified: bool
    avatar_key: str | None
    avatar_url: str | None
    created_at: datetime
    updated_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    message: str


class AuthorizationResponse(BaseModel):
    active: bool
    subject: str
    email: EmailStr
    role: str
    admin: bool
