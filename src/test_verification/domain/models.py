"""Test verification domain model (sandbox execution arrives with Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TestResult:
    name: str
    passed: bool
    output: str = ""


@dataclass(frozen=True)
class TestSuite:
    name: str
    results: tuple[TestResult, ...] = ()

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(r.passed for r in self.results)
