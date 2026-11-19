"""Record provider-reported usage once per completed model call."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.models.llm_usage import LLMUsageDaily
from app.db.session import SessionLocal
from app.schemas.llm_usage import LLMModelUsage, LLMUsageReport, LLMUsageTotals

logger = logging.getLogger(__name__)
COUNTERS = tuple(LLMUsageTotals.model_fields)


def _token_count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _response_usage(response: LLMResult, requested_model: str) -> tuple[str, LLMUsageTotals]:
    output = response.llm_output or {}
    raw = output.get("token_usage") or {}
    model = output.get("model_name") or requested_model
    input_tokens = _token_count(raw.get("prompt_tokens"))
    output_tokens = _token_count(raw.get("completion_tokens"))
    cached = _token_count((raw.get("prompt_tokens_details") or {}).get("cached_tokens"))

    for generations in response.generations:
        for generation in generations:
            message = getattr(generation, "message", None)
            metadata = getattr(message, "response_metadata", {}) or {}
            model = metadata.get("model_name") or model
            usage = getattr(message, "usage_metadata", None)
            if not usage:
                continue
            if input_tokens is None:
                input_tokens = _token_count(usage.get("input_tokens"))
            if output_tokens is None:
                output_tokens = _token_count(usage.get("output_tokens"))
            if cached is None:
                details = usage.get("input_token_details") or {}
                hits = [_token_count(details.get(key)) for key in ("cache_read", "priority_cache_read", "flex_cache_read")]
                if any(hit is not None for hit in hits):
                    cached = sum(hit or 0 for hit in hits)
            # Provider usage belongs to the request, even when it produced multiple choices.
            break
        else:
            continue
        break

    return model, LLMUsageTotals(
        requests=1,
        reported_requests=int(input_tokens is not None and output_tokens is not None),
        cache_reported_requests=int(cached is not None),
        input_tokens=input_tokens or 0,
        output_tokens=output_tokens or 0,
        cached_input_tokens=cached or 0,
    )


def _add_usage(db: Session, owner_id, day, source, connection_id, model, totals: LLMUsageTotals) -> None:
    table = LLMUsageDaily.__table__
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    statement = insert(table).values(
        owner_id=owner_id, day=day, source=source, connection_id=connection_id[:128],
        model=model[:256], **totals.model_dump(),
    )
    db.execute(statement.on_conflict_do_update(
        index_elements=list(table.primary_key),
        set_={name: table.c[name] + statement.excluded[name] for name in COUNTERS},
    ))


class LLMUsageCallback(BaseCallbackHandler):
    def __init__(self, owner_id: UUID | str, source: str, connection_id: str, model: str):
        self.owner_id = owner_id
        self.source = source
        self.connection_id = connection_id
        self.model = model

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            model, totals = _response_usage(response, self.model)
            with SessionLocal.begin() as db:
                _add_usage(db, self.owner_id, datetime.now(timezone.utc).date(),
                           self.source, self.connection_id, model, totals)
        except Exception:
            logger.warning("Could not record LLM usage for %s", self.source, exc_info=True)


def get_usage_report(db: Session, owner_id: UUID, days: int) -> LLMUsageReport:
    table = LLMUsageDaily.__table__
    dimensions = (table.c.source, table.c.connection_id, table.c.model)
    last_day = datetime.now(timezone.utc).date()
    first_day = last_day - timedelta(days=days - 1)
    rows = db.execute(
        select(*dimensions, *(func.sum(table.c[name]).label(name) for name in COUNTERS))
        .where(table.c.owner_id == owner_id, table.c.day.between(first_day, last_day))
        .group_by(*dimensions)
        .order_by(func.sum(table.c.input_tokens + table.c.output_tokens).desc(), *dimensions)
    ).mappings()
    models = [LLMModelUsage.model_validate(row) for row in rows]
    return LLMUsageReport(
        totals=LLMUsageTotals(**{name: sum(getattr(row, name) for row in models) for name in COUNTERS}),
        models=models,
    )
