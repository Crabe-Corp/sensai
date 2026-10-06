import json
from typing import Any
from pydantic import BaseModel, Field

from src.features.tools.registry import ToolRegistry, default_registry


class ToolExecutionResult(BaseModel):
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None

    def to_tool_message_content(self) -> str:
        if not self.success:
            return json.dumps(
                {
                    "error": self.error or "Erreur inconnue lors de l'exécution de l'outil.",
                    "success": False,
                },
                ensure_ascii=False,
            )

        if isinstance(self.result, BaseModel):
            return self.result.model_dump_json()

        if isinstance(self.result, (dict, list, int, float, bool)):
            return json.dumps(self.result, ensure_ascii=False)

        if isinstance(self.result, str):
            try:
                json.loads(self.result)
                return self.result
            except (json.JSONDecodeError, ValueError):
                return json.dumps({"result": self.result}, ensure_ascii=False)

        if self.result is None:
            return json.dumps({"success": True}, ensure_ascii=False)

        return json.dumps({"result": str(self.result)}, ensure_ascii=False)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or default_registry

    def execute(self, tool_name: str, arguments: dict[str, Any] | None = None) -> ToolExecutionResult:
        tool_def = self.registry.get(tool_name)
        if not tool_def:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"L'outil '{tool_name}' n'est pas enregistré dans le registre.",
            )

        args = arguments or {}
        try:
            raw_result = tool_def.handler(**args)
            return ToolExecutionResult(
                tool_name=tool_name,
                success=True,
                result=raw_result,
            )
        except Exception as exc:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"Erreur lors de l'exécution de '{tool_name}' avec {args} : {type(exc).__name__}: {exc}",
            )
