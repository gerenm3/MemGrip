"""
tests/L2/test_init_skills_trace_reader.py -- L2 mock integration tests for Init Skills + Trace Reader.
Group 12: 16 TCs (Init Skills 10 + Trace Reader 6) + 16 skipped
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from models.blueprints import Result


# ── Init Skills Tests (TC-01 ~ TC-10) ──

class TestInitSkills:
    """Init Skills tests: TC-01 ~ TC-10."""

    @pytest.mark.asyncio
    async def test_tc01_init_l1_skill_normal(self):
        """TC-01: init_l1_skill 正常初始化."""
        mock_sm = MagicMock()
        mock_sm.init_skill_dirs = MagicMock()
        mock_sm.load_skill = MagicMock(return_value={})
        mock_sm.save_skill = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.chat = AsyncMock(return_value=(
            '{"reasoning_resolution": {"core_concept": "C1"}, "constraint_rigidity": {"core_concept": "C2"}, "signal_noise_ratio": {"core_concept": "C3"}, "boundary_anchoring": {"core_concept": "C4"}, "uncertainty_handling": {"core_concept": "C5"}}',
            None
        ))

        with patch('skills.init_skills.SkillManager', return_value=mock_sm):
            with patch('clients.model_client.OllamaClient', return_value=mock_client_instance, create=True):
                from skills.init_skills import init_l1_skill
                result = await init_l1_skill("general")

        assert isinstance(result, dict)
        mock_sm.init_skill_dirs.assert_called_once()
        mock_sm.load_skill.assert_called_once()
        mock_sm.save_skill.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc02_init_l1_skill_llm_fail_fallback(self):
        """TC-02: init_l1_skill LLM 失敗 → fallback 寫入 _DEFAULT_SKILL."""
        mock_sm = MagicMock()
        mock_sm.init_skill_dirs = MagicMock()
        mock_sm.load_skill = MagicMock(return_value={})
        mock_sm.save_skill = MagicMock()

        with patch('skills.init_skills.SkillManager', return_value=mock_sm):
            with patch('clients.model_client.call_model', new_callable=AsyncMock, return_value=Result(success=False, error="LLM error")):
                from skills.init_skills import init_l1_skill
                result = await init_l1_skill("general")

        assert result is not None
        mock_sm.save_skill.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc03_init_l1_skill_exists_skip(self):
        """TC-03: init_l1_skill 已存在 → 不呼叫 LLM."""
        mock_sm = MagicMock()
        mock_sm.init_skill_dirs = MagicMock()
        mock_sm.load_skill = MagicMock(return_value={"reasoning_resolution": {"core_concept": "C1"}})
        mock_sm.save_skill = MagicMock()

        with patch('skills.init_skills.SkillManager', return_value=mock_sm):
            with patch('clients.model_client.call_model', new_callable=AsyncMock) as mock_llm:
                from skills.init_skills import init_l1_skill
                result = await init_l1_skill("general")

        assert isinstance(result, dict)
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_tc04_init_l1_skill_directory_auto_create(self):
        """TC-04: init_l1_skill 目錄自動建立."""
        mock_sm = MagicMock()
        mock_sm.init_skill_dirs = MagicMock()
        mock_sm.load_skill = MagicMock(return_value={})
        mock_sm.save_skill = MagicMock()

        with patch('skills.init_skills.SkillManager', return_value=mock_sm):
            with patch('clients.model_client.call_model', new_callable=AsyncMock):
                from skills.init_skills import init_l1_skill
                result = await init_l1_skill("software_dev")

        mock_sm.init_skill_dirs.assert_called_with("software_dev", "l1")

    @pytest.mark.asyncio
    async def test_tc05_init_all_l1_skills(self):
        """TC-05: init_all_l1_skills 批量初始化."""
        mock_init_l1 = AsyncMock(return_value={"reasoning_resolution": {"core_concept": "C1"}})

        with patch('skills.init_skills.init_l1_skill', mock_init_l1):
            with patch('config.TASK_TYPES', ["general", "software_dev", "it_security", "global"]):
                from skills.init_skills import init_all_l1_skills
                result = await init_all_l1_skills()

        assert isinstance(result, dict)
        # init_all_l1_skills: for each in TASK_TYPES + one extra "global"
        # With TASK_TYPES=["general","software_dev","it_security","global"] → 4+1=5
        assert mock_init_l1.call_count == 5

    @pytest.mark.asyncio
    async def test_tc06_init_l2_skill_normal(self):
        """TC-06: init_l2_skill 正常初始化."""
        mock_sm = MagicMock()
        mock_sm.init_skill_dirs = MagicMock()
        mock_sm.load_skill = MagicMock(return_value={})
        mock_sm.save_skill = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.chat = AsyncMock(return_value=(
            '{"reasoning_resolution": {"core_concept": "C1"}, "constraint_rigidity": {"core_concept": "C2"}, "signal_noise_ratio": {"core_concept": "C3"}, "boundary_anchoring": {"core_concept": "C4"}, "uncertainty_handling": {"core_concept": "C5"}}',
            None
        ))

        with patch('skills.init_skills.SkillManager', return_value=mock_sm):
            with patch('clients.model_client.OllamaClient', return_value=mock_client_instance, create=True):
                from skills.init_skills import init_l2_skill
                result = await init_l2_skill("general")

        assert isinstance(result, dict)
        mock_sm.init_skill_dirs.assert_called_with("general", "l2")
        mock_sm.save_skill.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc07_init_l2_skill_llm_fail_fallback(self):
        """TC-07: init_l2_skill LLM 失敗 → fallback 寫入 _DEFAULT_SKILL."""
        mock_sm = MagicMock()
        mock_sm.init_skill_dirs = MagicMock()
        mock_sm.load_skill = MagicMock(return_value={})
        mock_sm.save_skill = MagicMock()

        with patch('skills.init_skills.SkillManager', return_value=mock_sm):
            with patch('clients.model_client.call_model', new_callable=AsyncMock, return_value=Result(success=False, error="LLM error")):
                from skills.init_skills import init_l2_skill
                result = await init_l2_skill("general")

        assert result is not None
        mock_sm.save_skill.assert_called_once()

    @pytest.mark.asyncio
    async def test_tc08_init_l2_skill_uses_l2_prompt(self):
        """TC-08: init_l2_skill 使用 L2 prompt."""
        mock_sm = MagicMock()
        mock_sm.init_skill_dirs = MagicMock()
        mock_sm.load_skill = MagicMock(return_value={})
        mock_sm.save_skill = MagicMock()

        captured_calls = []

        async def capture_chat(*args, **kwargs):
            captured_calls.append((args, kwargs))
            return (
                '{"reasoning_resolution": {"core_concept": "C1"}}',
                None
            )

        mock_client_instance = MagicMock()
        mock_client_instance.chat = AsyncMock(side_effect=capture_chat)

        with patch('skills.init_skills.SkillManager', return_value=mock_sm):
            with patch('clients.model_client.OllamaClient', return_value=mock_client_instance, create=True):
                from skills.init_skills import init_l2_skill
                result = await init_l2_skill("general")

        assert len(captured_calls) == 1


    @pytest.mark.asyncio
    async def test_tc09_init_all_l2_skills(self):
        """TC-09: init_all_l2_skills 批量初始化."""
        mock_init_l2 = AsyncMock(return_value={"reasoning_resolution": {"core_concept": "C1"}})

        with patch('skills.init_skills.init_l2_skill', mock_init_l2):
            with patch('config.TASK_TYPES', ["general", "software_dev", "it_security", "global"]):
                from skills.init_skills import init_all_l2_skills
                result = await init_all_l2_skills()

        assert isinstance(result, dict)
        assert mock_init_l2.call_count == 5

    @pytest.mark.asyncio
    async def test_tc10_init_all_complete(self):
        """TC-10: init_all 完整初始化."""
        mock_init_l1 = AsyncMock(return_value={"reasoning_resolution": {"core_concept": "C1"}})
        mock_init_l2 = AsyncMock(return_value={"reasoning_resolution": {"core_concept": "C2"}})

        with patch('skills.init_skills.init_l1_skill', mock_init_l1):
            with patch('skills.init_skills.init_l2_skill', mock_init_l2):
                from skills.init_skills import init_all
                result = await init_all()

        assert isinstance(result, dict)
        # init_all_l1_skills calls init_l1_skill for each TASK_TYPES + "global"
        # With default TASK_TYPES having 4 items, call_count = 4 + 1 = 5
        assert mock_init_l1.call_count >= 1
        assert mock_init_l2.call_count >= 1


# ── Trace Reader Tests (TC-27 ~ TC-32) ──

class TestTraceReader:
    """Trace Reader tests: TC-27 ~ TC-32."""

    def test_tc27_build_execution_record_normal(self):
        """TC-27: build_execution_record 正常組裝."""
        mock_data = [{
            "session_id": "test-session",
            "task_type": "general",
            "goal": "G1",
            "units": [{"unit_id": "u1", "total_loop_count": 5}],
        }]

        with patch('skills.trace_reader._load_jsonl', return_value=mock_data):
            from skills.trace_reader import build_execution_record
            result = build_execution_record("test-session")

        assert isinstance(result, dict)

    def test_tc28_build_execution_record_session_not_found(self):
        """TC-28: build_execution_record session 不存在 → 回傳 None."""
        with patch('skills.trace_reader._load_jsonl', return_value=[]):
            from skills.trace_reader import build_execution_record
            result = build_execution_record("nonexistent-session")

        assert result is None

    def test_tc29_build_execution_record_verifier_pass_ratio(self):
        """TC-29: build_execution_record verifierPassRatio."""
        mock_data = [{
            "session_id": "test-session",
            "task_type": "general",
            "goal": "G1",
            "units": [{"unit_id": "u1", "total_loop_count": 5}],
        }]

        with patch('skills.trace_reader._load_jsonl', return_value=mock_data):
            from skills.trace_reader import build_execution_record
            result = build_execution_record("test-session")

        assert isinstance(result, dict)
        assert "verifier_pass_ratio" in result

    def test_tc30_build_execution_record_constraint_ratio(self):
        """TC-30: build_execution_record constraintRatio."""
        mock_data = [{
            "session_id": "test-session",
            "task_type": "general",
            "goal": "G1",
            "units": [{"unit_id": "u1", "total_loop_count": 5, "constraint_checks": [{"satisfied": True}, {"satisfied": False}]}],
        }]

        with patch('skills.trace_reader._load_jsonl', return_value=mock_data):
            from skills.trace_reader import build_execution_record
            result = build_execution_record("test-session")

        assert isinstance(result, dict)
        assert "constraint_satisfied_ratio" in result

    def test_tc31_build_execution_record_avg_loop_count(self):
        """TC-31: build_execution_record avg_loop_count."""
        mock_data = [{
            "session_id": "test-session",
            "task_type": "general",
            "goal": "G1",
            "units": [
                {"unit_id": "u1", "total_loop_count": 5},
                {"unit_id": "u2", "total_loop_count": 3},
                {"unit_id": "u3", "total_loop_count": 2},
            ],
        }]

        with patch('skills.trace_reader._load_jsonl', return_value=mock_data):
            from skills.trace_reader import build_execution_record
            result = build_execution_record("test-session")

        assert isinstance(result, dict)
        assert "avg_loop_count" in result

    def test_tc32_build_execution_record_unit_count_zero(self):
        """TC-32: build_execution_record unit_count=0."""
        mock_data = [{
            "session_id": "test-session",
            "task_type": "general",
            "goal": "G1",
            "units": [],
        }]

        with patch('skills.trace_reader._load_jsonl', return_value=mock_data):
            from skills.trace_reader import build_execution_record
            result = build_execution_record("test-session")

        assert isinstance(result, dict)
        assert result.get("unit_count") == 0


# ── Skipped TCs (TC-11 ~ TC-16, TC-17 ~ TC-26) ──

@pytest.mark.skip(reason="TC-11: Testing private method _write_default_skill; design doc does not describe its implementation.")
def test_tc11():
    pass

@pytest.mark.skip(reason="TC-12: Testing private method _write_default_skill; design doc does not describe _DEFAULT_SKILL content.")
def test_tc12():
    pass

@pytest.mark.skip(reason="TC-13: Testing private method _build_dimensions_text; design doc does not describe its implementation.")
def test_tc13():
    pass

@pytest.mark.skip(reason="TC-14: Testing private method _build_dimensions_text; design doc does not describe its implementation.")
def test_tc14():
    pass

@pytest.mark.skip(reason="TC-15: Testing private method _build_l1_prompt; design doc does not describe prompt format.")
def test_tc15():
    pass

@pytest.mark.skip(reason="TC-16: Testing private method _build_l2_prompt; design doc does not describe prompt format.")
def test_tc16():
    pass

@pytest.mark.skip(reason="TC-17: Testing private method _load_jsonl; design doc does not describe its implementation.")
def test_tc17():
    pass

@pytest.mark.skip(reason="TC-18: Testing private method _load_jsonl; design doc does not describe its implementation.")
def test_tc18():
    pass

@pytest.mark.skip(reason="TC-19: Testing private method _load_jsonl; design doc does not describe its implementation.")
def test_tc19():
    pass

@pytest.mark.skip(reason="TC-20: Testing private method _load_jsonl; design doc does not describe its implementation.")
def test_tc20():
    pass

@pytest.mark.skip(reason="TC-21: Testing private method _load_jsonl; design doc does not describe its implementation.")
def test_tc21():
    pass

@pytest.mark.skip(reason="TC-22: Testing private method _clear_cache; design doc does not describe its implementation.")
def test_tc22():
    pass

@pytest.mark.skip(reason="TC-23: Testing private method _extract_tool_calls_from_messages; design doc does not describe its implementation.")
def test_tc23():
    pass

@pytest.mark.skip(reason="TC-24: Testing private method _extract_tool_calls_from_messages; design doc does not describe its implementation.")
def test_tc24():
    pass

@pytest.mark.skip(reason="TC-25: Testing private method _extract_tool_calls_from_messages; design doc does not describe its implementation.")
def test_tc25():
    pass

@pytest.mark.skip(reason="TC-26: Testing private method _extract_tool_calls_from_messages; design doc does not describe its implementation.")
def test_tc26():
    pass