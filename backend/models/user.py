"""
User Profile Model
Extended user information stored in PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Text, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Configure Base to allow reserved attribute names
Base.__allow_unmapped__ = True


class UserProfile(Base):
    """
    User profile information for a VisionX user.
    
    Attributes:
        id: UUID of the user (primary key)
        email: User email
        full_name: User's full name
        username: Unique username
        avatar_url: URL to profile picture
        bio: User biography
        created_at: Account creation timestamp
        updated_at: Last profile update timestamp
    """
    __tablename__ = "user_profiles"
    __table_args__ = {"schema": "public"}
    
    # Avoid SQLAlchemy metadata conflict
    __mapper_args__ = {"exclude_properties": []}

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=True, index=True)
    avatar_url = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    extra_data = Column(Text, nullable=True)  # JSON string for additional metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<UserProfile(id={self.id}, email={self.email}, full_name={self.full_name})>"