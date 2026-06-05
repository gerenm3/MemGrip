"""v2 bootstrap — 組裝所有 v2 模組並回傳 Orchestrator 實例.

依據 v2 架構設計：
- 使用 DI 注入所有依賴
- 直接注入 OllamaClient 實例（底層使用 LiteLLM）
- 符合 v2 logging 規範
"""

import logging

from core.orchestrator import Orchestrator
from core.router import Router
from core.clarifier import Clarifier
from core.disassembler import Disassembler
from core.step_planner import StepPlanner
from core.scheduler import Scheduler
from core.executor import Executor
from core.verifier import Verifier
from core.responder import Responder
from core.tool_manager import ToolManager
from clients.mcp_client import MCPClient
from clients.model_client import call_model as _call_model
from clients.model_client import call_embedding as _call_embedding
from memory.manager import MemoryManager
from memory.vector import ConversationVector
from memory.summary import ConversationSummary, TempCache
from memory.summarizer import ConversationSummarizer
from memory.buffer import ConversationBuffer
from skills.lvs import LVS
from skills.skill_manager import SkillManager
from skills.optimizer import Optimizer
from models.blueprints import Result

logger = logging.getLogger(__name__)


def _build_call_model(tracer) -> callable:
    """建立 call_model 函式，供各模組使用.

    Args:
        tracer: tracer 實例

    Returns:
        call_model 函式
    """
    async def call_model(
        model: str,
        messages: list,
        temperature: float,
        max_tokens: int,
        think: bool,
        tools: list = None,
        caller: str = None,
        unit_id: str = None,
        step_id: str = None,
    ) -> Result:
        return await _call_model(model, messages, temperature, max_tokens, think, tools, caller, unit_id, step_id, tracer=tracer)
    return call_model


def _build_call_embedding(tracer) -> callable:
    """建立 call_embedding 函式，供 MemoryManager 使用.

    Args:
        tracer: tracer 實例

    Returns:
        call_embedding 函式
    """
    async def call_embedding(model: str, input_text: str) -> Result:
        return await _call_embedding(model, input_text, tracer=tracer)
    return call_embedding


async def build_orchestrator() -> Orchestrator:
    """組裝所有 v2 模組並回傳 Orchestrator 實例.

    Returns:
        Orchestrator 實例
    """
    from core.tracer import new_session, Tracer
    from clients.model_client import set_global_tracer

    # 初始化 tracer
    new_session()
    tracer = Tracer()
    # 設定全域 tracer，供 optimizer / signal_collector 等直接 import call_model 的模組使用
    set_global_tracer(tracer)

    # 建立呼叫函式（注入 tracer）
    call_model = _build_call_model(tracer)
    call_embedding = _build_call_embedding(tracer)

    # Memory Layer
    vector = ConversationVector()
    summary = ConversationSummary()
    temp_cache = TempCache()
    buffer = ConversationBuffer()

    # Summarizer（LLM 邏輯）
    summarizer = ConversationSummarizer(call_model, call_embedding)

    memory = MemoryManager(
        call_embedding_func=call_embedding,
        vector_store=vector,
        summary_store=summary,
        temp_cache=temp_cache,
        summarizer=summarizer,
    )

    # Core Modules
    router = Router(call_model_func=call_model)
    clarifier = Clarifier(call_model_func=call_model, buffer=buffer, summary=summary)
    disassembler = Disassembler(call_model_func=call_model)
    step_planner = StepPlanner(call_model_func=call_model)
    scheduler = Scheduler()
    mcp_client = MCPClient()
    tool_manager = ToolManager(mcp_client=mcp_client, call_model_func=call_model)
    await tool_manager.initialize()
    # Executor 需要 execute_tool_func: (tool_name, tool_args) -> Result
    # 這裡傳入一個 wrapper，因為 ToolManager.execute_tool 需要 server_name
    async def execute_tool(tool_name: str, tool_args: dict):
        # 預設使用第一個可用的 server
        return await tool_manager.execute_tool("file_rw", tool_name, tool_args)
    executor = Executor(call_model_func=call_model, execute_tool_func=execute_tool)
    verifier = Verifier(call_model_func=call_model)
    responder = Responder(call_model_func=call_model)

    # Skills
    lvs = LVS()
    skill_manager = SkillManager()

    return Orchestrator(
        router=router,
        clarifier=clarifier,
        disassembler=disassembler,
        step_planner=step_planner,
        executor=executor,
        verifier=verifier,
        responder=responder,
        tool_manager=tool_manager,
        scheduler=scheduler,
        memory=memory,
        lvs=lvs,
        skill_manager=skill_manager,
    )

