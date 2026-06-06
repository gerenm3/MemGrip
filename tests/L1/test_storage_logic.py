"""tests/L1/test_storage_logic.py — core/storage.py 純邏輯測試（12 筆）."""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import unittest.mock

from models.blueprints import UnitResult, StepResult, UnitStatus
from core.storage import UnitStore, StepStore


class TestUnitStore:
    """UnitStore 測試."""

    @pytest.fixture
    def mock_storage_dir(self, tmp_path):
        with unittest.mock.patch("core.storage._STORAGE_DIR", tmp_path):
            yield tmp_path

    @pytest.fixture
    def mock_flush(self, mock_storage_dir):
        with unittest.mock.patch.object(
            UnitStore, "_flush_session", return_value=None
        ):
            yield

    def test_save_and_get_unit(self, mock_flush):
        """等價類：儲存後取得相同 UnitResult."""
        from core.storage import UnitStore
        store = UnitStore()
        result = UnitResult(unit_id="u1", status=UnitStatus.SUCCESS, output={"data": "ok"})
        store.save_unit("s1", "u1", result)
        fetched = store.get_unit("s1", "u1")
        assert fetched is not None
        assert fetched.unit_id == "u1"
        assert fetched.status == UnitStatus.SUCCESS

    def test_get_all_units(self, mock_flush):
        """等價類：取得同一 session 所有 units."""
        from core.storage import UnitStore
        store = UnitStore()
        store.save_unit("s1", "u1", UnitResult(unit_id="u1", status=UnitStatus.SUCCESS))
        store.save_unit("s1", "u2", UnitResult(unit_id="u2", status=UnitStatus.FAILED))
        units = store.get_all_units("s1")
        assert len(units) == 2

    def test_get_nonexistent(self, mock_flush):
        """邊界：取得不存在的 unit → None."""
        from core.storage import UnitStore
        store = UnitStore()
        fetched = store.get_unit("s1", "nonexistent")
        assert fetched is None

    def test_session_isolation(self, mock_flush):
        """等價類：不同 session 資料隔離."""
        from core.storage import UnitStore
        store = UnitStore()
        store.save_unit("s1", "u1", UnitResult(unit_id="u1", status=UnitStatus.SUCCESS))
        fetched = store.get_unit("s2", "u1")
        assert fetched is None

    def test_flush_writes_file(self, mock_storage_dir):
        """等價類：flush 寫入檔案."""
        from core.storage import UnitStore
        store = UnitStore()
        store.save_unit("s1", "u1", UnitResult(unit_id="u1", status=UnitStatus.SUCCESS))
        file_path = mock_storage_dir / "units_s1.json"
        assert file_path.exists()
        content = file_path.read_text()
        data = json.loads(content)
        assert "u1" in data

    def test_empty_store(self, mock_flush):
        """邊界：空 store → get_all_units 回 []."""
        from core.storage import UnitStore
        store = UnitStore()
        units = store.get_all_units("s1")
        assert units == []


class TestStepStore:
    """StepStore 測試."""

    @pytest.fixture
    def mock_storage_dir(self, tmp_path):
        with unittest.mock.patch("core.storage._STORAGE_DIR", tmp_path):
            yield tmp_path

    @pytest.fixture
    def mock_flush(self, mock_storage_dir):
        with unittest.mock.patch.object(
            StepStore, "_flush_session", return_value=None
        ):
            yield

    def test_save_and_get_step(self, mock_flush):
        """等價類：儲存後取得相同 StepResult."""
        from core.storage import StepStore
        store = StepStore()
        result = StepResult(step_id="s1", status=UnitStatus.SUCCESS, output={"data": "ok"})
        store.save_step("s1", "u1", "s1", result)
        fetched = store.get_step("s1", "s1")
        assert fetched is not None
        assert fetched.step_id == "s1"

    def test_get_steps_by_unit(self, mock_flush):
        """等價類：取得同一 unit 的所有 steps."""
        from core.storage import StepStore
        store = StepStore()
        store.save_step("s1", "u1", "s1", StepResult(step_id="s1", status=UnitStatus.SUCCESS))
        store.save_step("s1", "u1", "s2", StepResult(step_id="s2", status=UnitStatus.FAILED))
        steps = store.get_steps_by_unit("s1", "u1")
        assert len(steps) == 2

    def test_clear_unit_steps(self, mock_flush):
        """等價類：清空指定 unit 的 steps."""
        from core.storage import StepStore
        store = StepStore()
        store.save_step("s1", "u1", "s1", StepResult(step_id="s1", status=UnitStatus.SUCCESS))
        store.clear_unit_steps("s1", "u1")
        steps = store.get_steps_by_unit("s1", "u1")
        assert steps == []

    def test_session_isolation(self, mock_flush):
        """等價類：不同 session 資料隔離."""
        from core.storage import StepStore
        store = StepStore()
        store.save_step("s1", "u1", "s1", StepResult(step_id="s1", status=UnitStatus.SUCCESS))
        fetched = store.get_step("s2", "s1")
        assert fetched is None

    def test_flush_writes_file(self, mock_storage_dir):
        """等價類：flush 寫入檔案."""
        from core.storage import StepStore
        store = StepStore()
        store.save_step("s1", "u1", "s1", StepResult(step_id="s1", status=UnitStatus.SUCCESS))
        file_path = mock_storage_dir / "steps_s1.json"
        assert file_path.exists()
        content = file_path.read_text()
        data = json.loads(content)
        assert "s1" in data

    def test_empty_store(self, mock_flush):
        """邊界：空 store → get_steps_by_unit 回 []."""
        from core.storage import StepStore
        store = StepStore()
        steps = store.get_steps_by_unit("s1", "u1")
        assert steps == []