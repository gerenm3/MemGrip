"""
tests/L2/conftest.py -- 共用 fixture for L2 mock integration tests.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is in sys.path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from models.blueprints import (
    ClarificationState,
    Result,
    Step,
    StepResult,
    StepStatus,
    Unit,
    UnitResult,
    UnitStatus,
)


# ── Blueprint helpers ──────────────────────────────────────────────

@pytest.fixture
def mock_result():
    """Return a minimal Result(success=True)."""
    return Result(success=True, data={})


@pytest.fixture
def mock_unit():
    return Unit(unit_id="u1", goal="goal1", expected_output="expected", output_type="CONTENT")


@pytest.fixture
def mock_step():
    return Step(step_id="s1", goal="step1", output_type="GLOBAL")


@pytest.fixture
def mock_unit_result():
    return UnitResult(
        unit_id="u1",
        status=UnitStatus.SUCCESS,
        output="output",
        error="",
        replan_count=0,
        total_loop_count=1,
        step_loop_counts=[1],
        constraint_checks=[],
    )


@pytest.fixture
def mock_step_result():
    return StepResult(
        step_id="s1",
        status=StepStatus.SUCCESS,
        output="step output",
        error="",
        loop_count=1,
        output_type="GLOBAL",
    )


# ── Mock factories ─────────────────────────────────────────────────

@pytest.fixture
def mock_router():
    router = MagicMock()
    router.route = AsyncMock(return_value=Result(success=True, data={"intent": "simple", "need_rag": False, "domain": "general"}))
    router.probe_server = AsyncMock(return_value=Result(success=True, data="brave_search"))
    router.is_clarification = AsyncMock(return_value=Result(success=True, data={"is_clarification": False}))
    return router


@pytest.fixture
def mock_clarifier():
    clarifier = MagicMock()
    clarifier.clarify = AsyncMock(return_value=Result(success=True, data={
        "goal": "search", "entities": [], "scope": "", "constraints": [], "questions": []
    }))
    return clarifier


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.add = AsyncMock()
    memory.retrieve = AsyncMock(return_value=Result(success=True, data="rag context"))
    memory.flush = AsyncMock(return_value=Result(success=True))
    memory.get_context = AsyncMock(return_value={"buffer": "buffer text", "summary": "summary text", "rag": ""})
    memory.on_activity = MagicMock()
    return memory


@pytest.fixture
def mock_responder():
    responder = MagicMock()
    responder.reply_simple = AsyncMock(return_value=Result(success=True, data="simple reply"))
    responder.reply_tool = AsyncMock(return_value=Result(success=True, data="tool reply"))
    responder.integrate = AsyncMock(return_value=Result(success=True, data="integrated reply"))
    return responder


@pytest.fixture
def mock_health():
    health = MagicMock()
    health.get_user_warnings = MagicMock(return_value=[])
    return health


@pytest.fixture
def mock_lvs():
    lvs = MagicMock()
    lvs.process = AsyncMock(return_value=(None, False))
    return lvs


@pytest.fixture
def mock_tool_manager():
    tm = MagicMock()
    tm.get_server_tools = AsyncMock(return_value=[])
    tm.run_agentic_loop = AsyncMock(return_value=Result(success=True, data="agentic output"))
    tm._init_tools = AsyncMock()
    tm.get_tools = AsyncMock(return_value=[])
    return tm


@pytest.fixture
def mock_scheduler():
    scheduler = MagicMock()
    scheduler.validate_dag = AsyncMock(return_value=Result(success=True))
    scheduler.validate_steps = AsyncMock(return_value=Result(success=True))
    scheduler.schedule = AsyncMock(return_value=Result(success=True, data={
        "execution_order": ["u1"], "unit_step_orders": {"u1": ["s1"]}, "cyclic_units": []
    }))
    return scheduler


@pytest.fixture
def mock_step_planner():
    sp = MagicMock()
    sp.plan_unit = AsyncMock(return_value=Result(success=True, data=[Step(step_id="s1", goal="step1")]))
    return sp


@pytest.fixture
def mock_disassembler():
    ds = MagicMock()
    ds.disassemble = AsyncMock(return_value=Result(success=True, data=[
        Unit(unit_id="u1", goal="goal1"),
        Unit(unit_id="u2", goal="goal2"),
    ]))
    return ds


@pytest.fixture
def mock_executor():
    ex = MagicMock()
    ex.execute = AsyncMock(return_value=Result(success=True, data={"output": "step output", "loop_count": 1}))
    return ex


@pytest.fixture
def mock_verifier():
    v = MagicMock()
    v.verify = AsyncMock(return_value=Result(success=True, data={
        "passed": True, "reason": "OK", "gaps": [], "constraint_checks": []
    }))
    return v


@pytest.fixture
def mock_unit_runner():
    ur = MagicMock()
    ur.execute = AsyncMock(return_value=UnitResult(
        unit_id="u1", status=UnitStatus.SUCCESS, output="unit output",
        error="", replan_count=0, total_loop_count=1, step_loop_counts=[1], constraint_checks=[]
    ))
    return ur


@pytest.fixture
def mock_step_store():
    ss = MagicMock()
    ss.save_step = AsyncMock()
    ss.get_steps_by_unit = MagicMock(return_value=[])
    return ss


@pytest.fixture
def mock_unit_store():
    us = MagicMock()
    us.save_unit = AsyncMock()
    us.get_unit = MagicMock(return_value=None)
    us.get_all_units = MagicMock(return_value=[])
    return us


# ── Config constants ───────────────────────────────────────────────

@pytest.fixture
def max_replan():
    return 2


@pytest.fixture
def max_clarify_rounds():
    return 2


# ── ClarificationState helper ──────────────────────────────────────

@pytest.fixture
def clarification_state_enum():
    """Return the ClarificationState enum class."""
    return ClarificationState


# ── ClarificationResult helper ─────────────────────────────────────

@pytest.fixture
def clarification_result_factory():
    """Factory fixture to build ClarificationResult objects."""
    from core.clarification_manager import ClarificationResult
    def _factory(completed=True, path="pending", clarify_data=None, domain="general",
                 buffer="", summary="", rag="", reply=None):
        return ClarificationResult(
            completed=completed, path=path, clarify_data=clarify_data or {},
            domain=domain, buffer=buffer, summary=summary, rag=rag, reply=reply,
        )
    return _factory


# ── Async loop helper ──────────────────────────────────────────────

@pytest.fixture
def event_loop():
    """Provide a synchronous event loop for asyncio tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ── Memory fixtures ──

