"""SQLAlchemy ORM models for plans, jobs, and artifacts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from .database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class PlanRow(Base):
    __tablename__ = "plans"

    id = Column(String(36), primary_key=True)
    workflow_id = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    study_instance_uid = Column(String(128), nullable=False)
    segmentation_uid = Column(String(128), nullable=True)
    prescription_gy = Column(Float, nullable=False)
    fraction_count = Column(Integer, nullable=False, default=1)
    beam_count = Column(Integer, nullable=False, default=1)
    notes = Column(Text, nullable=True)
    job_id = Column(String(36), nullable=True)
    qa_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # Relationships
    artifacts = relationship("ArtifactRow", back_populates="plan", cascade="all, delete-orphan")
    job = relationship("JobRow", back_populates="plan", uselist=False, cascade="all, delete-orphan")


class JobRow(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    plan_id = Column(String(36), ForeignKey("plans.id"), nullable=False)
    state = Column(String(20), nullable=False, default="queued")
    progress = Column(Float, default=0.0)
    message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    plan = relationship("PlanRow", back_populates="job")


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    id = Column(String(36), primary_key=True)
    plan_id = Column(String(36), ForeignKey("plans.id"), nullable=False)
    file_path = Column(Text, nullable=False)
    content_type = Column(String(64), default="application/dicom")
    file_name = Column(String(256), default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    plan = relationship("PlanRow", back_populates="artifacts")
