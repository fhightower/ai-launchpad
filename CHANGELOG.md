# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
