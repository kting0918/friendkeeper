import uuid
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import String, Text, Date, DateTime, Integer, Float, Boolean, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship


from app.core.database import Base


class Contact(Base):
    """聯絡人資料表"""
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    birthday: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    relationship_tag: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    contact_frequency_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_greeted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 關聯
    face_embeddings: Mapped[List["FaceEmbedding"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )
    encounters: Mapped[List["Encounter"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )
    reminders: Mapped[List["Reminder"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )


class FaceEmbedding(Base):
    """人臉特徵向量表"""
    __tablename__ = "face_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    embedding = mapped_column(JSON, nullable=False)
    source_photo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # 關聯
    contact: Mapped["Contact"] = relationship(back_populates="face_embeddings")


class Encounter(Base):
    """互動記錄表"""
    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    encountered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    location_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    photo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scene_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI 生成的場景描述
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="photo"
    )  # photo / manual / greeting
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # 關聯
    contact: Mapped["Contact"] = relationship(back_populates="encounters")


class Reminder(Base):
    """提醒設定表"""
    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reminder_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # birthday / contact_freq / custom
    next_trigger_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recurrence_rule: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # yearly / every_30d 等
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # 關聯
    contact: Mapped["Contact"] = relationship(back_populates="reminders")
