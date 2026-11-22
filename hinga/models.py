"""SQL tables. Private rows carry user_id. The users table is only id and name."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))


class Profile(Base):
    """values, goals, and tone. Stored sealed. One row per person."""

    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    values_sealed: Mapped[str] = mapped_column(Text)
    goals_sealed: Mapped[str] = mapped_column(Text)
    tone_sealed: Mapped[str] = mapped_column(Text)


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # Fernet ciphertext. Never write plaintext here.
    body: Mapped[str] = mapped_column(Text)
    mood: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    embedding_json: Mapped[str] = mapped_column(Text, default="[]")
    embedding_space: Mapped[str] = mapped_column(String(80), default="local")
    reflection_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(20), default="analyzed")
    safety_hold: Mapped[bool] = mapped_column(Boolean, default=False)


class Habit(Base):
    __tablename__ = "habits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    intention: Mapped[str] = mapped_column(Text)
    intention_small: Mapped[str] = mapped_column(Text, default="")
    value_link: Mapped[str] = mapped_column(Text, default="")


class HabitLog(Base):
    __tablename__ = "habit_logs"
    __table_args__ = (UniqueConstraint("habit_id", "logged_on", name="habit_log_once"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    habit_id: Mapped[str] = mapped_column(ForeignKey("habits.id"), index=True)
    logged_on: Mapped[date] = mapped_column(Date)
