import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, nullable=False)
    password_hash: str = Field(nullable=False)
    name: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class ConsentRecord(SQLModel, table=True):
    """Append-only consent choice recorded for a user."""

    __tablename__ = "consent_records"

    id: int | None = Field(default=None, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True, nullable=False)
    consent_type: str = Field(nullable=False)
    accepted: bool = Field(nullable=False)
    document_version: str | None = Field(default=None)
    recorded_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
