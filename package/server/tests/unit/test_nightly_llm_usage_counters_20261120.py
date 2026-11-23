"""Token accounting for the LLM usage ledger."""
import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.service.llm_usage import _response_usage, _token_count

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _result(message=None, llm_output=None):
    return LLMResult(
        generations=[[ChatGeneration(message=message or AIMessage(content="hello"))]],
        llm_output=llm_output,
    )


def test_token_count_accepts_non_negative_ints():
    assert _token_count(0) == 0
    assert _token_count(42) == 42


@pytest.mark.parametrize("value", [-1, True, "7", 1.5, None, []])
def test_token_count_rejects_every_other_type(value):
    assert _token_count(value) is None


def test_response_usage_reads_the_provider_token_usage():
    model, totals = _response_usage(
        _result(llm_output={"model_name": "qwen", "token_usage": {"prompt_tokens": 10, "completion_tokens": 4}}),
        "fallback",
    )
    assert model == "qwen"
    assert totals.requests == 1
    assert totals.reported_requests == 1
    assert totals.input_tokens == 10
    assert totals.output_tokens == 4
    assert totals.cached_input_tokens == 0
    assert totals.cache_reported_requests == 0


def test_response_usage_falls_back_to_the_requested_model():
    model, totals = _response_usage(_result(llm_output={"token_usage": {}}), "fallback")
    assert model == "fallback"
    assert totals.reported_requests == 0
    assert totals.input_tokens == 0


def test_response_usage_prefers_the_message_metadata_model():
    message = AIMessage(content="hi", response_metadata={"model_name": "from-message"})
    model, _ = _response_usage(_result(message=message, llm_output={"model_name": "from-output"}), "fallback")
    assert model == "from-message"


def test_response_usage_recovers_token_counts_from_the_message_metadata():
    message = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7, "input_token_details": {"cache_read": 3}},
    )
    _, totals = _response_usage(_result(message=message), "m")
    assert totals.input_tokens == 5
    assert totals.output_tokens == 2
    assert totals.cached_input_tokens == 3
    assert totals.cache_reported_requests == 1
    assert totals.reported_requests == 1


def test_response_usage_reports_no_tokens_when_the_provider_is_silent():
    _, totals = _response_usage(_result(), "m")
    assert totals.requests == 1
    assert totals.reported_requests == 0
    assert totals.input_tokens == 0
    assert totals.output_tokens == 0


