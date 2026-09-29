"""Validated experiment contracts; reject unsafe/unknown settings before any sends."""

from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PositiveInt = Annotated[int, Field(gt=0, strict=True)]
PositiveFloat = Annotated[float, Field(gt=0)]
Ratio = Annotated[float, Field(ge=0, le=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)


def validate_url(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or any(c.isspace() for c in value)
    ):
        raise ValueError("Use an HTTP(S) URL without credentials, query, fragment or whitespace")
    _ = parts.port
    return value.rstrip("/")


KeyEnv = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")]


class Endpoint(Contract):
    base_url: str
    model: str = Field(min_length=1, max_length=256)
    api_key_env: KeyEnv | None = None
    context_length: PositiveInt | None = None
    environment: dict[str, str | int | float | None] = Field(default_factory=dict)

    _url = field_validator("base_url")(validate_url)

    @field_validator("environment")
    @classmethod
    def no_secrets(cls, value):
        if any(
            k.lower() in {"api_key", "token", "password", "secret", "authorization", "access_token"}
            for k in value
        ):
            raise ValueError("Environment metadata must not contain secrets; use api_key_env")
        return value


class Message(Contract):
    role: Literal["system", "user", "assistant", "developer"]
    content: str = Field(min_length=1, max_length=2_000_000)


class Sample(Contract):
    id: str = Field(min_length=1, max_length=128)
    messages: list[Message] = Field(min_length=1, max_length=128)
    category: str = Field(default="default", min_length=1, max_length=128)
    max_tokens: PositiveInt | None = None


class Load(Contract):
    mode: Literal["concurrency", "rate"] = "concurrency"
    concurrency: PositiveInt = 1
    rate: PositiveFloat = 1.0
    count: Annotated[int, Field(gt=0, le=100_000, strict=True)] = 10
    warmup: Annotated[int, Field(ge=0, le=10_000, strict=True)] = 0
    repeats: Annotated[int, Field(gt=0, le=20, strict=True)] = 1
    scan: list[PositiveFloat] = Field(default_factory=list, max_length=32)
    mix: dict[str, PositiveFloat] = Field(default_factory=dict)
    seed: int = 42


class Generation(Contract):
    stream: bool = True
    max_tokens: Annotated[int, Field(gt=0, le=1_000_000, strict=True)] = 128
    temperature: Annotated[float, Field(ge=0, le=2)] = 0
    top_p: Annotated[float, Field(gt=0, le=1)] = 1
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("extra")
    @classmethod
    def allow_generation_options_only(cls, value):
        allowed = {
            "top_k",
            "repetition_penalty",
            "presence_penalty",
            "frequency_penalty",
            "seed",
            "chat_template_kwargs",
            "enable_thinking",
            "response_format",
            "stop",
        }
        if set(value) - allowed:
            raise ValueError("extra accepts generation options only; it cannot override protected fields")
        import json

        if len(json.dumps(value, allow_nan=False)) > 65536:
            raise ValueError("extra generation options exceed size limit")
        return value


class Goals(Contract):
    mode: Literal["online", "offline"] = "offline"
    min_requests_per_s: PositiveFloat | None = None
    max_p95_e2e_ms: PositiveFloat | None = None
    max_p95_ttft_ms: PositiveFloat | None = None
    max_p95_tpot_ms: PositiveFloat | None = None
    min_quality_pass_rate: Ratio = 1
    max_error_rate: Ratio = 0
    deadline_s: PositiveFloat | None = None
    target_requests: PositiveInt | None = None


class Quality(Contract):
    mode: Literal["rules", "manual", "none"] = "rules"
    require_json: bool = False
    json_fields: list[str] = Field(default_factory=list)
    required_text: list[str] = Field(default_factory=list)
    min_chars: Annotated[int, Field(ge=0, strict=True)] = 1
    reject_truncated: bool = True


class Safety(Contract):
    max_requests: Annotated[int, Field(gt=0, le=1_000_000, strict=True)] = 1000
    max_concurrency: Annotated[int, Field(gt=0, le=4096, strict=True)] = 64
    max_duration_s: Annotated[float, Field(gt=0, le=86400)] = 300
    request_timeout_s: Annotated[float, Field(gt=0, le=3600)] = 30
    max_output_tokens: PositiveInt = 128000
    max_response_bytes: Annotated[int, Field(gt=0, le=64 * 1024 * 1024, strict=True)] = 2 * 1024 * 1024


class MetricMapping(Contract):
    key: Literal[
        "queue_waiting",
        "requests_running",
        "kv_cache_usage_ratio",
        "preemptions_total",
        "prefix_hits_total",
        "prefix_queries_total",
        "device_utilization_ratio",
        "device_memory_used_bytes",
        "device_memory_total_bytes",
    ]
    metric: str = Field(min_length=1, pattern=r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
    kind: Literal["gauge", "counter"] = "gauge"
    scale: PositiveFloat = 1
    labels: dict[str, str] = Field(default_factory=dict)
    aggregation: Literal["sum", "max", "mean"] = "max"


class MetricSource(Contract):
    name: str = Field(min_length=1, max_length=128)
    url: str
    api_key_env: KeyEnv | None = None
    mappings: list[MetricMapping] = Field(default_factory=list, max_length=64)

    _url = field_validator("url")(validate_url)


class LocalTelemetry(Contract):
    enabled: bool = False


def local_ollama_url(base_url: str) -> str:
    """Only observe an explicitly selected loopback service, without proxy path guessing."""
    parts = urlsplit(validate_url(base_url))
    if parts.hostname not in {"localhost", "127.0.0.1", "::1"} or parts.path not in {"", "/v1"}:
        raise ValueError("local observation requires a loopback endpoint with root or /v1 path")
    return parts._replace(path="/api/ps").geturl()


class Telemetry(Contract):
    interval_s: Annotated[float, Field(ge=0.1, le=3600)] = 1
    sources: list[MetricSource] = Field(default_factory=list, max_length=16)
    local: LocalTelemetry = Field(default_factory=LocalTelemetry)


class ExperimentSpec(Contract):
    name: str = Field(default="baseline", min_length=1, max_length=128)
    endpoint: Endpoint
    dataset: list[Sample] = Field(min_length=1, max_length=10000)
    load: Load = Field(default_factory=Load)
    generation: Generation = Field(default_factory=Generation)
    goals: Goals = Field(default_factory=Goals)
    quality: Quality = Field(default_factory=Quality)
    safety: Safety = Field(default_factory=Safety)
    telemetry: Telemetry = Field(default_factory=Telemetry)
    cache_condition: Literal["unknown", "declared_cold", "declared_warm"] = "unknown"
    tokenizer_path: str | None = None
    notes: str = Field(default="", max_length=4096)
    protocol_fixture: bool = False

    @model_validator(mode="after")
    def guard_plan(self):
        if self.telemetry.local.enabled:
            local_ollama_url(self.endpoint.base_url)
        if len({r.id for r in self.dataset}) != len(self.dataset):
            raise ValueError("dataset sample ids must be unique")
        categories = {row.category for row in self.dataset}
        if set(self.load.mix) - categories:
            raise ValueError("mix references unknown categories")
        if self.load.mode == "concurrency" and any(not float(v).is_integer() for v in self.load.scan):
            raise ValueError("concurrency scan points must be integers")
        concurrency_values = [self.load.concurrency]
        if self.load.mode == "concurrency":
            concurrency_values += self.load.scan
        if max(concurrency_values) > self.safety.max_concurrency:
            raise ValueError("concurrency exceeds max_concurrency safety cap")
        requests = (self.load.count + self.load.warmup) * self.load.repeats * max(1, len(self.load.scan))
        if requests > self.safety.max_requests:
            raise ValueError("plan request reservation exceeds max_requests (including warmup/scans/repeats)")
        tokens = requests * max(row.max_tokens or self.generation.max_tokens for row in self.dataset)
        if tokens > self.safety.max_output_tokens:
            raise ValueError("plan output token reservation exceeds max_output_tokens")
        return self
