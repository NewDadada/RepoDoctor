from abc import ABC, abstractmethod
from pydantic import BaseModel

class ToolResult(BaseModel):
    ok: bool
    data: dict | None = None
    error: str | None = None
    hint: str | None = None

class Tool(ABC):
    name: str
    description: str
    args_schema: type[BaseModel]

    @abstractmethod
    def run(self, **kwargs) -> ToolResult: ...

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_schema.model_json_schema(),
            },
        }
        
