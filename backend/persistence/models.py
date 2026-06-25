"""
SQLAlchemy ORM models for PanelMind (Tier 0b).

Entity-relationship overview
────────────────────────────

    User ──┐
           │ owns
           ▼
    PitchSession ──┬── PitchTurn (one per agent or user utterance)
                   ├── AgentMemory (per-agent private state)
                   ├── PitchVerdict (final structured output)
                   ├── PitchRevision (rewritten pitch in revision loop)
                   └── (events live in-memory; not persisted)

    AgentPersona is a global catalog (one row per persona) — every session
    can reference multiple personas via the panel composition.

We use UUIDs (as strings) for all primary keys to keep the data model
portable: same schema works for SQLite, Postgres, and any future OLAP store.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _uuid() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


# ─── Enums (kept as strings for forward compat) ─────────────────


class SessionStatus(str, enum.Enum):
    """Lifecycle of a pitch session."""

    CREATED = "created"          # session_id minted, no pitch yet
    REFINING = "refining"        # pitch_refiner node running
    AWAITING_APPROVAL = "awaiting_approval"  # HITL summary approval
    DEBATING = "debating"        # controller loop active
    AWAITING_USER = "awaiting_user"  # waiting on user answer
    ENDING = "ending"            # final_node running
    COMPLETED = "completed"      # verdict delivered
    ABORTED = "aborted"          # user cancelled or error
    ERRORED = "errored"          # unrecoverable failure


class TurnRole(str, enum.Enum):
    """Who produced this turn in the conversation."""

    PERSONA = "persona"          # panelist spoke
    PITCHER = "pitcher"          # user spoke
    TOOL = "tool"                # tool output (search, fact-check)
    SYSTEM = "system"            # controller/system message


class TurnType(str, enum.Enum):
    """Sub-classification within a turn (matches legacy orchestrator types)."""

    QUESTION = "question"
    ANSWER = "answer"
    REACTION = "reaction"
    PITCHER_RESPONSE = "pitcher_response"
    PITCHER_INTERRUPT = "pitcher_interrupt"
    INTERRUPT_ACK = "interrupt_ack"
    INTERVIEWER_QUESTION = "interviewer_question"
    INTERVIEWER_INVITATION = "interviewer_invitation"
    PERSONA_RESPONSE = "persona_response"
    DEBATE_INTERJECTION = "debate_interjection"
    DEBATE_QUESTION = "debate_question"
    TOOL_OUTPUT = "tool_output"
    HOST_UTTERANCE = "host_utterance"
    OBSERVER_UTTERANCE = "observer_utterance"


class VerdictSignal(str, enum.Enum):
    """Top-level investment signal derived from the verdict."""

    STRONG = "STRONG"
    MEDIUM = "MEDIUM"
    WEAK = "WEAK"
    ABORTED = "ABORTED"


# ─── User ────────────────────────────────────────────────────────


class User(Base):
    """An authenticated PanelMind user (created in Tier 0b with NextAuth)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[Optional[str]] = mapped_column(String(320), unique=True, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(50), default="email", nullable=False)
    provider_account_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    sessions: Mapped[list["PitchSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", name="uq_user_provider"),
    )


# ─── Agent Persona (global catalog) ─────────────────────────────


class AgentPersona(Base):
    """A reusable agent persona. Loaded from YAML at startup, cached in DB."""

    __tablename__ = "agent_personas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. "vc"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # OCEAN profile (each 0..1) — drives behavior_text in prompts
    ocean_openness: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    ocean_conscientiousness: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    ocean_extraversion: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    ocean_agreeableness: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    ocean_neuroticism: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)

    # Free-form config (colors, avatar, voice prefs, etc.)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ─── Pitch Session ──────────────────────────────────────────────


