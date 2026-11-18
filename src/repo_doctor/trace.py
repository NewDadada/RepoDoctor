"""Optional Langfuse tracing.

Tracing is opt-in: install the extra (``pip install -e ".[tracing]"``) and set
``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY``. When the package is missing
or the keys are not configured the module still imports and every call is a
no-op, so the agent never depends on tracing being available.
"""

try:
    from langfuse import Langfuse
except ImportError:  # pragma: no cover - tracing is an optional extra
    Langfuse = None

from .config import settings

if Langfuse is not None and settings.langfuse_public_key and settings.langfuse_secret_key:
    lf = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )
else:
    lf = None


def trace_step(i, step):
    if lf is None:
        return
    lf.create_event(
        name=f"tool:{step.tool}",
        input={"args": step.args},
        output=step.result,
        metadata={"step": i, "thought": step.thought},
    )
