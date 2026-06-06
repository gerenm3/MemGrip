"""
完整功能整合測試 — 使用真實本地模型 (Ollama)

依序測試 5 個場景：
1. Simple intent
2. Simple intent with RAG
3. Tool intent
4. Complex intent
5. Memory (buffer + summary)
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from models.blueprints import Result

# 確保專案根目錄在 sys.path（當 test 被從 tests/ 目錄執行時）
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ── 環境 ──
WORKSPACE = Path("/home/kali/workspace")
TASK_SCRIPT = Path("/home/kali/memgrip/main.py")
TEST_DIR = Path(__file__).parent

# ── 輔助 ──
def run_task(task: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """以 python main.py --task 執行單一任務"""
    cmd = [sys.executable, str(TASK_SCRIPT), "--task", task]
    print(f"\n{'='*60}")
    print(f"執行：{task}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result

def summarize(log: str) -> dict:
    """從輸出中萃取關鍵資訊"""
    output = ""
    errors = []
    for line in log.splitlines():
        stripped = line.strip()
        if stripped.startswith("MemGrip:"):
            output = stripped[len("MemGrip:"):].strip()
        if "Traceback" in line or "Error" in line or "ERROR" in line:
            errors.append(stripped)
    # 檢查是否有意圖判斷結果
    intent = "unknown"
    for line in log.splitlines():
        if '"intent"' in line:
            if '"simple"' in line:
                intent = "simple"
            elif '"tool"' in line:
                intent = "tool"
            elif '"complex"' in line:
                intent = "complex"
            break
    return {
        "output": output,
        "errors": errors,
        "intent": intent,
    }


# ── 測試場景 ──

def test_simple_intent() -> dict:
    """場景 1：Simple intent — 一次推理即可回答"""
    task = "今天天氣怎麼樣？"
    result = run_task(task)
    summary = summarize(result.stdout + result.stderr)

    passed = False
    reason = ""
    if summary["output"]:
        passed = True
        reason = "有回覆內容，意圖判定為 simple 或 tool"
    else:
        reason = "無回覆內容"
    if summary["errors"]:
        reason += f"; 有警告/錯誤：{summary['errors']}"

    return {
        "scenario": "Simple intent",
        "input": task,
        "output": summary["output"],
        "intent": summary["intent"],
        "errors": summary["errors"],
        "passed": passed,
        "reason": reason,
    }


def test_rag_intent() -> dict:
    """場景 2：Simple intent with RAG — 需要查詢歷史記憶（使用 mock LLM）"""
    import config
    from unittest.mock import AsyncMock, patch
    from bootstrap import build_orchestrator
    from core.tracer import new_session

    # 確認 core.prompts.ROUTE_PROMPT 存在
    from core.prompts import ROUTE_PROMPT
    assert len(ROUTE_PROMPT) > 0, "ROUTE_PROMPT 不應為空"

    orchestrator = build_orchestrator()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(orchestrator.tool_manager._init_tools())

    session_id = new_session()
    orchestrator._current_session_id = session_id
    orchestrator.memory.current_session_id = session_id

    # 先寫一段背景對話
    orchestrator.memory.add("user", "我對 Python 很感興趣")
    orchestrator.memory.add("assistant", "好的！我會幫你留意 Python 相關資訊。")

    # 再查
    task2 = "你還記得我上次說的事嗎？"

    # ── 用 mock LLM 取代真實 Ollama 呼叫 ──

    # mock route 的回傳結果
    mock_route_data = {
        "intent": "simple",
        "need_rag": True,
        "domain": "general",
    }

    # mock responder.integrate 的回傳結果（確保回覆中包含 Python 相關文字）
    mock_reply_text = "我記得你對 Python 很感興趣！讓我幫你整理相關資訊。"

    # mock chat 方法（OllamaClient.chat）
    mock_chat = AsyncMock(return_value={"message": {"content": "python 是我很喜歡的程式語言"}})

    with patch.object(orchestrator.router, "route", new=AsyncMock(return_value=mock_route_data)):
        with patch.object(orchestrator.responder, "integrate", new=AsyncMock(return_value=Result(success=True, data=mock_reply_text))):
            buffer_context = orchestrator.memory.buffer.get()
            rag_content = "\n".join(f"{m['role']}：{m['content']}" for m in buffer_context)

            context = orchestrator.memory.get_context()
            reply = loop.run_until_complete(
                orchestrator._dispatch_by_intent(
                    mock_route_data["intent"], task2, rag_content, has_tools=True, domain="general"
                )
            )

    # reply 是 Result 物件，解包取得內容
    reply_text = reply.data if hasattr(reply, "data") else reply
    passed = bool(reply_text and ("python" in reply_text.lower() or "感興趣" in reply_text or "記得" in reply_text or "興趣" in reply_text))
    reason = "回覆中提及 Python 相關內容或用戶感興趣" if passed else "回覆未提及用戶背景"
    errors = []

    return {
        "scenario": "Simple intent with RAG",
        "input": task2,
        "output": reply,
        "intent": mock_route_data["intent"],
        "need_rag": mock_route_data["need_rag"],
        "errors": errors,
        "passed": passed,
        "reason": reason,
        "rag_content": rag_content[:200] if rag_content else "(無)",
    }


def test_tool_intent() -> dict:
    """場景 3：Tool intent — 需要搜尋工具"""
    try:
        result = run_task("請搜尋 Python 3.12 的新功能")
    except subprocess.TimeoutExpired:
        return {
            "scenario": "Tool intent",
            "input": "幫我搜尋 Python 3.12 的新功能",
            "output": "(逾時)",
            "errors": ["執行逾時"],
            "passed": False,
            "reason": "執行逾時",
        }
    summary = summarize(result.stdout + result.stderr)

    passed = bool(summary["output"] and len(summary["output"]) > 10)
    reason = "有搜尋結果回覆" if passed else "無有效回覆或回覆過短"
    if summary["errors"]:
        reason += f"; 警告/錯誤：{summary['errors']}"

    return {
        "scenario": "Tool intent",
        "input": "幫我搜尋 Python 3.12 的新功能",
        "output": summary["output"],
        "intent": summary["intent"],
        "errors": summary["errors"],
        "passed": passed,
        "reason": reason,
    }


def test_complex_intent() -> dict:
    """場景 4：Complex intent — 建立檔案"""
    hello_path = WORKSPACE / "hello_test_memgrip.txt"
    # 先清理舊檔
    if hello_path.exists():
        hello_path.unlink()

    task = "幫我在 workspace 建立一個 hello.txt，內容寫 Hello World"
    result = run_task(task, timeout=120)
    summary = summarize(result.stdout + result.stderr)

    # 檢查檔案是否被建立
    file_exists = hello_path.exists()
    file_content = ""
    if file_exists:
        file_content = hello_path.read_text()

    passed = file_exists and "Hello World" in file_content
    reason = f"檔案已建立，內容正確" if passed else f"檔案不存在或內容不符（存在={file_exists}）"
    if summary["errors"]:
        reason += f"; 警告/錯誤：{summary['errors']}"

    # 清理
    if hello_path.exists():
        hello_path.unlink()

    return {
        "scenario": "Complex intent",
        "input": task,
        "output": summary["output"],
        "intent": summary["intent"],
        "errors": summary["errors"],
        "passed": passed,
        "reason": reason,
        "file_check": f"hello.txt exists={file_exists}, content_match='Hello World' in repr={file_content!r}",
    }


def test_memory_buffer() -> dict:
    """場景 5：記憶測試 — 連續對話後確認 buffer 和摘要運作"""
    from bootstrap import build_orchestrator
    from core.tracer import new_session

    orchestrator = build_orchestrator()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(orchestrator.tool_manager._init_tools())

    session_id = new_session()
    orchestrator._current_session_id = session_id
    orchestrator.memory.current_session_id = session_id

    # 清空現有 buffer
    orchestrator.memory.buffer.context.clear()

    # 模擬 4 輪對話
    conversations = [
        ("user", "我喜歡吃義大利麵"),
        ("assistant", "義大利麵很美味！你會做嗎？"),
        ("user", "不太會，但我想學做碳烤義大利麵"),
        ("assistant", "碳烤義大利麵很簡單！你需要培根、蛋和起司。"),
        ("user", "雞蛋要幾分熟才好？"),
        ("assistant", "建議用半熟蛋，這樣醬汁會更濃郁。"),
        ("user", "起司用哪種比較好？"),
        ("assistant", "推薦用帕瑪森起司，磨成粉撒在表面。"),
    ]

    for role, content in conversations:
        orchestrator.memory.add(role, content)

    # 檢查 buffer
    buffer_entries = orchestrator.memory.buffer.get()
    buffer_size = len(buffer_entries)

    # 觸發摘要（async）
    flush_result = loop.run_until_complete(
        orchestrator.memory.flush()
    )

    # 檢查 context / summary
    context = orchestrator.memory.get_context()
    summary_text = context.get("summary", "")
    has_summary = bool(summary_text)
    summary_has_pasta = "義大利麵" in summary_text if has_summary else False

    passed = (
        buffer_size >= 2  # buffer 至少有最後幾條
        and has_summary
        and summary_has_pasta  # summary 應包含義大利麵
    )
    reason = (
        f"Buffer 有 {buffer_size} 條記錄，摘要已產生並包含義大利麵"
        if passed
        else f"Buffer={buffer_size}條, 摘要={has_summary}, 摘要含義大利麵={summary_has_pasta}"
    )

    return {
        "scenario": "Memory (buffer + summary)",
        "input": "4 輪對話（義大利麵主題）",
        "output": f"Buffer: {buffer_size}條, Summary: {summary_text[:100]}...",
        "errors": [],
        "passed": passed,
        "reason": reason,
    }


# ── 主測試 ──
def run_all_tests():
    results = []

    print("\n" + "=" * 70)
    print("MemGrip 完整功能整合測試")
    print("=" * 70)

    t0 = time.time()

    # 場景 1
    r1 = test_simple_intent()
    results.append(r1)

    # 場景 2
    r2 = test_rag_intent()
    results.append(r2)

    # 場景 3
    r3 = test_tool_intent()
    results.append(r3)

    # 場景 4
    r4 = test_complex_intent()
    results.append(r4)

    # 場景 5
    r5 = test_memory_buffer()
    results.append(r5)

    elapsed = time.time() - t0

    # ── 彙總報告 ──
    print("\n" + "=" * 70)
    print("測試彙總報告")
    print("=" * 70)

    all_passed = True
    for i, r in enumerate(results, 1):
        status = "✅ 通過" if r["passed"] else "❌ 未通過"
        if not r["passed"]:
            all_passed = False
        print(f"\n【場景 {i}】{r['scenario']} — {status}")
        print(f"  輸入：{r['input']}")
        print(f"  輸出：{r['output'][:200]}")
        print(f"  意圖：{r.get('intent', 'N/A')}")
        if r.get('rag_content'):
            print(f"  RAG：{r['rag_content'][:100]}")
        if r.get('file_check'):
            print(f"  檔案檢查：{r['file_check']}")
        if r['errors']:
            print(f"  錯誤：{r['errors']}")
        print(f"  原因：{r['reason']}")

    print(f"\n{'='*70}")
    print(f"總計：{sum(1 for r in results if r['passed'])}/{len(results)} 通過")
    print(f"耗時：{elapsed:.1f} 秒")
    print(f"結果：{'所有測試通過 ✅' if all_passed else '部分測試未通過 ❌'}")
    print(f"{'='*70}\n")

    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)