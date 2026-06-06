"""測試 _enforce_trace_size 的獨立行為。"""

import json
import os
import pathlib
import tempfile
from unittest.mock import patch

import pytest

from skills import lvs


class TestEnforceTraceSize:
    """測試 trace.jsonl 大小裁切邏輯。"""

    def test_no_file_returns_early(self):
        """檔案不存在時直接回傳。"""
        fake_path = pathlib.Path("/tmp/nonexistent_lvs_trace_test_12345.jsonl")
        with patch.object(lvs, "TRACE_LOG_PATH", fake_path):
            # 不應拋出異常
            lvs._enforce_trace_size()

    def test_file_under_limit_no_change(self):
        """檔案小於上限時不應修改。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "trace.jsonl")
            # 寫 10 行小檔案
            with open(test_file, "w") as f:
                for i in range(10):
                    f.write(json.dumps({"i": i}) + "\n")
            orig_size = os.path.getsize(test_file)

            test_path = pathlib.Path(test_file)
            with patch.object(lvs, "TRACE_LOG_PATH", test_path):
                lvs._enforce_trace_size()

            final_size = os.path.getsize(test_file)
            assert final_size == orig_size

    def test_file_over_limit_cuts_to_keep_lines(self):
        """檔案超過上限時裁切為 TRACE_KEEP_LINES 行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "trace.jsonl")

            # 用較小值測試：設 MAX_TRACE_SIZE 為 1000 bytes
            small_limit = 1000
            n_lines = 50

            # 寫足夠多的行（每行約 40 bytes，寫 200 行 ≈ 8000 bytes > 1000）
            with open(test_file, "w") as f:
                for i in range(200):
                    f.write(json.dumps({"i": i, "s": "x" * 25}) + "\n")

            orig_size = os.path.getsize(test_file)
            assert orig_size > small_limit

            test_path = pathlib.Path(test_file)
            with patch.object(lvs, "TRACE_LOG_PATH", test_path):
                with patch.object(lvs, "MAX_TRACE_SIZE", small_limit):
                    with patch.object(lvs, "TRACE_KEEP_LINES", n_lines):
                        lvs._enforce_trace_size()

            final_size = os.path.getsize(test_file)
            # 裁切後行數 = TRACE_KEEP_LINES
            # 注意：當 KEEP_LINES 行本身的大小 > MAX_TRACE_SIZE 時，
            # 最終大小仍會超過上限，這是合理的（我們已用最小行數保留）

            # 驗證行數
            with open(test_file) as f:
                lines = f.readlines()
            assert len(lines) == n_lines

            # 驗證是「最後 N 行」
            for idx, line in enumerate(lines):
                data = json.loads(line)
                # 原始寫了 200 行 (0-199)，保留最後 50 行
                # 即 150-199
                assert data["i"] == 150 + idx

    def test_file_over_limit_but_fewer_lines(self):
        """超過大小但行數少於 KEEP_LINES 時保留所有行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "trace.jsonl")
            # 寫少量大行
            with open(test_file, "w") as f:
                f.write(json.dumps({"data": "x" * 500}) + "\n")
                f.write(json.dumps({"data": "y" * 500}) + "\n")
                f.write(json.dumps({"data": "z" * 500}) + "\n")

            orig_size = os.path.getsize(test_file)

            test_path = pathlib.Path(test_file)
            # 設上限為 500 bytes（檔案 > 1500 bytes，超過）
            # 設 KEEP_LINES = 100（大於實際行數 3）
            with patch.object(lvs, "TRACE_LOG_PATH", test_path):
                with patch.object(lvs, "MAX_TRACE_SIZE", 500):
                    with patch.object(lvs, "TRACE_KEEP_LINES", 100):
                        lvs._enforce_trace_size()

            final_size = os.path.getsize(test_file)
            # 行數 < KEEP_LINES，不裁切
            assert final_size == orig_size

    def test_enforce_preserves_recent_session_data(self):
        """裁切後最新的 session_id 資料仍存在。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "trace.jsonl")
            old_session = "old_session_001"
            new_session = "new_session_002"

            # 寫 100 行舊資料 + 10 行新資料
            with open(test_file, "w") as f:
                for i in range(100):
                    f.write(json.dumps({"session_id": old_session, "i": i}) + "\n")
                for i in range(10):
                    f.write(json.dumps({"session_id": new_session, "i": i}) + "\n")

            # 設定 SMALL 上限讓檔案超過
            test_path = pathlib.Path(test_file)
            with patch.object(lvs, "TRACE_LOG_PATH", test_path):
                with patch.object(lvs, "MAX_TRACE_SIZE", 100):
                    with patch.object(lvs, "TRACE_KEEP_LINES", 50):
                        lvs._enforce_trace_size()

            # 讀取裁切後檔案，確認有 new_session
            with open(test_file) as f:
                for line in f:
                    data = json.loads(line)
                    if data["session_id"] == new_session:
                        break
                else:
                    pytest.fail("裁切後遺失了新 session_id 的資料")