from sqlalchemy import BigInteger, Column, Date, ForeignKey, String

from app.db.base import Base
from app.db.types import GUID


class LLMUsageDaily(Base):
    __tablename__ = "llm_usage_daily"

    owner_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day = Column(Date, primary_key=True)
    source = Column(String(24), primary_key=True)
    connection_id = Column(String(128), primary_key=True)
    model = Column(String(256), primary_key=True)
    requests = Column(BigInteger, nullable=False)
    reported_requests = Column(BigInteger, nullable=False)
    cache_reported_requests = Column(BigInteger, nullable=False)
    input_tokens = Column(BigInteger, nullable=False)
    output_tokens = Column(BigInteger, nullable=False)
    cached_input_tokens = Column(BigInteger, nullable=False)
