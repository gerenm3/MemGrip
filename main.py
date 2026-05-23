"""
MemGrip - Entry Point
Basic chat loop with Ollama backend.
Memory layer will be integrated in Week 2-3.
"""

import argparse
import asyncio
from bootstrap import build_orchestrator


async def run_task_mode(orchestrator: object, task: str) -> None:
    """非互動式模式：執行單一任務後退出"""
    await orchestrator.tool_manager._init_tools()

    from core.tracer import new_session as tracer_new_session
    tracer_new_session()

    # 設定 session_id（非互動式模式需在 run_task_mode 中手動初始化）
    orchestrator._current_session_id = tracer_new_session()

    # 分流階段
    route_result = await orchestrator.router.route(task)
    intent = route_result['intent']

    # 非互動式模式不進行 RAG（無對話歷史）
    rag_content = ""

    # 依意圖分流處理
    has_tools = bool(orchestrator.tool_manager.server_schemas)
    reply = await orchestrator._dispatch_by_intent(intent, task, rag_content, has_tools)

    # 寫入 buffer 與 trace
    orchestrator.buffer.add("user", task)
    orchestrator.buffer.add("assistant", reply)
    orchestrator._summarize_if_needed()

    print(f"MemGrip: {reply}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MemGrip - AI Task Orchestrator")
    parser.add_argument("--task", type=str, help="Execute a single task non-interactively")
    args = parser.parse_args()

    orchestrator = build_orchestrator()

    if args.task:
        asyncio.run(run_task_mode(orchestrator, args.task))
    else:
        asyncio.run(orchestrator.run())