@pytest.fixture
def mock_conversation_buffer():
    """Return a mock ConversationBuffer."""
    buf = MagicMock()
    buf.context = []
    buf.flushed = []
    buf.check = MagicMock()
    buf.extract_flushed = MagicMock(return_value=[])
    buf.serialize = MagicMock(return_value="")
    buf.get = MagicMock(return_value=[])
    buf.add = MagicMock()
    return buf


@pytest.fixture
def mock_conversation_summary():
    """Return a mock ConversationSummary."""
    summ = MagicMock()
    summ.summary = ""
    summ.set_summary = MagicMock()
    summ.get_summary = MagicMock(return_value="")
    return summ


@pytest.fixture
def mock_temp_cache():
    """Return a mock TempCache."""
    cache = MagicMock()
    cache.items = []
    cache.add = MagicMock(return_value="test-uuid-0000-0000-0000-000000000001")
    cache.get_top_k = MagicMock(return_value=[])
    cache.remove = MagicMock(return_value=False)
    cache.total_tokens = MagicMock(return_value=0)
    cache.count = MagicMock(return_value=0)
    cache.clear = MagicMock()
    return cache


@pytest.fixture
def mock_conversation_vector():
    """Return a mock ConversationVector with mock ChromaDB collections."""
    vec = MagicMock()
    vec.raw_collection = MagicMock()
    vec.summary_collection = MagicMock()
    vec.add = MagicMock()
    vec.search = MagicMock(return_value=[])
    vec.compare = MagicMock(return_value=1.0)
    vec.repair_consistency = MagicMock(return_value={"summary_only": 0, "raw_only": 0, "cleaned": 0})
    return vec


@pytest.fixture
def mock_summarizer():
    """Return a mock ConversationSummarizer."""
    summ = MagicMock()
    summ.summarize_turns = MagicMock(return_value=Result(success=True, data={"summary": ""}))
    summ.check_importance = MagicMock(return_value=Result(success=True, data={"importance": 0.5}))
    return summ


@pytest.fixture
def mock_summary_store():
    """Return a mock summary store."""
    store = MagicMock()
    store.set_summary = MagicMock()
    store.get_summary = MagicMock(return_value="")
    return store
