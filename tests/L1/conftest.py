"""tests/L1/conftest -- L1 純邏輯測試共用 fixtures."""

import sys
from pathlib import Path
import unittest.mock
import uuid
from unittest.mock import MagicMock

import pytest

# 確保專案根目錄在 sys.path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# 在 conftest 匯入時保存原始 config 值（只執行一次）
_orig_config_values = {}
def _save_original_config():
    import config
    for _attr in ["HEALTH_LOG_PATH", "DEBUG_MODE", "LLM_MODE", "LARGE_MODEL_NAME",
                   "MEDIUM_MODEL_NAME", "EMBEDDING_MODEL_NAME", "CLOUD_MODEL_NAME",
                   "CLOUD_MEDIUM_MODEL_NAME", "SKILL_DIR_BASE", "TASK_TYPES", "PATTERNS_PATH"]:
        if hasattr(config, _attr):
            _orig_config_values[_attr] = getattr(config, _attr)

_save_original_config()

@pytest.fixture(autouse=True)
def _clear_shared_state(request):
    """每個測試前清除所有共享的全域狀態."""
    try:
        import core.health
        core.health._pending_warnings.clear()
        core.health._session_id_var.set(None)
    except Exception:
        pass
    try:
        import clients.model_client
        clients.model_client._global_tracer = None
    except Exception:
        pass
    try:
        import skills.trace_reader
        skills.trace_reader._cache.clear()
    except Exception:
        pass
    # 清除 router/responder module（含 Router 實例的 _patterns_list）
    try:
        sys.modules.pop("core.router", None)
    except Exception:
        pass
    try:
        sys.modules.pop("core.responder", None)
    except Exception:
        pass
    # 還原 config 值
    try:
        import config
        for _attr, _val in _orig_config_values.items():
            setattr(config, _attr, _val)
    except Exception:
        pass
    yield


# ── Unit / Step / Result 建構 helper ──

@pytest.fixture
def make_unit():
    """產生 Unit dataclass 的 factory fixture."""
    from models.blueprints import Unit

    def _make(unit_id="u1", goal="test goal", depends_on=None, output_type="ACTION"):
        return Unit(
            unit_id=unit_id,
            goal=goal,
            depends_on=depends_on or [],
            output_type=output_type,
        )

    return _make


@pytest.fixture
def make_step():
    """產生 Step dataclass 的 factory fixture."""
    from models.blueprints import Step

    def _make(
        step_id="s1",
        goal="test goal",
        output_type="INTERNAL",
        depends_on=None,
        tool=None,
    ):
        return Step(
            step_id=step_id,
            goal=goal,
            output_type=output_type,
            depends_on=depends_on or [],
            tool=tool,
        )

    return _make


@pytest.fixture
def make_result():
    """產生 Result dataclass 的 factory fixture."""
    from models.blueprints import Result

    def _make(success=True, error=None, data=None):
        return Result(success=success, error=error, data=data)

    return _make


# ── UnitStore / StepStore helper ──

@pytest.fixture
def mock_flush_unit_store():
    """mock UnitStore._flush_session 為 pass."""
    from core.storage import UnitStore

    with unittest.mock.patch.object(
        UnitStore, "_flush_session", return_value=None
    ):
        yield


@pytest.fixture
def mock_flush_step_store():
    """mock StepStore._flush_session 為 pass."""
    from core.storage import StepStore

    with unittest.mock.patch.object(
        StepStore, "_flush_session", return_value=None
    ):
        yield


@pytest.fixture
def sample_unit_result():
    """產生 UnitResult dataclass 的 factory fixture."""
    from models.blueprints import UnitResult, UnitStatus

    def _make(
        unit_id="u1",
        status=UnitStatus.SUCCESS,
        output=None,
        error="",
        replan_count=0,
        total_loop_count=0,
        step_loop_counts=None,
        constraint_checks=None,
    ):
        return UnitResult(
            unit_id=unit_id,
            status=status,
            output=output or {},
            error=error,
            replan_count=replan_count,
            total_loop_count=total_loop_count,
            step_loop_counts=step_loop_counts or {},
            constraint_checks=constraint_checks or [],
        )

    return _make


# ── config mock fixtures ──

@pytest.fixture
def mock_config_llm_mode():
    """mock config.LLM_MODE."""
    with unittest.mock.patch("config.LLM_MODE", "local") as m:
        yield m


@pytest.fixture
def mock_config_all_model_names():
    """mock 所有 config 模型名稱."""
    with unittest.mock.patch("config.LLM_MODE", "local") as m1, unittest.mock.patch(
        "config.LARGE_MODEL_NAME", "llama3"
    ), unittest.mock.patch("config.MEDIUM_MODEL_NAME", "llama3-med"), unittest.mock.patch(
        "config.EMBEDDING_MODEL_NAME", "all-minilm"
    ), unittest.mock.patch(
        "config.CLOUD_MODEL_NAME", "openai/gpt-4"
    ), unittest.mock.patch(
        "config.CLOUD_MEDIUM_MODEL_NAME", "openai/gpt-3.5"
    ):
        yield m1


# ── LVS fixture ──

@pytest.fixture
def lvs_instance():
    """LVS instance fixture."""
    from skills.lvs import LVS

    return LVS()


# ── TempCache fixtures ──

@pytest.fixture
def mock_temp_cache_config():
    """mock TempCache 相關的 config 值."""
    with unittest.mock.patch(
        "memory.summary.config.TEMP_CACHE_MAX_ITEMS", 100
    ), unittest.mock.patch(
        "memory.summary.config.TEMP_CACHE_MAX_TOKENS", 10000
    ), unittest.mock.patch(
        "memory.summary.config.TEMP_CACHE_DECAY_LAMBDA", 0.01
    ), unittest.mock.patch(
        "memory.summary.config.TEMP_CACHE_EVICTION_THRESHOLD", 0.1
    ):
        yield


@pytest.fixture
def mock_estimate_tokens():
    """mock estimate_tokens 回傳固定值."""
    with unittest.mock.patch(
        "memory.summary.estimate_tokens", return_value=10
    ) as m:
        yield m


@pytest.fixture
def temp_cache_instance(mock_temp_cache_config):
    """TempCache instance fixture."""
    from memory.summary import TempCache

    return TempCache()


# ── Vector fixtures ──

@pytest.fixture
def mock_chroma_collection():
    """mock ChromaDB collection 的 count/get/query/delete."""
    collection_mock = MagicMock()
    collection_mock.count.return_value = 0
    yield collection_mock


@pytest.fixture
def mock_chroma_client(mock_chroma_collection):
    """mock chromadb.PersistentClient."""
    client_mock = MagicMock()
    client_mock.get_or_create_collection.return_value = mock_chroma_collection
    with unittest.mock.patch(
        "memory.vector.chromadb.PersistentClient", client_mock
    ):
        yield client_mock


@pytest.fixture
def vector_instance(mock_chroma_client, mock_chroma_collection):
    """ConversationVector instance fixture."""
    from memory.vector import ConversationVector

    return ConversationVector()


# ── Health fixtures ──

@pytest.fixture
def mock_health_log_path(tmp_path):
    """mock config.HEALTH_LOG_PATH 指向 tmp_path."""
    log_file = tmp_path / "health.jsonl"
    with unittest.mock.patch(
        "config.HEALTH_LOG_PATH", str(log_file)
    ):
        yield log_file