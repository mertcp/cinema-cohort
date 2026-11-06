from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.cost_db import MarketingBase, OpsCostBase


class SegmentMarketingBudget(MarketingBase):
    """Target-group marketing plans (marketing.db)."""

    __tablename__ = "segment_marketing_budget"

    segment_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monthly_spend_gbp: Mapped[int] = mapped_column(Integer, default=0)
    active_months: Mapped[str] = mapped_column(String(64), default="")


class SiteMonthCost(OpsCostBase):
    """One theatre × calendar month line (separate .db per category)."""

    __tablename__ = "site_month_cost"
    __table_args__ = (UniqueConstraint("theatre_id", "period_key", name="uq_theatre_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    theatre_id: Mapped[int] = mapped_column(Integer, index=True)
    period_key: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    amount_gbp: Mapped[int] = mapped_column(Integer, default=0)
