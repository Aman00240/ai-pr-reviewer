import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    AUTO_APPROVED = "auto_approved"
    REQUIRES_HUMAN_APPROVAL = "requires_human_approval"
    FAILED = "failed"


class SeverityLevel(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NITPICK = "nitpick"


class PRReviewRecord(Base):
    __tablename__ = "pr_review_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_full_name: Mapped[str] = mapped_column(Text)
    pr_number: Mapped[int] = mapped_column()
    commit_sh: Mapped[str] = mapped_column(Text)

    overall_confidance: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))

    status: Mapped[ReviewStatus] = mapped_column(
        SQLEnum(
            ReviewStatus,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda obj: [e.value for e in obj],
            name="check_pr_review_status",
        ),
        default=ReviewStatus.PENDING,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc)
    )

    findings: Mapped[list["FindingRecord"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", passive_deletes=True
    )


class FindingRecord(Base):
    __tablename__ = "finding_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pr_review_records.id"), ondelete="CASCADE"
    )
    agent_type: Mapped[str] = mapped_column(Text)

    severity: Mapped[SeverityLevel] = mapped_column(
        SQLEnum(
            SeverityLevel,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda obj: [e.value for e in obj],
            name="check_finding_severity",
        )
    )
    file_path: Mapped[str] = mapped_column(Text)
    line_number: Mapped[int] = mapped_column()
    suggestion: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    rationale: Mapped[str] = mapped_column(Text)

    review: Mapped[PRReviewRecord] = relationship(back_populates="findings")


class CodeChunk(Base):
    __tablename__ = "code_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    embedding: Mapped[Any] = mapped_column(Vector(1536))
    content_tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english',content)", persisted=True)
    )


Index(
    "code_chunks_emb_idx",
    CodeChunk.embedding,
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgressql_ops={"embedding": "vector_ip_ops"},
)
Index("code_chunks_fts_idx", CodeChunk.content_tsv, postgresql_using="gin")


class AgentEvent(Base):
    __tablename__ = "agent_events"
    __table_args__ = {"postgresql_partition_by": "RANGE (ts)"}

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        default=lambda: datetime.now(timezone.utc),
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)

    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int | None] = mapped_column()
    payload: Mapped[dict | None] = mapped_column(JSONB)
