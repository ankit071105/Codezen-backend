import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class TopicAttempt(Base):
    """One row per graded event (interview feedback, code review, PYQ answer).
    Purely additive table — does not touch Submission/User/Room schemas.
    Used to compute per-topic weak/strong breakdown for the adaptive loop."""
    __tablename__ = "topic_attempts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # "interview" | "pyq" | "code_review"
    company: Mapped[str] = mapped_column(String(100), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    user = relationship("User", backref="topic_attempts")