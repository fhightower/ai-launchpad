import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from agents import ClaudeAgent
from data_models import WorkItem
from launch import (
    _confirm_work_items,
    _get_work_items,
    _create_home_base,
    _copy_relevant_source,
    _copy_relevant_sources,
    _write_cleanup_script,
    _start_agent_in_context,
    _create_context,
    _resolve_agent,
    lift_off,
    start_launch_sequence,
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
    @patch("launch.read_config", return_value={"base_worktrees_dir": ""})
    def test_creates_directory(self, _mock_config, tmp_path):
        with patch(
            "launch.read_config",
            return_value={"base_worktrees_dir": str(tmp_path)},
        ):
            home = _create_home_base("my-task")
        assert home.exists()
        assert home.name == "my-task"

    @patch("launch.read_config")
    def test_idempotent(self, mock_config, tmp_path):
        mock_config.return_value = {"base_worktrees_dir": str(tmp_path)}
        _create_home_base("task")
        _create_home_base("task")  # should not raise


# ---------------------------------------------------------------------------
# _copy_relevant_source
# ---------------------------------------------------------------------------
class TestCopyRelevantSource:
    @patch("launch.read_config")
    def test_source_not_found_raises(self, mock_config, tmp_path):
        mock_config.return_value = {"base_source_dir": str(tmp_path)}
        with pytest.raises(ValueError, match="does not exist"):
            _copy_relevant_source("nonexistent", "branch", tmp_path / "dest")

    @patch("launch.read_config")
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
    @patch("launch.read_config", return_value={"base_source_dir": "/nonexistent"})
    def test_handles_errors_gracefully(self, _mock_config, tmp_path, capsys):
        item = _make_work_item(relevant_source_directories=["bad-repo"])
        _copy_relevant_sources(item, tmp_path)
        captured = capsys.readouterr()
        assert "Warning" in captured.out


# ---------------------------------------------------------------------------
# _write_cleanup_script
# ---------------------------------------------------------------------------
class TestWriteCleanupScript:
    @patch("launch.read_config", return_value={"base_source_dir": "/src", "base_worktrees_dir": "/contexts"})
    def test_creates_cleanup_script(self, _mock_config, tmp_path):
        home_base = tmp_path / "my-task"
        home_base.mkdir()
        item = _make_work_item(relevant_source_directories=["repo-a"])
        agent = ClaudeAgent()
        _write_cleanup_script(home_base, item, agent)
        cleanup = home_base / "cleanup.sh"
        assert cleanup.exists()
        content = cleanup.read_text()
        assert "my-task" in content
        assert "my-task-claude" in content
        assert "/src/repo-a" in content

    @patch("launch.read_config", return_value={"base_source_dir": "/src", "base_worktrees_dir": "/contexts"})
    def test_cleanup_script_is_executable(self, _mock_config, tmp_path):
        home_base = tmp_path / "task"
        home_base.mkdir()
        item = _make_work_item()
        agent = ClaudeAgent()
        _write_cleanup_script(home_base, item, agent)
        cleanup = home_base / "cleanup.sh"
        assert cleanup.stat().st_mode & 0o755

    @patch("launch.read_config", return_value={"base_source_dir": "/src", "base_worktrees_dir": "/contexts"})
    def test_absolute_source_dir(self, _mock_config, tmp_path):
        home_base = tmp_path / "task"
        home_base.mkdir()
        item = _make_work_item(relevant_source_directories=["/absolute/repo"])
        agent = ClaudeAgent()
        _write_cleanup_script(home_base, item, agent)
        content = (home_base / "cleanup.sh").read_text()
        assert "/absolute/repo" in content


# ---------------------------------------------------------------------------
# _copy_relevant_source
# ---------------------------------------------------------------------------
class TestCopyRelevantSourceSubprocess:
    @patch("launch.subprocess.run")
    @patch("launch.read_config", return_value={"base_source_dir": ""})
    def test_calls_git_worktree_new_branch(self, _mock_config, mock_run, tmp_path):
        source = tmp_path / "repo"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        # Simulate branch not existing (returncode=1)
        mock_run.return_value = MagicMock(returncode=1)
        _copy_relevant_source(str(source), "new-branch", dest)
        # First call: git show-ref, second call: git worktree add -b
        worktree_call = mock_run.call_args_list[1]
        assert "worktree" in worktree_call.args[0]
        assert "-b" in worktree_call.args[0]

    @patch("launch.subprocess.run")
    @patch("launch.read_config", return_value={"base_source_dir": ""})
    def test_calls_git_worktree_existing_branch(self, _mock_config, mock_run, tmp_path):
        source = tmp_path / "repo"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        # Simulate branch exists (returncode=0)
        mock_run.return_value = MagicMock(returncode=0)
        _copy_relevant_source(str(source), "existing-branch", dest)
        worktree_call = mock_run.call_args_list[1]
        assert "worktree" in worktree_call.args[0]
        assert "-b" not in worktree_call.args[0]

    @patch("builtins.input")
    @patch("launch.subprocess.run")
    @patch(
        "launch.read_config",
        return_value={
            "base_source_dir": "",
            "expected_source_repo_branch": "development",
        },
    )
    def test_expected_branch_no_prompt_when_already_on_branch(
        self, _mock_config, mock_run, mock_input, tmp_path
    ):
        source = tmp_path / "repo"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()

        mock_run.side_effect = [
            MagicMock(stdout="development\n"),
            MagicMock(returncode=1),
            MagicMock(returncode=0),
        ]

        _copy_relevant_source(str(source), "new-branch", dest)

        mock_input.assert_not_called()
        assert "rev-parse" in mock_run.call_args_list[0].args[0]
        worktree_call = mock_run.call_args_list[2]
        assert "worktree" in worktree_call.args[0]
        assert "-b" in worktree_call.args[0]

    @patch("builtins.input", return_value="")
    @patch("launch.subprocess.run")
    @patch(
        "launch.read_config",
        return_value={
            "base_source_dir": "",
            "expected_source_repo_branch": "development",
        },
    )
    def test_expected_branch_mismatch_prompts_and_rechecks(
        self, _mock_config, mock_run, mock_input, tmp_path
    ):
        source = tmp_path / "repo"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()

        mock_run.side_effect = [
            MagicMock(stdout="main\n"),
            MagicMock(stdout="development\n"),
            MagicMock(returncode=1),
            MagicMock(returncode=0),
        ]

        _copy_relevant_source(str(source), "new-branch", dest)

        mock_input.assert_called_once()
        assert "rev-parse" in mock_run.call_args_list[0].args[0]
        assert "rev-parse" in mock_run.call_args_list[1].args[0]
        worktree_call = mock_run.call_args_list[3]
        assert "worktree" in worktree_call.args[0]


# ---------------------------------------------------------------------------
# _start_agent_in_context
# ---------------------------------------------------------------------------
class TestStartAgentInContext:
    def test_empty_command_raises(self, tmp_path):
        with pytest.raises(ValueError, match="empty"):
            _start_agent_in_context(tmp_path, "", "prompt")

    @patch("launch.subprocess.run")
    def test_passes_prompt_to_agent_command(self, mock_run, tmp_path):
        _start_agent_in_context(tmp_path, "claude", "my prompt")
        first_call = mock_run.call_args_list[0].args[0]
        assert "tmux" in first_call
        assert "new-session" in first_call
        assert first_call[-1] == "claude 'my prompt'"


# ---------------------------------------------------------------------------
# _resolve_agent
# ---------------------------------------------------------------------------
class TestResolveAgent:
    @patch("launch.read_config", return_value={})
    def test_cli_agent_takes_precedence(self, _mock_config):
        agent = _resolve_agent("claude")
        assert isinstance(agent, ClaudeAgent)

    @patch("launch.read_config", return_value={"default_agent": "claude"})
    def test_config_agent_used_when_no_cli(self, _mock_config):
        agent = _resolve_agent(None)
        assert isinstance(agent, ClaudeAgent)

    @patch("launch.read_config", return_value={})
    def test_raises_when_no_agent_specified(self, _mock_config):
        with pytest.raises(ValueError, match="No agent specified"):
            _resolve_agent(None)

    def test_unknown_agent_raises(self):
        with pytest.raises(ValueError, match="Unknown agent"):
            _resolve_agent("nonexistent")


# ---------------------------------------------------------------------------
# _create_context
# ---------------------------------------------------------------------------
class TestCreateContext:
    @patch("launch._write_cleanup_script")
    @patch("launch._copy_relevant_sources")
    @patch("launch._create_home_base")
    def test_orchestration(self, mock_home, mock_copy, mock_cleanup, tmp_path):
        mock_home.return_value = tmp_path / "ctx"
        (tmp_path / "ctx").mkdir()
        item = _make_work_item()
        agent = ClaudeAgent()
        result = _create_context(item, agent)
        mock_home.assert_called_once()
        mock_copy.assert_called_once_with(item, tmp_path / "ctx")
        mock_cleanup.assert_called_once_with(tmp_path / "ctx", item, agent)
        assert result == tmp_path / "ctx"


# ---------------------------------------------------------------------------
# launch
# ---------------------------------------------------------------------------
class TestLaunch:
    @patch("agents.read_config", return_value={})
    @patch("launch._start_agent_in_context")
    @patch("launch._create_context")
    @patch("launch._get_work_items")
    def test_launch_processes_items(
        self, mock_get, mock_ctx, mock_start, _mock_read_config, tmp_path
    ):
        item = _make_work_item()
        mock_get.return_value = [item]
        mock_ctx.return_value = tmp_path
        agent = ClaudeAgent()
        lift_off([], agent)
        mock_ctx.assert_called_once_with(item, agent)
        assert mock_start.called


# ---------------------------------------------------------------------------
# start_launch_sequence
# ---------------------------------------------------------------------------
class TestStartLaunchSequence:
    @patch("launch.lift_off")
    @patch("launch._resolve_agent")
    def test_parses_agent_arg(self, mock_resolve, mock_lift_off):
        agent = ClaudeAgent()
        mock_resolve.return_value = agent
        start_launch_sequence(["--agent", "claude"])
        mock_resolve.assert_called_once_with("claude")
        mock_lift_off.assert_called_once_with([], agent)

    @patch("launch.lift_off")
    @patch("launch._resolve_agent")
    def test_default_agent_is_none(self, mock_resolve, mock_lift_off):
        agent = ClaudeAgent()
        mock_resolve.return_value = agent
        start_launch_sequence([])
        mock_resolve.assert_called_once_with(None)

    @patch("launch.lift_off")
    @patch("launch._resolve_agent")
    def test_passes_sources_from_args(self, mock_resolve, mock_lift_off, tmp_path):
        todo = tmp_path / "todo.txt"
        todo.write_text("- Task one\n")
        agent = ClaudeAgent()
        mock_resolve.return_value = agent
        start_launch_sequence(["--todo-file", str(todo), "--agent", "claude"])
        mock_resolve.assert_called_once_with("claude")
        _, kwargs = mock_lift_off.call_args
        # sources are positional
        sources = mock_lift_off.call_args.args[0]
        assert len(sources) == 1
