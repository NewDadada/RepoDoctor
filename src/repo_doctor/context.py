import json
from .state import TaskState

SYSTEM = open("src/repo_doctor/prompts/system.md", encoding="utf-8").read()


def build_messages(state: TaskState) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM}]
    msgs.append({"role": "user", "content":
        f"Goal: {state.goal}\nRepo: {state.repo_url}\nWorkspace: {state.workspace}"})

    if state.facts:
        msgs.append({"role": "user", "content":
            "Known facts:\n" + "\n".join(f"- {f}" for f in state.facts)})

    for s in state.last_steps(5):
        if s.tool:
            msgs.append({"role": "assistant", "content": None, "tool_calls": [{
                "id": f"call_{id(s)}", "type": "function",
                "function": {"name": s.tool, "arguments": json.dumps(s.args)}
            }]})
            content = json.dumps(s.result, ensure_ascii=False, default=str)
            msgs.append({"role": "tool", "tool_call_id": f"call_{id(s)}",
                        "content": content[:4000]})
        else:
            msgs.append({"role": "assistant", "content": s.thought})

    return msgs