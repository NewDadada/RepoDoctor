import json
import time
from typing import Callable

from .state import TaskState, Step
from .llm import call_llm
from .context import build_messages
from .config import settings
from .trace import trace_step


def run_agent(
    goal: str,
    repo_url: str,
    workspace: str,
    tools: dict,
    on_loop: Callable[[int], None] | None = None,
    on_step: Callable[[int, Step], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    max_steps: int | None = None,
) -> TaskState:
    """Run the tool-calling loop.

    ``on_loop`` / ``on_step`` are optional observers used by the local web UI to
    stream progress; they are ignored by the CLI and the eval runner.
    ``should_stop`` is polled before every model call so a run can be cancelled.
    """
    state = TaskState(goal=goal, repo_url=repo_url, workspace=workspace)
    tools_schema = [t.to_openai_schema() for t in tools.values()]
    limit = settings.max_steps if max_steps is None else max_steps

    for step_i in range(limit):
        if should_stop is not None and should_stop():
            state.cancelled = True
            return state

        if on_loop is not None:
            on_loop(step_i + 1)
            if should_stop is not None and should_stop():
                state.cancelled = True
                return state

        msgs = build_messages(state)
        msg = call_llm(msgs, tools_schema)

        if not msg.tool_calls:
            state.final_answer = msg.content
            state.done = True
            return state

        tc = msg.tool_calls[0]
        name = tc.function.name
        args = json.loads(tc.function.arguments or "{}")

        if state.steps and state.steps[-1].tool == name and state.steps[-1].args == args:
            state.add_fact(f"Repeated {name}{args} failed; try a different approach.")
            continue

        started = time.perf_counter()
        tool = tools.get(name)
        if not tool:
            result = {"ok": False, "error": f"unknown tool {name}"}
        else:
            r = tool.run(**args)
            result = r.model_dump()
        duration_ms = round((time.perf_counter() - started) * 1000)

        step = Step(
            thought=msg.content or "",
            tool=name,
            args=args,
            result=result,
            duration_ms=duration_ms,
        )
        state.steps.append(step)
        trace_step(step_i, step)

        if on_step is not None:
            on_step(step_i + 1, step)

        if not result.get("ok"):
            state.add_fact(f"{name} failed: {result.get('error')}")
        elif name == "clone_repo" and result.get("data", {}).get("path"):
            state.add_fact(f"Repo is at {result['data']['path']}")

    state.final_answer = "Max steps reached without completion."
    return state
