"""initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="student"),
        sa.Column("xp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "rooms",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(20), nullable=False, server_default="python"),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("code_snapshot", sa.Text, nullable=False, server_default=""),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "room_members",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("room_id", UUID(as_uuid=False), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="editor"),
        sa.Column("invite_token", sa.String(512), nullable=True),
        sa.Column("is_revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_room_members_room_id", "room_members", ["room_id"])
    op.create_index("ix_room_members_user_id", "room_members", ["user_id"])

    op.create_table(
        "submissions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("room_id", UUID(as_uuid=False), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column("stdout", sa.Text, nullable=False, server_default=""),
        sa.Column("stderr", sa.Text, nullable=False, server_default=""),
        sa.Column("exit_code", sa.Integer, nullable=False, server_default="0"),
        sa.Column("runtime_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("memory_kb", sa.Integer, nullable=False, server_default="0"),
        sa.Column("timed_out", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_submissions_room_id", "submissions", ["room_id"])
    op.create_index("ix_submissions_user_id", "submissions", ["user_id"])

    op.create_table(
        "op_log",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("room_id", UUID(as_uuid=False), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("op_type", sa.String(20), nullable=False),
        sa.Column("op_json", JSONB, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_op_log_room_id", "op_log", ["room_id"])
    op.create_index("ix_op_log_created_at", "op_log", ["created_at"])

    op.create_table(
        "complexity_log",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("room_id", UUID(as_uuid=False), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("time_complexity", sa.String(30), nullable=False),
        sa.Column("space_complexity", sa.String(30), nullable=False),
        sa.Column("confidence", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_complexity_log_room_id", "complexity_log", ["room_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("room_id", UUID(as_uuid=False), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("meta_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_room_id", "audit_log", ["room_id"])

    op.create_table(
        "xp_events",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("xp_delta", sa.Integer, nullable=False),
        sa.Column("meta_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_xp_events_user_id", "xp_events", ["user_id"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_chunks_source", "knowledge_chunks", ["source"])
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding ON knowledge_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "qa_cache",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("hit_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "CREATE INDEX ix_qa_cache_embedding ON qa_cache "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)"
    )


def downgrade() -> None:
    op.drop_table("qa_cache")
    op.drop_table("knowledge_chunks")
    op.drop_table("xp_events")
    op.drop_table("audit_log")
    op.drop_table("complexity_log")
    op.drop_table("op_log")
    op.drop_table("submissions")
    op.drop_table("room_members")
    op.drop_table("rooms")
    op.drop_table("users")
