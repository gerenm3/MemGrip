"""MemGrip — 入口點.

依據架構設計：
- 入口點，呼叫 bootstrap.build_orchestrator()
- 啟動 orchestrator.run()
- 支援 --task 參數進行非互動式模式
- 符合 logging 規範（禁止 print 用於模組輸出，僅用於 CLI 使用者互動）
"""

import argparse
import asyncio
import logging

import config as config
from bootstrap import build_orchestrator

logger = logging.getLogger(__name__)


async def run_task_mode(orchestrator, task: str) -> None:
    """非互動式模式：執行單一任務後退出.

    Args:
        orchestrator: Orchestrator 實例
        task: 要執行的任務
    """
    from core.tracer import new_session

    # 初始化工具
    await orchestrator.tool_manager._init_tools()

    # 建立 session
    session_id = new_session()
    orchestrator._session_id = session_id

    # 初始化 storage（與 orchestrator.run() 一致）
    from core.storage import UnitStore, StepStore
    orchestrator._unit_store = UnitStore()
    orchestrator._step_store = StepStore()

    # 路由
    route_result = await orchestrator.router.route(task)
    if not route_result.success:
        logger.error("[main] 路由失敗: %s", route_result.error)
        print(f"MemGrip: 路由失敗: {route_result.error}")
        return

    intent = route_result.data.get("intent", "simple")
    domain = route_result.data.get("domain", "general")

    # 非互動式模式不進行 RAG（無對話歷史）
    rag = ""

    # 準備 context
    context = orchestrator.memory.get_context()
    buffer = context.get("buffer", "")
    summary = context.get("summary", "")

    # 依意圖分流
    if intent == "simple":
        system_prompt = orchestrator._build_system_prompt(domain)
        reply_result = await orchestrator.responder.reply_simple(
            system_prompt=system_prompt,
            user_input=task,
            buffer=buffer,
            summary=summary,
            rag=rag,
        )
        reply = reply_result.data or "無法生成回覆。"
    elif intent == "tool":
        reply = await orchestrator._dispatch_tool(task, buffer, summary, rag)
    elif intent == "complex":
        reply = await orchestrator._dispatch_complex(task, buffer, summary, rag, domain)
    else:
        system_prompt = orchestrator._build_system_prompt(domain)
        reply_result = await orchestrator.responder.reply_simple(
            system_prompt=system_prompt,
            user_input=task,
            buffer=buffer,
            summary=summary,
            rag=rag,
        )
        reply = reply_result.data or "無法生成回覆。"

    # 寫入 memory
    orchestrator.memory.add("user", task)
    orchestrator.memory.add("assistant", reply)

    # 非同步 flush
    await orchestrator._summarize_if_needed()

    # 等待所有背景 task 完成（例如 optimizer）
    pending = asyncio.all_tasks()
    pending.discard(asyncio.current_task())
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    print(f"MemGrip: {reply}")


async def _init_skills() -> None:
    """初始化 skill 目錄與 skill guide（LLM 生成 + fallback）."""
    from skills.init_skills import init_all
    await init_all()
    logger.info("[main] skills initialized")


def main() -> None:
    """主入口點"""
    parser = argparse.ArgumentParser(description="MemGrip v2 - AI Task Orchestrator")
    parser.add_argument("--task", type=str, help="執行單一任務後退出")
    args = parser.parse_args()

    asyncio.run(_init_skills())
    orchestrator = build_orchestrator()

    if args.task:
        asyncio.run(run_task_mode(orchestrator, args.task))
    else:
        asyncio.run(orchestrator.run())


if __name__ == "__main__":
    main()