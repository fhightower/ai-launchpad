from unittest.mock import patch, MagicMock

import pytest

from ai_launchpad.agents import ClaudeAgent, CodexAgent, resolve_agent
from ai_launchpad.work_items import (
    WorkItem,
    get_work_items,
    _confirm_work_items,
    _copy_relevant_source,
    _normalize_source_dir,
    copy_relevant_sources,
)
from ai_launchpad.work_trees import (
    _create_home_base,
    _write_cleanup_script,
    _write_task_file,
    setup_worktree,
)
from ai_launchpad.launch import start_launch_sequence


def _make_work_item(**overrides: object) -> WorkItem:
    defaults: dict[str, object] = dict(
        title="Fix bug",
        description="desc",
        link="https://example.com",
        relevant_source_directories=["repo-a"],
    )
    defaults.update(overrides)
    return WorkItem(**defaults)  # type: ignore[typeddict-item]


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

    def test_prompts_for_missing_source_dirs(self, monkeypatch):
        answers = iter(["y", "repo-x"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        item = _make_work_item(relevant_source_directories=[])
        confirmed = _confirm_work_items([item])
        assert len(confirmed) == 1
        assert confirmed[0]["relevant_source_directories"] == ["repo-x"]

    def test_missing_source_dirs_can_be_skipped(self, monkeypatch):
        answers = iter(["y", ""])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        item = _make_work_item(relevant_source_directories=[])
        confirmed = _confirm_work_items([item])
        assert len(confirmed) == 1
        assert confirmed[0]["relevant_source_directories"] == []

    def test_no_source_dir_prompt_when_not_queued(self, monkeypatch):
        answers = iter(["n"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        item = _make_work_item(relevant_source_directories=[])
        confirmed = _confirm_work_items([item])
        assert confirmed == []


# ---------------------------------------------------------------------------
# get_work_items
# ---------------------------------------------------------------------------
class TestGetWorkItems:
    def test_aggregates_from_sources(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "y")
        source1 = MagicMock()
        source1.get_work_items.return_value = [_make_work_item(title="A")]
        source2 = MagicMock()
        source2.get_work_items.return_value = [_make_work_item(title="B")]
        items = get_work_items([source1, source2])
        assert len(items) == 2


# ---------------------------------------------------------------------------
# _create_home_base
# ---------------------------------------------------------------------------
class TestCreateHomeBase:
    @patch(
        "ai_launchpad.work_trees.read_config", return_value={"base_worktrees_dir": ""}
    )
    def test_creates_directory(self, _mock_config, tmp_path):
        with patch(
            "ai_launchpad.work_trees.read_config",
            return_value={"base_worktrees_dir": str(tmp_path)},
        ):
            home = _create_home_base("my-task")
        assert home.exists()
        assert home.name == "my-task"

    @patch("ai_launchpad.work_trees.read_config")
    def test_idempotent(self, mock_config, tmp_path):
        mock_config.return_value = {"base_worktrees_dir": str(tmp_path)}
        _create_home_base("task")
        _create_home_base("task")  # should not raise


# ---------------------------------------------------------------------------
# _copy_relevant_source
# ---------------------------------------------------------------------------
class TestCopyRelevantSource:
    @patch("ai_launchpad.work_items.read_config")
    def test_source_not_found_raises(self, mock_config, tmp_path):
        mock_config.return_value = {"base_source_dir": str(tmp_path)}
        with pytest.raises(ValueError, match="does not exist"):
            _copy_relevant_source("nonexistent", "branch", tmp_path / "dest")

    @patch("ai_launchpad.work_items.read_config")
    def test_destination_exists_raises(self, mock_config, tmp_path):
        source_dir = tmp_path / "source" / "repo"
        source_dir.mkdir(parents=True)
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "repo").mkdir()
        mock_config.return_value = {"base_source_dir": str(tmp_path / "source")}
        with pytest.raises(ValueError, match="already exists"):
            _copy_relevant_source("repo", "branch", dest)


# ---------------------------------------------------------------------------
# _normalize_source_dir
# ---------------------------------------------------------------------------
class TestNormalizeSourceDir:
    def test_lowercases(self):
        assert _normalize_source_dir("FooBar") == "foobar"

    def test_replaces_spaces_with_hyphens(self):
        assert _normalize_source_dir("Foo Bar") == "foo-bar"

    def test_handles_multiple_spaces(self):
        assert _normalize_source_dir("Foo Bar Baz") == "foo-bar-baz"

    def test_already_normalized__unchanged(self):
        assert _normalize_source_dir("foo-bar") == "foo-bar"

    def test_empty_string(self):
        assert _normalize_source_dir("") == ""


# ---------------------------------------------------------------------------
# copy_relevant_sources
# ---------------------------------------------------------------------------
class TestCopyRelevantSources:
    @patch(
        "ai_launchpad.work_items.read_config",
        return_value={"base_source_dir": "/nonexistent"},
    )
    def test_handles_errors_gracefully(self, _mock_config, tmp_path, capsys):
        item = _make_work_item(relevant_source_directories=["bad-repo"])
        copy_relevant_sources(item, tmp_path)
        captured = capsys.readouterr()
        assert "Warning" in captured.out

    @patch("ai_launchpad.work_items._copy_relevant_source")
    @patch(
        "ai_launchpad.work_items.read_config", return_value={"base_source_dir": "/src"}
    )
    def test_normalizes_source_dir_with_spaces(self, _mock_config, mock_copy, tmp_path):
        item = _make_work_item(relevant_source_directories=["Foo Bar"])
        copy_relevant_sources(item, tmp_path)
        passed_source_dir = mock_copy.call_args.args[0]
        assert passed_source_dir == "foo-bar"

    @patch("ai_launchpad.work_items._copy_relevant_source")
    @patch(
        "ai_launchpad.work_items.read_config", return_value={"base_source_dir": "/src"}
    )
    def test_absolute_source_dir_not_normalized(
        self, _mock_config, mock_copy, tmp_path
    ):
        item = _make_work_item(relevant_source_directories=["/Absolute/Repo Name"])
        copy_relevant_sources(item, tmp_path)
        passed_source_dir = mock_copy.call_args.args[0]
        assert passed_source_dir == "/Absolute/Repo Name"


# ---------------------------------------------------------------------------
# _write_cleanup_script
# ---------------------------------------------------------------------------
class TestWriteCleanupScript:
    @patch(
        "ai_launchpad.work_trees.read_config",
        return_value={"base_source_dir": "/src", "base_worktrees_dir": "/contexts"},
    )
    def test_creates_cleanup_script(self, _mock_config, tmp_path):
        home_base = tmp_path / "my-task-claude"
        home_base.mkdir()
        item = _make_work_item(relevant_source_directories=["repo-a"])
        agent = ClaudeAgent()
        _write_cleanup_script(home_base, item, agent)
        cleanup = home_base / "cleanup.sh"
        assert cleanup.exists()
        content = cleanup.read_text()
        assert "my-task-claude" in content
        assert "/src/repo-a" in content

    @patch(
        "ai_launchpad.work_trees.read_config",
        return_value={"base_source_dir": "/src", "base_worktrees_dir": "/contexts"},
    )
    def test_cleanup_script_is_executable(self, _mock_config, tmp_path):
        home_base = tmp_path / "task"
        home_base.mkdir()
        item = _make_work_item()
        agent = ClaudeAgent()
        _write_cleanup_script(home_base, item, agent)
        cleanup = home_base / "cleanup.sh"
        assert cleanup.stat().st_mode & 0o755

    @patch(
        "ai_launchpad.work_trees.read_config",
        return_value={"base_source_dir": "/src", "base_worktrees_dir": "/contexts"},
    )
    def test_absolute_source_dir(self, _mock_config, tmp_path):
        home_base = tmp_path / "task"
        home_base.mkdir()
        item = _make_work_item(relevant_source_directories=["/absolute/repo"])
        agent = ClaudeAgent()
        _write_cleanup_script(home_base, item, agent)
        content = (home_base / "cleanup.sh").read_text()
        assert "/absolute/repo" in content

    @patch(
        "ai_launchpad.work_trees.read_config",
        return_value={"base_source_dir": "/src", "base_worktrees_dir": "/contexts"},
    )
    def test_normalizes_source_dir_with_spaces(self, _mock_config, tmp_path):
        home_base = tmp_path / "task"
        home_base.mkdir()
        item = _make_work_item(relevant_source_directories=["Foo Bar"])
        agent = ClaudeAgent()
        _write_cleanup_script(home_base, item, agent)
        content = (home_base / "cleanup.sh").read_text()
        assert "/src/foo-bar" in content


# ---------------------------------------------------------------------------
# _write_task_file
# ---------------------------------------------------------------------------
class TestWriteTaskFile:
    def test_creates_task_md(self, tmp_path):
        item = _make_work_item(
            title="Fix bug", description="desc", link="https://example.com"
        )
        _write_task_file(tmp_path, item)
        task_file = tmp_path / "task.md"
        assert task_file.exists()
        content = task_file.read_text()
        assert "# Fix bug" in content
        assert "https://example.com" in content
        assert "desc" in content
        assert "repo-a" in content

    def test_lists_all_source_directories(self, tmp_path):
        item = _make_work_item(relevant_source_directories=["repo-a", "repo-b"])
        _write_task_file(tmp_path, item)
        content = (tmp_path / "task.md").read_text()
        assert "- repo-a" in content
        assert "- repo-b" in content

    def test_markdown_structure__sections_appear_in_order(self, tmp_path):
        item = _make_work_item(
            title="My Title",
            link="https://link.example.com",
            description="Some description",
            relevant_source_directories=["src"],
        )
        _write_task_file(tmp_path, item)
        content = (tmp_path / "task.md").read_text()
        title_pos = content.index("# My Title")
        link_pos = content.index("**Link:**")
        desc_heading_pos = content.index("## Description")
        sources_heading_pos = content.index("## Relevant source directories")
        assert title_pos < link_pos < desc_heading_pos < sources_heading_pos

    def test_file_ends_with_newline(self, tmp_path):
        item = _make_work_item()
        _write_task_file(tmp_path, item)
        content = (tmp_path / "task.md").read_text()
        assert content.endswith("\n")

    def test_multiline_description__preserved_in_output(self, tmp_path):
        multiline = "First line\nSecond line\nThird line"
        item = _make_work_item(description=multiline)
        _write_task_file(tmp_path, item)
        content = (tmp_path / "task.md").read_text()
        assert "First line\nSecond line\nThird line" in content

    def test_empty_source_directories__heading_present_no_bullets(self, tmp_path):
        item = _make_work_item(relevant_source_directories=[])
        _write_task_file(tmp_path, item)
        content = (tmp_path / "task.md").read_text()
        assert "## Relevant source directories" in content
        sources_section = content.split("## Relevant source directories")[1]
        assert "- " not in sources_section

    def test_special_characters_in_title__written_verbatim(self, tmp_path):
        title = "Fix #42: refactor [core] module *urgently*"
        item = _make_work_item(title=title)
        _write_task_file(tmp_path, item)
        content = (tmp_path / "task.md").read_text()
        assert f"# {title}" in content


# ---------------------------------------------------------------------------
# _copy_relevant_source subprocess behavior
# ---------------------------------------------------------------------------
class TestCopyRelevantSourceSubprocess:
    @patch("ai_launchpad.work_items.subprocess.run")
    @patch("ai_launchpad.work_items.read_config", return_value={"base_source_dir": ""})
    def test_calls_git_worktree_new_branch(self, _mock_config, mock_run, tmp_path):
        source = tmp_path / "repo"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        mock_run.return_value = MagicMock(returncode=1)
        _copy_relevant_source(str(source), "new-branch", dest)
        worktree_call = mock_run.call_args_list[1]
        assert "worktree" in worktree_call.args[0]
        assert "-b" in worktree_call.args[0]

    @patch("ai_launchpad.work_items.subprocess.run")
    @patch("ai_launchpad.work_items.read_config", return_value={"base_source_dir": ""})
    def test_calls_git_worktree_existing_branch(self, _mock_config, mock_run, tmp_path):
        source = tmp_path / "repo"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        mock_run.return_value = MagicMock(returncode=0)
        _copy_relevant_source(str(source), "existing-branch", dest)
        worktree_call = mock_run.call_args_list[1]
        assert "worktree" in worktree_call.args[0]
        assert "-b" not in worktree_call.args[0]

    @patch("builtins.input")
    @patch("ai_launchpad.work_items.subprocess.run")
    @patch(
        "ai_launchpad.work_items.read_config",
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
    @patch("ai_launchpad.work_items.subprocess.run")
    @patch(
        "ai_launchpad.work_items.read_config",
        return_value={
            "base_source_dir": "",
            "expected_source_repo_branch": "development",
        },
    )
    def test_expected_branch_mismatch_prompts_and_continues(
        self, _mock_config, mock_run, mock_input, tmp_path
    ):
        source = tmp_path / "repo"
        source.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()

        mock_run.side_effect = [
            MagicMock(stdout="main\n"),
            MagicMock(returncode=1),
            MagicMock(returncode=0),
        ]

        _copy_relevant_source(str(source), "new-branch", dest)

        mock_input.assert_called_once()
        assert "rev-parse" in mock_run.call_args_list[0].args[0]
        worktree_call = mock_run.call_args_list[2]
        assert "worktree" in worktree_call.args[0]


# ---------------------------------------------------------------------------
# BaseAgent.start_agent_in_context
# ---------------------------------------------------------------------------
class TestStartAgentInContext:
    def test_empty_command_raises(self, tmp_path):
        agent = ClaudeAgent()
        agent.name = ""
        with pytest.raises(ValueError, match="empty"):
            agent.start_agent_in_context(tmp_path, "prompt")

    @patch("ai_launchpad.agents.time.sleep")
    @patch("ai_launchpad.agents.subprocess.run")
    @patch("ai_launchpad.agents.read_config", return_value={})
    def test_passes_prompt_to_agent_command(
        self, _mock_config, mock_run, _mock_sleep, tmp_path
    ):
        CodexAgent().start_agent_in_context(tmp_path, "my prompt")
        first_call = mock_run.call_args_list[0].args[0]
        assert "tmux" in first_call
        assert "new-session" in first_call
        assert first_call[-1] == "codex 'my prompt'"

    @patch("ai_launchpad.agents.time.sleep")
    @patch("ai_launchpad.agents.subprocess.run")
    @patch("ai_launchpad.agents.read_config", return_value={})
    def test_session_name_is_context_path_name(
        self, _mock_config, mock_run, _mock_sleep, tmp_path
    ):
        context = tmp_path / "fix-bug-claude"
        context.mkdir()
        ClaudeAgent().start_agent_in_context(context, "prompt")
        cmd = mock_run.call_args_list[0].args[0]
        s_index = cmd.index("-s")
        assert cmd[s_index + 1] == "fix-bug-claude"

    @patch("ai_launchpad.agents.time.sleep")
    @patch("ai_launchpad.agents.subprocess.run")
    @patch("ai_launchpad.agents.read_config", return_value={})
    def test_claude_includes_name_flag(
        self, _mock_config, mock_run, _mock_sleep, tmp_path
    ):
        context = tmp_path / "fix-bug-claude"
        context.mkdir()
        ClaudeAgent().start_agent_in_context(context, "my prompt")
        cmd = mock_run.call_args_list[0].args[0]
        assert cmd[-1] == "claude -n fix-bug-claude 'my prompt'"

    @patch("ai_launchpad.agents.time.sleep")
    @patch("ai_launchpad.agents.subprocess.run")
    @patch("ai_launchpad.agents.read_config", return_value={})
    def test_codex_does_not_include_name_flag(
        self, _mock_config, mock_run, _mock_sleep, tmp_path
    ):
        context = tmp_path / "fix-bug-codex"
        context.mkdir()
        CodexAgent().start_agent_in_context(context, "my prompt")
        cmd = mock_run.call_args_list[0].args[0]
        assert cmd[-1] == "codex 'my prompt'"

    @patch("ai_launchpad.agents.time.sleep")
    @patch("ai_launchpad.agents.subprocess.run")
    @patch("ai_launchpad.agents.read_config", return_value={})
    def test_defaults_to_context_path(
        self, _mock_config, mock_run, _mock_sleep, tmp_path
    ):
        ClaudeAgent().start_agent_in_context(tmp_path, "prompt")
        cmd = mock_run.call_args_list[0].args[0]
        c_index = cmd.index("-c")
        assert cmd[c_index + 1] == str(tmp_path)

    @patch("ai_launchpad.agents.time.sleep")
    @patch("ai_launchpad.agents.subprocess.run")
    @patch(
        "ai_launchpad.agents.read_config",
        return_value={"tmux_start_dir": "/custom/dir"},
    )
    def test_uses_configured_tmux_start_dir(
        self, _mock_config, mock_run, _mock_sleep, tmp_path
    ):
        ClaudeAgent().start_agent_in_context(tmp_path, "prompt")
        cmd = mock_run.call_args_list[0].args[0]
        c_index = cmd.index("-c")
        assert cmd[c_index + 1] == "/custom/dir"

    @patch("ai_launchpad.agents.time.sleep")
    @patch("ai_launchpad.agents.subprocess.run")
    @patch("ai_launchpad.agents.read_config", return_value={"tmux_start_dir": ""})
    def test_empty_tmux_start_dir_falls_back_to_context_path(
        self, _mock_config, mock_run, _mock_sleep, tmp_path
    ):
        ClaudeAgent().start_agent_in_context(tmp_path, "prompt")
        cmd = mock_run.call_args_list[0].args[0]
        c_index = cmd.index("-c")
        assert cmd[c_index + 1] == str(tmp_path)

    @patch("ai_launchpad.agents.time.sleep")
    @patch("ai_launchpad.agents.subprocess.run")
    @patch("ai_launchpad.agents.read_config", return_value={})
    def test_sends_enter_to_accept_trust_prompt(
        self, _mock_config, mock_run, mock_sleep, tmp_path
    ):
        context = tmp_path / "fix-bug-claude"
        context.mkdir()
        ClaudeAgent().start_agent_in_context(context, "prompt")
        mock_sleep.assert_called_once_with(2)
        send_keys_call = mock_run.call_args_list[1].args[0]
        assert send_keys_call == ["tmux", "send-keys", "-t", "fix-bug-claude", "Enter"]


# ---------------------------------------------------------------------------
# resolve_agent
# ---------------------------------------------------------------------------
class TestResolveAgent:
    @patch("ai_launchpad.agents.read_config", return_value={})
    def test_cli_agent_takes_precedence(self, _mock_config):
        agent = resolve_agent("claude")
        assert isinstance(agent, ClaudeAgent)

    @patch("ai_launchpad.agents.read_config", return_value={"default_agent": "claude"})
    def test_config_agent_used_when_no_cli(self, _mock_config):
        agent = resolve_agent(None)
        assert isinstance(agent, ClaudeAgent)

    @patch("ai_launchpad.agents.read_config", return_value={})
    def test_raises_when_no_agent_specified(self, _mock_config):
        with pytest.raises(ValueError, match="No agent specified"):
            resolve_agent(None)

    def test_unknown_agent_raises(self):
        with pytest.raises(ValueError, match="Unknown agent"):
            resolve_agent("nonexistent")


# ---------------------------------------------------------------------------
# setup_worktree
# ---------------------------------------------------------------------------
class TestSetupWorktree:
    @patch("ai_launchpad.work_trees._write_task_file")
    @patch("ai_launchpad.work_trees._write_cleanup_script")
    @patch("ai_launchpad.work_trees.copy_relevant_sources")
    @patch("ai_launchpad.work_trees._create_home_base")
    def test_orchestration(
        self, mock_home, mock_copy, mock_cleanup, mock_task, tmp_path
    ):
        mock_home.return_value = tmp_path / "ctx"
        (tmp_path / "ctx").mkdir()
        item = _make_work_item()
        agent = ClaudeAgent()
        result = setup_worktree(item, agent)
        mock_home.assert_called_once()
        mock_copy.assert_called_once_with(item, tmp_path / "ctx")
        mock_cleanup.assert_called_once_with(tmp_path / "ctx", item, agent)
        mock_task.assert_called_once_with(tmp_path / "ctx", item)
        assert result == tmp_path / "ctx"

    @patch("ai_launchpad.work_trees._write_task_file")
    @patch("ai_launchpad.work_trees._write_cleanup_script")
    @patch("ai_launchpad.work_trees.copy_relevant_sources")
    @patch("ai_launchpad.work_trees._create_home_base")
    def test_context_name_includes_agent_name__home_base_contains_agent_slug(
        self, mock_home, mock_copy, mock_cleanup, mock_task, tmp_path
    ):
        mock_home.return_value = tmp_path / "fix-bug-claude"
        item = _make_work_item(title="Fix bug")
        agent = ClaudeAgent()
        setup_worktree(item, agent)
        mock_home.assert_called_once_with("fix-bug-claude")

    @patch("ai_launchpad.work_trees._write_task_file")
    @patch("ai_launchpad.work_trees._write_cleanup_script")
    @patch("ai_launchpad.work_trees.copy_relevant_sources")
    @patch("ai_launchpad.work_trees._create_home_base")
    def test_context_name_includes_codex_agent__home_base_contains_codex_slug(
        self, mock_home, mock_copy, mock_cleanup, mock_task, tmp_path
    ):
        mock_home.return_value = tmp_path / "fix-bug-codex"
        item = _make_work_item(title="Fix bug")
        agent = CodexAgent()
        setup_worktree(item, agent)
        mock_home.assert_called_once_with("fix-bug-codex")

    @patch("ai_launchpad.work_trees._write_task_file")
    @patch("ai_launchpad.work_trees._write_cleanup_script")
    @patch("ai_launchpad.work_trees.copy_relevant_sources")
    @patch("ai_launchpad.work_trees._create_home_base")
    def test_two_agents_same_work_item__different_context_names(
        self, mock_home, mock_copy, mock_cleanup, mock_task, tmp_path
    ):
        item = _make_work_item(title="Fix bug")
        mock_home.side_effect = lambda name: tmp_path / name

        path_claude = setup_worktree(item, ClaudeAgent())
        path_codex = setup_worktree(item, CodexAgent())

        assert path_claude.name == "fix-bug-claude"
        assert path_codex.name == "fix-bug-codex"
        assert path_claude != path_codex

    @patch("ai_launchpad.work_trees._write_task_file")
    @patch("ai_launchpad.work_trees._write_cleanup_script")
    @patch("ai_launchpad.work_trees.copy_relevant_sources")
    @patch("ai_launchpad.work_trees._create_home_base")
    def test_title_with_special_chars__context_name_slugified_with_agent(
        self, mock_home, mock_copy, mock_cleanup, mock_task, tmp_path
    ):
        mock_home.return_value = tmp_path / "fix-the-login-bug-42-claude"
        item = _make_work_item(title="Fix the Login Bug #42!")
        agent = ClaudeAgent()
        setup_worktree(item, agent)
        mock_home.assert_called_once_with("fix-the-login-bug-42-claude")


# ---------------------------------------------------------------------------
# start_launch_sequence
# ---------------------------------------------------------------------------
class TestStartLaunchSequence:
    @patch("ai_launchpad.agents.read_config", return_value={})
    @patch("ai_launchpad.launch.setup_worktree")
    @patch("ai_launchpad.launch.get_work_items")
    @patch("ai_launchpad.launch.resolve_agent")
    def test_processes_items(
        self, mock_resolve, mock_get, mock_setup, _mock_read_config, tmp_path
    ):
        item = _make_work_item()
        mock_get.return_value = [item]
        mock_setup.return_value = tmp_path
        agent = MagicMock(spec=ClaudeAgent)
        agent.generate_prompt.return_value = "Read task.md please"
        mock_resolve.return_value = agent

        start_launch_sequence(["--agent", "claude"])

        mock_setup.assert_called_once_with(item, agent)
        agent.start_agent_in_context.assert_called_once()
        call_args = agent.start_agent_in_context.call_args.args
        assert call_args[0] == tmp_path
        assert "task.md" in call_args[1]

    @patch("ai_launchpad.launch.get_work_items", return_value=[])
    @patch("ai_launchpad.launch.resolve_agent")
    def test_parses_agent_arg(self, mock_resolve, _mock_get):
        mock_resolve.return_value = ClaudeAgent()
        start_launch_sequence(["--agent", "claude"])
        mock_resolve.assert_called_once_with("claude")

    @patch("ai_launchpad.launch.get_work_items", return_value=[])
    @patch("ai_launchpad.launch.resolve_agent")
    def test_default_agent_is_none(self, mock_resolve, _mock_get):
        mock_resolve.return_value = ClaudeAgent()
        start_launch_sequence([])
        mock_resolve.assert_called_once_with(None)

    @patch("ai_launchpad.launch.get_work_items", return_value=[])
    @patch("ai_launchpad.launch.resolve_agent")
    def test_passes_sources_from_args(self, mock_resolve, mock_get, tmp_path):
        todo = tmp_path / "todo.txt"
        todo.write_text("- Task one\n")
        mock_resolve.return_value = ClaudeAgent()
        start_launch_sequence(["--todo-file", str(todo), "--agent", "claude"])
        mock_resolve.assert_called_once_with("claude")
        sources = mock_get.call_args.args[0]
        assert len(sources) == 1
