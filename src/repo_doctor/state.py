from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    thought: str
    tool: str | None
    args: dict | None
    result: Any = None
    error: str | None = None


@dataclass
class TaskState:
    goal: str
    repo_url: str
    workspace: str
    steps: list[Step] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    scratchpad: str = ""
    done: bool = False
    final_answer: str | None = None

    def add_fact(self, f: str):
        self.facts.append(f)

    def last_steps(self, n: int = 5) -> list[Step]:
        return self.steps[-n:]

    def last_n_steps(self, n: int = 5) -> list[Step]:
        return self.steps[-n:]