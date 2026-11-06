from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Theatre(Base):
    __tablename__ = "theatres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(48))
    borough: Mapped[str] = mapped_column(String(48), default="")
    address: Mapped[str] = mapped_column(String(120), default="")
    postcode: Mapped[str] = mapped_column(String(12), default="")
    lat: Mapped[float] = mapped_column(Float, default=51.5074)
    lng: Mapped[float] = mapped_column(Float, default=-0.1278)
    screen_count: Mapped[int] = mapped_column(Integer, default=8)
    seat_capacity: Mapped[int] = mapped_column(Integer, default=1200)

    visits: Mapped[list["Visit"]] = relationship(back_populates="theatre")


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    label: Mapped[str] = mapped_column(String(80))
    return_rate: Mapped[float] = mapped_column(Float, default=0.0)
    visits_per_year: Mapped[float] = mapped_column(Float, default=0.0)
    top_genre: Mapped[str] = mapped_column(String(32), default="")
    peak_month: Mapped[int] = mapped_column(Integer, default=1)
    member_count: Mapped[int] = mapped_column(Integer, default=0)

    customers: Mapped[list["Customer"]] = relationship(back_populates="segment")
    campaigns: Mapped[list["CampaignDraft"]] = relationship(back_populates="segment")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    borough: Mapped[str] = mapped_column(String(48), default="")
    postcode: Mapped[str] = mapped_column(String(12), default="")
    lat: Mapped[float] = mapped_column(Float, default=51.5074)
    lng: Mapped[float] = mapped_column(Float, default=-0.1278)
    age: Mapped[int] = mapped_column(Integer, default=35)
    home_theatre_id: Mapped[Optional[int]] = mapped_column(ForeignKey("theatres.id"), nullable=True)
    segment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("segments.id"), nullable=True)

    segment: Mapped[Optional[Segment]] = relationship(back_populates="customers")
    home_theatre: Mapped[Optional[Theatre]] = relationship(foreign_keys=[home_theatre_id])
    visits: Mapped[list["Visit"]] = relationship(back_populates="customer")


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    theatre_id: Mapped[int] = mapped_column(ForeignKey("theatres.id"))
    visited_on: Mapped[date] = mapped_column(Date)
    genre: Mapped[str] = mapped_column(String(32))
    ticket_type: Mapped[str] = mapped_column(String(24))

    customer: Mapped[Customer] = relationship(back_populates="visits")
    theatre: Mapped[Theatre] = relationship(back_populates="visits")


class CampaignDraft(Base):
    __tablename__ = "campaign_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    action: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(48))
    expected_lift: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    edited_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    segment: Mapped[Segment] = relationship(back_populates="campaigns")
