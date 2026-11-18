
from langfuse import Langfuse
lf = Langfuse()
def trace_step(i, step):
    if lf:
        lf.create_event(
            name=f"tool:{step.tool}",
            input={"args": step.args},
            output=step.result,
            metadata={"step": i, "thought": step.thought},
        )