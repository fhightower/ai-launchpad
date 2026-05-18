# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## 0.7.0

### Changed

- Library structure
- `custom_agent_message` config now fully replaces the default agent prompt instead of being appended to it.

## 0.6.0

### Added

- Optional `tmux_start_dir` config to start all tmux sessions in a configurable directory (defaults to context path).
- Claude agent sessions are now named via `--name` flag, making them easier to resume with `claude --resume`.
- Automatically send Enter to new tmux sessions to accept the agent's initial directory trust prompt.

### Changed

- Simplified tmux session naming to use context path name directly, removing redundant agent suffix.
- Branch mismatch prompt now allows continuing on the current branch instead of looping until switched.

## 0.5.0

### Added

- Optional `expected_source_repo_branch` config to pause and re-check source repo branches before creating worktrees.
- Work items are now written to a `task.md` file in the home base directory instead of being passed inline in the agent prompt.

### Changed

- `BaseAgent.generate_prompt()` no longer accepts a `work_item` parameter; agents are instructed to read `task.md` for their work item.

## 0.4.0

### Changed

- Move secrets from `.env` to `config.toml`
- Pass prompt to agent directly (avoids flaky tmux timing issues)
- Cleanup script now drops you into the `base_worktrees_dir`
- Changed "base_contexts_dir" to "base_worktrees_dir" in the config file

### Added

- Add codex as an agent

## 0.3.0

### Added

- `--jira-jql` source support for fetching Jira issues and mapping them to work items.

## 0.2.0

### Added

- Source support for local todo files and Github issues

## 0.1.0

### Added

- Initial launchpad framework w/ support for Claude
