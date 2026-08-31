from unittest.mock import patch, MagicMock

import pytest

from ai_launchpad.multiplexers import (
    BaseMultiplexer,
    CmuxMultiplexer,
    MULTIPLEXER_REGISTRY,
    TmuxMultiplexer,
    _parse_workspace_ref,
    resolve_multiplexer,
)


class TestTmuxMultiplexer:
    @patch("ai_launchpad.multiplexers.time.sleep")
    @patch("ai_launchpad.multiplexers.subprocess.run")
    def test_sends_enter_to_accept_trust_prompt(self, mock_run, mock_sleep):
        TmuxMultiplexer().start_session("fix-bug-claude", "/dir", "claude 'p'")
        mock_sleep.assert_called_once_with(2)
        send_keys_call = mock_run.call_args_list[1].args[0]
        assert send_keys_call == ["tmux", "send-keys", "-t", "fix-bug-claude", "Enter"]


class TestCmuxMultiplexer:
    @patch("ai_launchpad.multiplexers.time.sleep")
    @patch("ai_launchpad.multiplexers.subprocess.run")
    def test_creates_unfocused_workspace(self, mock_run, _mock_sleep):
        mock_run.return_value = MagicMock(stdout="OK workspace:12\n")
        CmuxMultiplexer().start_session("fix-bug-claude", "/dir", "claude 'p'")
        cmd = mock_run.call_args_list[0].args[0]
        assert cmd[:2] == ["cmux", "new-workspace"]
        assert cmd[cmd.index("--name") + 1] == "fix-bug-claude"
        assert cmd[cmd.index("--cwd") + 1] == "/dir"
        assert cmd[cmd.index("--command") + 1] == "claude 'p'"
        assert cmd[cmd.index("--focus") + 1] == "false"

    @patch("ai_launchpad.multiplexers.time.sleep")
    @patch("ai_launchpad.multiplexers.subprocess.run")
    def test_sends_enter_to_new_workspace(self, mock_run, mock_sleep):
        mock_run.return_value = MagicMock(stdout="OK workspace:12\n")
        CmuxMultiplexer().start_session("fix-bug-claude", "/dir", "claude 'p'")
        mock_sleep.assert_called_once_with(2)
        assert mock_run.call_args_list[1].args[0] == [
            "cmux",
            "send-key",
            "--workspace",
            "workspace:12",
            "Enter",
        ]

    @patch("ai_launchpad.multiplexers.time.sleep")
    @patch("ai_launchpad.multiplexers.subprocess.run")
    def test_skips_enter_when_workspace_ref_is_missing(self, mock_run, mock_sleep):
        mock_run.return_value = MagicMock(stdout="OK\n")
        CmuxMultiplexer().start_session("fix-bug-claude", "/dir", "claude 'p'")
        mock_sleep.assert_not_called()
        assert mock_run.call_count == 1


class TestParseWorkspaceRef:
    def test_parses_ref(self):
        assert _parse_workspace_ref("OK workspace:54\n") == "workspace:54"

    def test_returns_empty_when_absent(self):
        assert _parse_workspace_ref("OK\n") == ""


class TestResolveMultiplexer:
    @patch("ai_launchpad.multiplexers.read_config", return_value={})
    def test_cli_multiplexer_takes_precedence(self, _mock_config):
        assert isinstance(resolve_multiplexer("cmux"), CmuxMultiplexer)

    @patch(
        "ai_launchpad.multiplexers.read_config", return_value={"multiplexer": "cmux"}
    )
    def test_falls_back_to_config(self, _mock_config):
        assert isinstance(resolve_multiplexer(None), CmuxMultiplexer)

    @patch("ai_launchpad.multiplexers.read_config", return_value={})
    def test_defaults_to_tmux(self, _mock_config):
        assert isinstance(resolve_multiplexer(None), TmuxMultiplexer)

    @patch("ai_launchpad.multiplexers.read_config", return_value={})
    def test_unknown_multiplexer_raises(self, _mock_config):
        with pytest.raises(ValueError, match="Unknown multiplexer"):
            resolve_multiplexer("screen")


class TestBaseMultiplexer:
    def test_start_session_is_abstract(self):
        with pytest.raises(NotImplementedError):
            BaseMultiplexer().start_session("session", "/dir", "cmd")

    def test_cleanup_script_body_is_abstract(self):
        with pytest.raises(NotImplementedError):
            BaseMultiplexer().cleanup_script_body()


class TestMultiplexerRegistry:
    def test_registry_contains_tmux(self):
        assert MULTIPLEXER_REGISTRY["tmux"] is TmuxMultiplexer

    def test_registry_contains_cmux(self):
        assert MULTIPLEXER_REGISTRY["cmux"] is CmuxMultiplexer

    def test_error_lists_available_multiplexers(self):
        with pytest.raises(ValueError, match="cmux, tmux"):
            resolve_multiplexer("screen")
