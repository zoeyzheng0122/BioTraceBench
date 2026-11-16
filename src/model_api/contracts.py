"""Provider-neutral results. Model text is deliberately not JSON-decoded here."""
from dataclasses import asdict, dataclass
from typing import Any

VERSION = 'model-api-1'


@dataclass(frozen=True)
class BackendDescription:
    provider: str
    model: str
    protocol: str
    profile: dict
    profile_hash: str
    implementation_version: str = VERSION


@dataclass(frozen=True)
class BackendResponse:
    text: str
    finish_reason: str | None
    actual_model: str | None
    request_id: str | None
    usage: dict[str, Any]
    raw_usage: dict | None
    elapsed_seconds: float
    archive: str

    def as_dict(self):
        return asdict(self)


class ApiFailure(RuntimeError):
    """Safe diagnostic: vendor bodies and credentials never enter the message."""
    def __init__(self, message, status='paused_unknown', category=None, scope='case', retryable=False):
        super().__init__(message)
        self.status = status
        self.category = category or status
        self.scope = scope
        self.retryable = retryable
