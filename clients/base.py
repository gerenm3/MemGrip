"""clients/base.py — 基礎資料結構與抽象類別."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def serialize_tool_calls(tool_calls: List[Any]) -> List[Dict[str, Any]]:
    """將 tool_calls 轉換為可序列化的 dict 列表。

    支援多種來源：litellm ToolCall、ollama.ToolCall、dict、及其他有 __dict__ 的物件。
    """
    if not tool_calls:
        return []
    result: List[Dict[str, Any]] = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            result.append(tc)
        elif hasattr(tc, "model_dump"):
            result.append(tc.model_dump())
        elif hasattr(tc, "dict"):
            result.append(tc.dict())
        elif hasattr(tc, "__dict__"):
            result.append(vars(tc))
        else:
            result.append({"raw": str(tc)})
    return result


@dataclass
class ChatResponse:
    """LLM 聊天回應的統一格式."""
    content: str = ""
    tool_calls: List[Any] = field(default_factory=list)
    reasoning_content: Optional[str] = None