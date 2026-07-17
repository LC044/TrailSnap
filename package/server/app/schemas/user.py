from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr

# Shared properties
class UserBase(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    is_active: Optional[bool] = True
    is_superuser: bool = False

# Properties to receive via API on creation
class UserCreate(UserBase):
    username: str
    email: EmailStr
    password: str
    security_question: Optional[str] = None
    security_answer: Optional[str] = None

# Properties to receive via API on update
class UserUpdate(UserBase):
    password: Optional[str] = None
    security_question: Optional[str] = None
    security_answer: Optional[str] = None

class UserUpdateMe(BaseModel):
    nickname: Optional[str] = None
    avatar: Optional[str] = None

# Properties shared by models stored in DB
class UserInDBBase(UserBase):
    id: UUID
    failed_login_attempts: int
    last_failed_login: Optional[datetime] = None
    lockout_until: Optional[datetime] = None
    security_question: Optional[str] = None

    class Config:
        from_attributes = True

# Additional properties to return via API
class UserResponse(UserInDBBase):
    pass

# Password Reset Schemas
class PasswordResetCheck(BaseModel):
    username_or_email: str

class PasswordResetCheckResponse(BaseModel):
    security_question: Optional[str] = None
    # If no question set, maybe return error or specific status

class PasswordResetConfirm(BaseModel):
    username_or_email: str
    security_answer: str
    new_password: str

# 通过服务器日志验证码重置密码（兜底方案，无需安全问题）
class LogResetCodeConfirm(BaseModel):
    username_or_email: str
    code: str
    new_password: str
