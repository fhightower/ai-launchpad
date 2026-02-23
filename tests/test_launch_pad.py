import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

from data_models import WorkItem
from launch_pad import (
    _confirm_work_items,
    _get_work_items,
    _create_home_base,
    _copy_relevant_source,
    _copy_relevant_sources,
    _start_agent_in_context,
    _create_context,
    launch,
)


def _make_work_item(**overrides) -> WorkItem:
    defaults = dict(
        title="Fix bug",
        description="desc",
        link="https://example.com",
        relevant_source_directories=["repo-a"],
    )
    defaults.update(overrides)
    return WorkItem(**defaults)


# ---------------------------------------------------------------------------
# _confirm_work_items
# ---------------------------------------------------------------------------
class TestConfirmWorkItems:
    def test_confirm_all(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        items = [_make_work_item(title="A"), _make_work_item(title="B")]
        assert len(_confirm_work_items(items)) == 2

    def test_reject_all(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "n")
        items = [_make_work_item()]
        assert _confirm_work_items(items) == []

    def test_empty_input_rejects(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        assert _confirm_work_items([_make_work_item()]) == []


# ---------------------------------------------------------------------------
# _get_work_items
# ---------------------------------------------------------------------------
class TestGetWorkItems:
    def test_aggregates_from_sources(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        source1 = MagicMock()
        source1.get_work_items.return_value = [_make_work_item(title="A")]
        source2 = MagicMock()
        source2.get_work_items.return_value = [_make_work_item(title="B")]
        items = _get_work_items([source1, source2])
        assert len(items) == 2


# ---------------------------------------------------------------------------
# _create_home_base
# ---------------------------------------------------------------------------
class TestCreateHomeBase:
    @patch("launch_pad.read_config", return_value={"base_contexts_dir": ""})
    def test_creates_directory(self, _mock_config, tmp_path):
        with patch(
            "launch_pad.read_config",
            return_value={"base_contexts_dir": str(tmp_path)},
        ):
            home = _create_home_base("my-task")
        assert home.exists()
        assert home.name == "my-task"

    @patch("launch_pad.read_config")
    def test_idempotent(self, mock_config, tmp_path):
        mock_config.return_value = {"base_contexts_dir": str(tmp_path)}
        _create_home_base("task")
        _create_home_base("task")  # should not raise


# ---------------------------------------------------------------------------
# _copy_relevant_source
# ---------------------------------------------------------------------------
class TestCopyRelevantSource:
    @patch("launch_pad.read_config")
    def test_source_not_found_raises(self, mock_config, tmp_path):
        mock_config.return_value = {"base_source_dir": str(tmp_path)}
        with pytest.raises(ValueError, match="does not exist"):
            _copy_relevant_source("nonexistent", "branch", tmp_path / "dest")

    @patch("launch_pad.read_config")
    def test_destination_exists_raises(self, mock_config, tmp_path):
        source_dir = tmp_path / "source" / "repo"
        source_dir.mkdir(parents=True)
        dest = tmp_path / "dest"
        dest.mkdir()
        # destination_path = dest / repo name
        (dest / "repo").mkdir()
        mock_config.return_value = {"base_source_dir": str(tmp_path / "source")}
        with pytest.raises(ValueError, match="already exists"):
            _copy_relevant_source("repo", "branch", dest)


# ---------------------------------------------------------------------------
# _copy_relevant_sources
# ---------------------------------------------------------------------------
class TestCopyRelevantSources:
    @patch("launch_pad.read_config", return_value={"base_source_dir": "/nonexistent"})
    def test_handles_errors_gracefully(self, _mock_config, tmp_path, capsys):
        item = _make_work_item(relevant_source_directories=["bad-repo"])
        _copy_relevant_sources(item, tmp_path)
        captured = capsys.readouterr()
        assert "Warning" in captured.out


# ---------------------------------------------------------------------------
# _start_agent_in_context
# ---------------------------------------------------------------------------
class TestStartAgentInContext:
    def test_empty_command_raises(self, tmp_path):
        with pytest.raises(ValueError, match="empty"):
            _start_agent_in_context(tmp_path, "", "prompt")

    @patch("launch_pad.subprocess.run")
    @patch("launch_pad.time.sleep")
    def test_writes_prompt_and_starts_tmux(self, _sleep, mock_run, tmp_path):
        _start_agent_in_context(tmp_path, "claude", "my prompt")
        prompt_file = tmp_path / "agent_prompt_claude.txt"
        assert prompt_file.read_text() == "my prompt"
        # First call should be tmux new-session
        first_call = mock_run.call_args_list[0]
        assert "tmux" in first_call.args[0]
        assert "new-session" in first_call.args[0]


# ---------------------------------------------------------------------------
# _create_context
# ---------------------------------------------------------------------------
class TestCreateContext:
    @patch("launch_pad._write_cleanup_script")
    @patch("launch_pad._copy_relevant_sources")
    @patch("launch_pad._create_home_base")
    def test_orchestration(self, mock_home, mock_copy, mock_cleanup, tmp_path):
        mock_home.return_value = tmp_path / "ctx"
        (tmp_path / "ctx").mkdir()
        item = _make_work_item()
        result = _create_context(item)
        mock_home.assert_called_once()
        mock_copy.assert_called_once_with(item, tmp_path / "ctx")
        mock_cleanup.assert_called_once()
        assert result == tmp_path / "ctx"


# ---------------------------------------------------------------------------
# launch
# ---------------------------------------------------------------------------
class TestLaunch:
    @patch("agents.read_config", return_value={})
    @patch("launch_pad._start_agent_in_context")
    @patch("launch_pad._create_context")
    @patch("launch_pad._get_work_items")
    def test_launch_processes_items(
        self, mock_get, mock_ctx, mock_start, _mock_read_config, tmp_path
    ):
        item = _make_work_item()
        mock_get.return_value = [item]
        mock_ctx.return_value = tmp_path
        launch([])
        mock_ctx.assert_called_once_with(item)
        assert mock_start.called
