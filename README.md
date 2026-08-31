# AI Launchpad
[![Tests](https://github.com/fhightower/ai-launchpad/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/fhightower/ai-launchpad/actions/workflows/test.yml)

A lightweight framework for making simultaneous agentic updates to multiple repositories.

## Initial Setup

The first time you are setting up this project, you will need to:

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
2. Run `uv sync` to create a virtual environment and install all dependencies
3. Copy `config-example.toml` to `config.toml` and fill in your configuration and credentials

Optional config:

- `expected_source_repo_branch` (example: `"dev"`): if set, Launchpad will pause before creating each worktree until the source repo is on this branch.
- `multiplexer` (`"tmux"` or `"cmux"`, defaults to `"tmux"`): which terminal multiplexer to start agent sessions in. Override per run with `--multiplexer`.
- `session_start_dir` (example: `"~/code"`): if set, agent sessions start in this directory instead of the work item's context path.

## Quickstart

Once this project is [set up](#initial-setup), you can get started with:

```bash
uv run python launch.py -h
```

## Sources

### Local TODO File Sources

You can load work items from a local text file. Each line that starts with `- ` is treated as a work item title; all other lines are ignored. The file's parent directory is used as the relevant source directory for the items it contains.

```bash
# Load work items from a local todo file
uv run python launch.py --todo-file ./todo

# The flag can be repeated to combine multiple files
uv run python launch.py --todo-file ./todo --todo-file ../other-repo/todo
```

Example `todo` file:

```
- Add retry logic to the upload client
- Fix the off-by-one error in the pagination helper
```

### GitHub Issue Sources

You can load work items directly from GitHub issues:

Set `github.access_token` in `config.toml` if queries need private-repo access.

```bash
# Pull issues using a GitHub issue query for one repo
uv run python launch.py --github-issue-query "repo:owner/repo is:open label:bug sort:updated-desc"

# Launch a single issue by number
uv run python launch.py --github-issue-query "repo:owner/repo is:issue 123"

# Mix and match multiple sources
uv run python launch.py \
  --todo-file ./todo \
  --github-issue-query "repo:owner/repo-a is:open assignee:@me" \
  --github-issue-query "org:owner is:open label:bug"
```

The query uses [GitHub's issue search syntax](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests). To target a single issue, include the issue number directly in the query string along with the repo qualifier.

### Jira Sources

You can load work items from Jira using JQL:

```bash
uv run python launch.py --jira-jql "project = CORE AND status = 'Backlog' ORDER BY created DESC"

# Launch a single Jira ticket by key
uv run python launch.py --jira-jql "key = CORE-123"
```

Required config for Jira (set in `config.toml`):

- `jira.org_name`
- `jira.email`
- `jira.api_token`

### Linear Sources

You can load work items from Linear:

```bash
# Launch a single Linear issue by identifier
uv run python launch.py --linear-query "ENG-123"

# Pull issues using a Linear IssueFilter as JSON
uv run python launch.py --linear-query '{"team":{"key":{"eq":"ENG"}},"state":{"type":{"neq":"completed"}}}'
```

The query is either an issue identifier (e.g. `ENG-123`) or a Linear [IssueFilter](https://developers.linear.app/docs/graphql/working-with-the-graphql-api/filtering) encoded as JSON.

Required config for Linear (set in `config.toml`):

- `linear.api_key` — a [Linear personal API key](https://linear.app/settings/account/security)
