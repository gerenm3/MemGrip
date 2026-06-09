"""L1 test for HealthState (module 23) - core/health.py.

Black-box testing: only read docs/test_plan_l1/23_health_state.md and api_signatures.md.
No source code reading of core/health.py.
"""

import pytest
from unittest.mock import patch, MagicMock
import json


class TestLogActionOKNoUserMessage:
    """TC-23-01: log_action - OK status, no user_message."""

    def test_TC23_01_log_action_ok_no_user_message(self):
        from core.health import log_action, set_session_id

        set_session_id("s1")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "init", "OK", "ok", "")

        mock_file.write.assert_called()
        written = mock_file.write.call_args[0][0]
        data = json.loads(written)
        assert data["status"] == "OK"


class TestLogActionDegradedWithUserMessage:
    """TC-23-02: log_action - DEGRADED status with user_message."""

    def test_TC23_02_log_action_degraded_with_user_message(self):
        from core.health import log_action, get_user_warnings, set_session_id

        set_session_id("s1")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "fail", "DEGRADED", "degraded", "warning msg")

        mock_file.write.assert_called()
        written = mock_file.write.call_args[0][0]
        data = json.loads(written)
        assert data["status"] == "DEGRADED"

        # Verify warning was added via get_user_warnings
        warnings = get_user_warnings("s1")
        assert "warning msg" in warnings


class TestLogActionFailedWithUserMessage:
    """TC-23-03: log_action - FAILED status with user_message."""

    def test_TC23_03_log_action_failed_with_user_message(self):
        from core.health import log_action, get_user_warnings, set_session_id

        set_session_id("s2")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "fail", "FAILED", "failed", "error msg")

        mock_file.write.assert_called()
        written = mock_file.write.call_args[0][0]
        data = json.loads(written)
        assert data["status"] == "FAILED"

        warnings = get_user_warnings("s2")
        assert "error msg" in warnings


class TestLogActionDegradedNoUserMessage:
    """TC-23-04: log_action - DEGRADED status, no user_message (BVA)."""

    def test_TC23_04_log_action_degraded_no_user_message(self):
        from core.health import log_action, get_user_warnings, set_session_id

        set_session_id("s3")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "fail", "DEGRADED", "degraded", "")

        mock_file.write.assert_called()

        # Empty user_message should NOT add to pending_warnings
        warnings = get_user_warnings("s3")
        assert "degraded" not in warnings


class TestLogActionFailedNoUserMessage:
    """TC-23-05: log_action - FAILED status, no user_message (BVA)."""

    def test_TC23_05_log_action_failed_no_user_message(self):
        from core.health import log_action, get_user_warnings, set_session_id

        set_session_id("s4")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "fail", "FAILED", "failed", "")

        mock_file.write.assert_called()

        warnings = get_user_warnings("s4")
        assert "failed" not in warnings


class TestLogActionDebugModeTrue:
    """TC-23-06: log_action - DEBUG_MODE is True."""

    def test_TC23_06_log_action_debug_mode_true(self, monkeypatch):
        from core import health
        import config

        monkeypatch.setattr(config, 'DEBUG_MODE', True)

        # Re-import to pick up the patched config
        import importlib
        importlib.reload(health)

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            with patch('builtins.print') as mock_print:
                health.log_action("test", "init", "OK", "ok", "")
                mock_print.assert_called()


class TestLogActionDebugModeFalse:
    """TC-23-07: log_action - DEBUG_MODE is False."""

    def test_TC23_07_log_action_debug_mode_false(self, monkeypatch):
        from core import health
        import config

        monkeypatch.setattr(config, 'DEBUG_MODE', False)

        import importlib
        importlib.reload(health)

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            with patch('builtins.print') as mock_print:
                health.log_action("test", "init", "OK", "ok", "")
                mock_print.assert_not_called()


class TestGetUserWarningsWithWarnings:
    """TC-23-08: get_user_warnings - has warnings.

    Black-box adjustment: use log_action to create warnings, then verify via get_user_warnings.
    """

    def test_TC23_08_get_user_warnings_with_warnings(self):
        from core.health import log_action, get_user_warnings, set_session_id

        set_session_id("s5")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "fail", "DEGRADED", "d", "w1")
            log_action("test", "fail", "FAILED", "f", "w2")

        warnings = get_user_warnings("s5")
        assert "w1" in warnings
        assert "w2" in warnings
        # After getting, warnings should be cleared for this session
        warnings2 = get_user_warnings("s5")
        assert "w1" not in warnings2
        assert "w2" not in warnings2


class TestGetUserWarningsNoWarnings:
    """TC-23-09: get_user_warnings - no warnings."""

    def test_TC23_09_get_user_warnings_no_warnings(self):
        from core.health import get_user_warnings

        warnings = get_user_warnings("s1")
        assert warnings == []


class TestGetUserWarningsSessionIsolation:
    """TC-23-10: get_user_warnings - session isolation.

    Black-box adjustment: use log_action to create warnings for different sessions.
    """

    def test_TC23_10_get_user_warnings_session_isolation(self):
        from core.health import log_action, get_user_warnings, set_session_id

        set_session_id("s1")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "fail", "DEGRADED", "d", "w1")
            set_session_id("s2")
            log_action("test", "fail", "FAILED", "f", "w2")

        warnings_s1 = get_user_warnings("s1")
        warnings_s2 = get_user_warnings("s2")

        assert "w1" in warnings_s1
        assert "w2" in warnings_s2


class TestGetUserWarningsNonExistentSession:
    """TC-23-11: get_user_warnings - non-existent session (BVA)."""

    def test_TC23_11_get_user_warnings_non_existent_session(self):
        from core.health import get_user_warnings

        warnings = get_user_warnings("s2")
        assert warnings == []


class TestSetSessionId:
    """TC-23-12: set_session_id - set session.

    Black-box adjustment: verify via log_action + get_user_warnings
    rather than directly checking _current_session_id.
    """

    def test_TC23_12_set_session_id(self):
        from core.health import set_session_id, log_action, get_user_warnings

        set_session_id("s1")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "fail", "DEGRADED", "d", "w1")

        warnings = get_user_warnings("s1")
        assert "w1" in warnings
        assert get_user_warnings("s2") == []


class TestLogActionOKWithUserMessage:
    """TC-23-13: log_action - user_message non-empty but status OK (BVA)."""

    def test_TC23_13_log_action_ok_with_user_message(self):
        from core.health import log_action, get_user_warnings, set_session_id

        set_session_id("s6")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "init", "OK", "ok", "msg")

        warnings = get_user_warnings("s6")
        assert "msg" not in warnings


class TestLogActionUserMessageNone:
    """TC-23-14: log_action - user_message is None (BVA)."""

    def test_TC23_14_log_action_user_message_none(self):
        from core.health import log_action, get_user_warnings, set_session_id

        set_session_id("s7")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "fail", "DEGRADED", "degraded", None)

        warnings = get_user_warnings("s7")
        assert "degraded" not in warnings


class TestLogActionUserMessageEmptyString:
    """TC-23-15: log_action - user_message is empty string (BVA)."""

    def test_TC23_15_log_action_user_message_empty_string(self):
        from core.health import log_action, get_user_warnings, set_session_id

        set_session_id("s8")

        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', return_value=mock_file):
            log_action("test", "fail", "DEGRADED", "degraded", "")

        warnings = get_user_warnings("s8")
        assert "degraded" not in warnings