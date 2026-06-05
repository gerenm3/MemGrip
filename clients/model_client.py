"""v2 ModelClient — 模型調用封裝 (LiteLLM).

依據 §3.1 (ModelClient) 定義：
- __init__ 支援 tracer 注入（用於 trace 記錄）
- 移除舊版 call_model_func() dead code
- 符合 v2 logging 規範（使用 logger 而非 print）
- 提供 call_model() 公用函式供 Optimizer 等模組使用
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import litellm
from core.health import log_action
from models.blueprints import Result
import config
from config import LLM_TIMEOUT, MODEL_BASE_URL
from clients.ollama import OllamaLocalClient
from clients.cloud import CloudClient
from clients.base import ChatResponse

logger = logging.getLogger(__name__)

# 預設參數
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8192

# 全域 tracer（由 bootstrap 設定）
_global_tracer = None


def set_global_tracer(tracer) -> None:
    """設定全域 tracer，供所有 call_model/call_embedding 使用。"""
    global _global_tracer
    _global_tracer = tracer


def resolve_model(role: str) -> str:
    """根據 LLM_MODE 解析角色對應的模型名稱。

    Args:
        role: "large", "medium" 或 "embedding"

    Returns:
        實際模型名稱字串
    """
    mapping = {
        "local":  {
            "large": config.LARGE_MODEL_NAME,
            "medium": config.MEDIUM_MODEL_NAME,
            "embedding": config.EMBEDDING_MODEL_NAME,
        },
        "cloud":  {
            "large": config.CLOUD_MODEL_NAME,
            "medium": config.CLOUD_MEDIUM_MODEL_NAME,
            "embedding": config.EMBEDDING_MODEL_NAME,
        },
        "hybrid": {
            "large": config.CLOUD_MODEL_NAME,
            "medium": config.MEDIUM_MODEL_NAME,
            "embedding": config.EMBEDDING_MODEL_NAME,
        },
    }
    return mapping.get(config.LLM_MODE, mapping["local"])[role]


def get_client(model_name: str, tracer=None):
    """根據模型名稱選擇 client。

    Args:
        model_name: 模型名稱（如 "qwen3.5:9b" 或 "openai/gpt-4"）
        tracer: 可選的 tracer 物件，用於記錄 trace。

    Returns:
        CloudClient 或 OllamaLocalClient 實例
    """
    if "/" in model_name:
        return CloudClient(tracer=tracer)
    return OllamaLocalClient(tracer=tracer)


async def call_model(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    think: bool = False,
    tools: Optional[List[Dict]] = None,
    caller: Optional[str] = None,
    unit_id: Optional[str] = None,
    step_id: Optional[str] = None,
    tracer: Any = None,
) -> Result:
    """公用模型呼叫函式，供 Optimizer 等模組使用。

    Args:
        model: 模型名稱
        messages: 對話訊息列表
        temperature: 溫度參數
        max_tokens: 最大 token 數
        think: 是否啟用思考模式
        tools: 可選的工具列表
        caller: 呼叫者標識，用於 trace
        unit_id: Unit ID，用於 trace
        step_id: Step ID，用於 trace
        tracer: 可選的 tracer 物件。若未提供，使用全域 tracer。

    Returns:
        Result(success=True, data=content, tool_calls=tool_calls)
    """
    # 優先使用全域 tracer
    effective_tracer = tracer or _global_tracer
    # Resolve role to actual model name
    actual_model = resolve_model(model)
    client = get_client(actual_model, tracer=effective_tracer)
    try:
        response: ChatResponse = await client.chat(
            actual_model, messages, temperature, max_tokens, think, tools,
            caller=caller, unit_id=unit_id, step_id=step_id,
        )
        return Result(
            success=True,
            data=response.content,
            tool_calls=response.tool_calls or [],
        )
    except Exception as e:
        logger.error("[model_client] call_model failed: %s", e, exc_info=True)
        return Result(success=False, error=str(e))


class ModelServiceError(Exception):
    """模型服務異常"""
    pass


async def call_embedding(
    model: str = config.MODEL_EMBEDDING,
    input_text: str = "",
    tracer: Any = None,
) -> Result:
    """公用 embedding 呼叫函式，供 MemoryManager 等模組使用。

    Args:
        model: 模型名稱（預設 config.MODEL_EMBEDDING）
        input_text: 輸入文字
        tracer: 可選的 tracer 物件。若未提供，使用全域 tracer。

    Returns:
        Result(success=True, data=embeddings) 或 Result(success=False, error=str(e))
    """
    # 優先使用全域 tracer
    effective_tracer = tracer or _global_tracer
    actual_model = model or config.MODEL_EMBEDDING
    client = get_client(actual_model, tracer=effective_tracer)
    try:
        embeddings = await client.embed(actual_model, input_text)
        return Result(success=True, data=embeddings)
    except Exception as e:
        logger.error("[model_client] call_embedding failed: %s", e, exc_info=True)
        return Result(success=False, error=str(e))