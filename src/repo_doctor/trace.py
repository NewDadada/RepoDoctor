"""Optional Langfuse tracing.

Tracing is opt-in: install the extra (``pip install -e ".[tracing]"``) and set
``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY``. When the package is missing
the module still imports and every call is a no-op, so the agent never depends
on tracing being available.
"""

try:
    from langfuse import Langfuse
except ImportError:  # pragma: no cover - tracing is an optional extra
    Langfuse = None

lf = Langfuse() if Langfuse is not None else None


def trace_step(i, step):
    if lf is None:
        return
    lf.create_event(
        name=f"tool:{step.tool}",
        input={"args": step.args},
        output=step.result,
        metadata={"step": i, "thought": step.thought},
    )
