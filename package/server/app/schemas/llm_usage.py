from pydantic import BaseModel


class LLMUsageTotals(BaseModel):
    requests: int = 0
    reported_requests: int = 0
    cache_reported_requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


class LLMModelUsage(LLMUsageTotals):
    source: str
    connection_id: str
    model: str


class LLMUsageReport(BaseModel):
    totals: LLMUsageTotals
    models: list[LLMModelUsage]
