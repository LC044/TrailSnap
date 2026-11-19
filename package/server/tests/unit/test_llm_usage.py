from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models.llm_usage import LLMUsageDaily
from app.db.models.user import User
from app.schemas.llm_usage import LLMUsageTotals
from app.service import llm_usage

pytestmark = pytest.mark.smoke


@pytest.fixture
def usage_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'usage.sqlite').as_posix()}")
    User.__table__.create(engine)
    LLMUsageDaily.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(llm_usage, "SessionLocal", factory)
    try:
        yield factory
    finally:
        engine.dispose()


def test_usage_records_one_request_per_result_and_filters_by_owner_and_range(usage_db):
    owner_id, other_id = uuid4(), uuid4()
    response = LLMResult(generations=[[
        ChatGeneration(message=AIMessage(
            content="reply",
            usage_metadata={"input_tokens": 19, "output_tokens": 7, "total_tokens": 26,
                            "input_token_details": {"cache_read": 0}},
            response_metadata={"model_name": "resolved-model"},
        )),
        ChatGeneration(message=AIMessage(content="second choice")),
    ]])
    callback = llm_usage.LLMUsageCallback(owner_id, "visual_analysis", "external", "alias")
    callback.on_llm_end(response)
    callback.on_llm_end(response)
    callback.on_llm_end(LLMResult(generations=[], llm_output={"model_name": "resolved-model"}))
    llm_usage.LLMUsageCallback(other_id, "visual_analysis", "external", "alias").on_llm_end(response)

    today = datetime.now(timezone.utc).date()
    with usage_db.begin() as db:
        llm_usage._add_usage(db, owner_id, today - timedelta(days=7), "visual_analysis",
                             "external", "resolved-model", LLMUsageTotals(requests=1))
    with usage_db() as db:
        report = llm_usage.get_usage_report(db, owner_id, 7)
    assert report.totals == LLMUsageTotals(
        requests=3, reported_requests=2, cache_reported_requests=2,
        input_tokens=38, output_tokens=14, cached_input_tokens=0,
    )
    assert len(report.models) == 1
    assert report.models[0].model == "resolved-model"


@pytest.mark.asyncio
@pytest.mark.parametrize("reject_stream_options", [False, True])
async def test_streaming_usage_and_compatibility_fallback(usage_db, reject_stream_options):
    from app.service.agent.service import FixedChatOpenAI

    owner_id = uuid4()
    requested_options = []
    common = {"id": "chatcmpl-test", "object": "chat.completion.chunk", "created": 1, "model": "actual"}

    def reply(request):
        body = json.loads(request.content)
        include_usage = body.get("stream_options", {}).get("include_usage", False)
        requested_options.append(include_usage)
        if include_usage and reject_stream_options:
            return httpx.Response(400, json={"error": {"message": "Unsupported field stream_options"}})
        frames = [
            {**common, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"}, "finish_reason": None}]},
            {**common, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        if include_usage:
            frames.append({**common, "choices": [], "usage": {
                "prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15,
                "prompt_tokens_details": {"cached_tokens": 8},
            }})
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"},
                              text="".join(f"data: {json.dumps(frame)}\n\n" for frame in frames) + "data: [DONE]\n\n")

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
        model = FixedChatOpenAI(
            model="alias", api_key="test", base_url="https://example.test",
            http_async_client=http, stream_usage=True, max_retries=0,
            callbacks=[llm_usage.LLMUsageCallback(owner_id, "chat", "external", "alias")],
        )
        chunks = [chunk async for chunk in model.astream("test")]

    assert "".join(chunk.content for chunk in chunks) == "ok"
    with usage_db() as db:
        report = llm_usage.get_usage_report(db, owner_id, 1)
    assert report.totals.requests == 1
    assert report.models[0].model == "actual"
    if reject_stream_options:
        assert requested_options == [True, False]
        assert report.totals.reported_requests == report.totals.cache_reported_requests == 0
    else:
        assert requested_options == [True]
        assert report.totals.input_tokens == 12
        assert report.totals.output_tokens == 3
        assert report.totals.cached_input_tokens == 8