class PitchSession(Base):
    """A single pitch evaluation. One per (user, time)."""

    __tablename__ = "pitch_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # Foreign key to user (nullable: anonymous sessions in Tier 0a)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Inputs
    pitch_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    refined_pitch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Configuration
    mode: Mapped[str] = mapped_column(String(20), default="venture", nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="groq", nullable=False)
    aggressiveness: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # State
    status: Mapped[str] = mapped_column(
        String(30), default=SessionStatus.CREATED.value, nullable=False, index=True
    )
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_steps: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_force_ended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Privacy (Tier-1c). When true, the verdict is publicly shareable
    # at /v/<session_id>. When false, the verdict is owner-only.
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Domain classification (filled in by the orchestrator)
    domain: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    active_panel: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Long-form / opaque data
    hitl_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    global_memory: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    agent_memory: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    memory_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    past_pitch_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    black_swan_insight: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    revised_pitch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(
        # Inherits DateTime from base. Nullable so it can be set on first event.
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="sessions")
    turns: Mapped[list["PitchTurn"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PitchTurn.step_index",
    )
    verdict: Mapped[Optional["PitchVerdict"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )
    revisions: Mapped[list["PitchRevision"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PitchRevision.created_at",
    )

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["turns"] = [t.to_dict() for t in self.turns]
        if self.verdict:
            d["verdict"] = self.verdict.to_dict()
        d["revisions"] = [r.to_dict() for r in self.revisions]
        return d


# ─── Pitch Turn ──────────────────────────────────────────────────


class PitchTurn(Base):
    """A single message in the panel conversation."""

    __tablename__ = "pitch_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pitch_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # TurnRole value
    turn_type: Mapped[str] = mapped_column(String(40), nullable=False)  # TurnType value
    agent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    agent_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Relationships
    session: Mapped["PitchSession"] = relationship(back_populates="turns")


# ─── Pitch Verdict ──────────────────────────────────────────────


class PitchVerdict(Base):
    """The final structured verdict for a session."""

    __tablename__ = "pitch_verdicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pitch_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Free-form verdict text (rendered to PDF + UI)
    verdict_text: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Structured parts
    strongest: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    weakness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    investment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    # Aggregate scores
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    signal: Mapped[str] = mapped_column(
        String(20), default=VerdictSignal.MEDIUM.value, nullable=False
    )

    # Pre-rendered chart images (base64 PNG)
    charts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    session: Mapped["PitchSession"] = relationship(back_populates="verdict")


# ─── Pitch Revision (the re-pitch loop) ─────────────────────────


class PitchRevision(Base):
    """A rewritten pitch generated in response to the verdict."""

    __tablename__ = "pitch_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pitch_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    original_pitch: Mapped[str] = mapped_column(Text, nullable=False)
    revised_pitch: Mapped[str] = mapped_column(Text, nullable=False)
    improvements_addressed: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )

    # Relationships
    session: Mapped["PitchSession"] = relationship(back_populates="revisions")


# ─── Prompt Experiments (Tier-2c) ──────────────────────────────────


class PromptExperiment(Base):
    """An A/B test between two prompt versions.

    Each experiment has a name (e.g. "controller-prompt-v2") and two
    or more "variants" (different prompt versions). Sessions are
    assigned to variants via a deterministic hash of session_id.
    Outcomes are recorded separately so we can compare.
    """

    __tablename__ = "prompt_experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Whether the experiment is currently active. Inactive experiments
    # always serve the "control" variant.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Map of variant_name -> traffic_weight (int, relative). The sum
    # is normalized at runtime. E.g. {"control": 80, "v2": 20} means
    # 80% of sessions get "control" and 20% get "v2".
    variant_weights: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    # Optional metadata (variant descriptions, dates, owner, etc.)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class PromptAssignment(Base):
    """A specific session's assignment to a variant of an experiment.

    Created when a session is first routed through an experiment.
    Used to ensure the same session always gets the same variant
    (deterministic A/B).
    """

    __tablename__ = "prompt_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    experiment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prompt_experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    variant: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class PromptOutcome(Base):
    """An outcome (e.g. user rating, score) for a prompt assignment.

    Used to compare variants. We record multiple metrics per assignment
    so you can analyze different aspects (e.g. rating, time-to-completion,
    cost).
    """

    __tablename__ = "prompt_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    assignment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prompt_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ApiKey(Base):
    """An API key for accessing the public REST API.

    Keys are stored as hashes; the raw value is shown to the user
    only once at creation time. Owners can revoke keys, which sets
    `revoked_at` and rejects all future requests.
    """

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Display info
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # First 8 chars of the raw key (after the prefix), for display:
    # e.g. "pm_live_abcd1234"
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)

    # Permissions / scoping
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Whether this key is currently active. Revoked keys fail auth.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Rate limit overrides (per-key, in requests per minute).
    # None means "use the default".
    rate_limit_per_minute: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    total_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Lifecycle
    revoked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    def to_dict(self, include_hash: bool = False) -> dict[str, Any]:
        d = super().to_dict()
        if not include_hash:
            d.pop("key_hash", None)
        return d


# Update SessionRepository to know about API keys (Tier-2b)
# We extend the existing SessionRepository interface with API-key methods.
from .repository import SessionRepository  # noqa: E402  (circular-safe import at module level)
