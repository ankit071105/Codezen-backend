from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class CompanyPyqCache(Base):
    """Cached scraped+extracted question patterns per company, refreshed
    every CACHE_TTL_DAYS (see pyq_scraper_agent.py) so we never re-scrape
    on every request."""
    __tablename__ = "company_pyq_cache"

    company: Mapped[str] = mapped_column(String(100), primary_key=True)
    patterns: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
