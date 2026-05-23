"""Bootstrap — 組裝所有模組並回傳 Orchestrator 實例"""

from typing import Any, Dict, List, Optional
from clients.model_client import OllamaClient
from clients import mcp_client
from memory.buffer import ConversationBuffer
from memory.summary import ConversationSummary, TempCache
from memory.vector import ConversationVector
from core.router import Router
from core.clarifier import Clarifier
from core.planner import Planner
from core.summarizer import Summarizer
from core.batch_summarizer import BatchSummarizer
from core.tool_manager import ToolManager
from core.executor import Executor
from core.responder import Responder
from core.retriever import Retriever
from core.orchestrator import Orchestrator
from core.tracer import new_session


def build_orchestrator() -> Orchestrator:
    """組裝所有模組並回傳 Orchestrator 實例"""
    # 初始化 tracer session
    new_session()

    ollama = OllamaClient()
    call_model = _create_call_model(ollama)
    call_embedding = _create_call_embedding(ollama)

    buffer, summary, vector = _create_memory()
    temp_cache = TempCache()
    router = Router(call_model)
    clarifier = Clarifier(call_model, buffer, summary)
    planner = Planner(call_model)
    batch_summarizer = BatchSummarizer(call_model)
    summarizer = Summarizer(call_model, call_embedding, summary, vector, temp_cache)
    tool_manager = ToolManager(mcp_client, call_model)
    responder = Responder(call_model)
    executor = Executor(call_model, planner, tool_manager.execute_tool, tool_manager)

    return Orchestrator(
        router=router,
        clarifier=clarifier,
        planner=planner,
        executor=executor,
        responder=responder,
        summarizer=summarizer,
        tool_manager=tool_manager,
        buffer=buffer,
        retriever=Retriever(call_embedding, vector),
        summary=summary,
        temp_cache=temp_cache,
        batch_summarizer=batch_summarizer,
    )


def _create_call_model(ollama: OllamaClient) -> Any:
    async def _call_model(
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        think: bool,
        tools: Optional[List[Dict]] = None,
        caller: Optional[str] = None,
        unit_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> tuple:
        return await ollama.chat(model, messages, temperature, max_tokens, think, tools, caller=caller, unit_id=unit_id, step_id=step_id)
    return _call_model


def _create_call_embedding(ollama: OllamaClient) -> Any:
    async def _call_embedding(model: str, input_text: str) -> List[float]:
        return await ollama.embed(model, input_text)
    return _call_embedding


def _create_memory() -> tuple:
    return ConversationBuffer(), ConversationSummary(), ConversationVector()
