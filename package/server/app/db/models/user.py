#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/5/9 23:44 
@Author      : SiYuan 
@Email       : sixyuan044@gmail.com 
@File        : TrailSnap-user.py 
@Description : 
"""

from sqlalchemy import Column, String, Boolean, DateTime, Integer, JSON
from app.db.types import UUID
import uuid
from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    nickname = Column(String, nullable=True)
    avatar = Column(String, nullable=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    last_failed_login = Column(DateTime, nullable=True)
    lockout_until = Column(DateTime, nullable=True)

    # Password Reset Security Question
    security_question = Column(String, nullable=True)
    security_answer_hash = Column(String, nullable=True)

    # User Settings
    settings = Column(JSON, default={})
