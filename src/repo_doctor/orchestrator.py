import json
from .state import TaskState, Step
from .llm import call_llm
from .context import build_messages
from .config import settings
from .trace import trace_step


def run_agent(goal: str, repo_url: str, workspace: str, tools: dict) -> TaskState:
    state = TaskState(goal=goal, repo_url=repo_url, workspace=workspace)
    tools_schema = [t.to_openai_schema() for t in tools.values()]

    for step_i in range(settings.max_steps):
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

        tool = tools.get(name)
        if not tool:
            result = {"ok": False, "error": f"unknown tool {name}"}
        else:
            r = tool.run(**args)
            result = r.model_dump()

        step = Step(thought=msg.content or "", tool=name, args=args, result=result)
        state.steps.append(step)
        trace_step(step_i, step)

        if not result.get("ok"):
            state.add_fact(f"{name} failed: {result.get('error')}")
        elif name == "clone_repo" and result.get("data", {}).get("path"):
            state.add_fact(f"Repo is at {result['data']['path']}")

    state.final_answer = "Max steps reached without completion."
    return state