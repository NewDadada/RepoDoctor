"""Tracing is optional: without a client every call is a no-op."""

from dataclasses import dataclass

import repo_doctor.trace as trace


@dataclass
class FakeStep:
    tool: str = "read_file"
    args: dict | None = None
    result: dict | None = None
    thought: str = "inspect the file"


def test_trace_step_is_noop_without_client(monkeypatch):
    monkeypatch.setattr(trace, "lf", None)

    trace.trace_step(0, FakeStep())


def test_tracing_client_is_optional():
    # None when langfuse is not installed; otherwise an object with create_event.
    assert trace.lf is None or hasattr(trace.lf, "create_event")
