"""BP-001 transport-neutral result contract. No provider or host integrations."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal['OK', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED', 'NEEDS_REVIEW', 'ERROR']
STATUSES = {'OK', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED', 'NEEDS_REVIEW', 'ERROR'}


@dataclass(frozen=True)
class Cost:
    state: Literal['KNOWN', 'UNKNOWN'] = 'UNKNOWN'
    currency: str = 'USD'
    estimated: str | None = None
    actual: str | None = None
    scope: str = 'external_service_charges_only; excludes host inference and hardware'

    def __post_init__(self):
        from publishing_core import number, currency_code
        currency_code(self.currency)
        if self.state not in {'KNOWN', 'UNKNOWN'}:
            raise ValueError('invalid cost state')
        if self.state == 'KNOWN' and self.actual is None:
            raise ValueError('known cost requires an actual amount')
        if self.state == 'UNKNOWN' and self.actual is not None:
            raise ValueError('unknown actual cost must remain null')
        for value in (self.estimated, self.actual):
            if value is not None:
                number(value, 'cost')


@dataclass(frozen=True)
class ToolResult:
    status: Status
    data: dict[str, Any]
    operation_id: str
    timing: dict[str, Any]
    evidence_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    error: dict[str, str] | None = None
    cost: Cost = field(default_factory=Cost)
    artifact_refs: list[dict[str, Any]] = field(default_factory=list)
    tool_version: str = '0.2.0'

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError('invalid tool status')
        if not self.operation_id or self.timing.get('elapsed_ms', -1) < 0:
            raise ValueError('operation ID and actual nonnegative timing required')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
