from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Violation:
    rule_id: str
    subject: str
    detail: str
