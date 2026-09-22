import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SavedItem(Base):
    """
    Generic saved-item table for all agent features — mock interviews,
    algorithm canvas designs, tutor chat sessions, code reviews.
    Polymorphic via item_type + a JSONB payload, so the app can save
    multiple of each type without needing a new table per feature.
    """
    __tablename__ = "saved_items"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # item_type in: "interview", "canvas", "tutor_chat", "code_review"
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # payload shape depends on item_type:
    #   interview: {topic, difficulty, transcript, feedback}
    #   canvas: {nodes, connections, generated_code, language}
    #   tutor_chat: {messages: [{role, text}]}
    #   code_review: {code, language, review}
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
