# AI Launchpad
[![Tests](https://github.com/fhightower/ai-launchpad/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/fhightower/ai-launchpad/actions/workflows/test.yml)

A light-weight framework for making simultaneous agentic updates to a multiple repositories.

## Initial Setup

The first time you are setting up this project, you will need to:

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
2. Run `uv sync` to create a virtual environment and install all dependencies
3. Copy `config-example.toml` to `config.toml` and fill in your configuration and credentials

## Quickstart

Once this project is [setup](#initial-setup), you can get started with:

```bash
uv run python launch.py -h
```

### GitHub Issue Sources

You can load work items directly from GitHub issues:

Set `github.access_token` in `config.toml` if queries need private-repo access.

```bash
# Pull issues using a GitHub issue query for one repo
uv run python launch.py --github-issue-query "repo:owner/repo is:open label:bug sort:updated-desc"

# Mix and match multiple sources
uv run python launch.py \
  --todo-file ./todo \
  --github-issue-query "repo:owner/repo-a is:open assignee:@me" \
  --github-issue-query "org:owner is:open label:bug"
```

### Jira Sources

You can load work items from Jira using JQL:

```bash
uv run python launch.py --jira-jql "project = CORE AND status = 'Backlog' ORDER BY created DESC"
```

Required config for Jira (set in `config.toml`):

- `jira.org_name`
- `jira.email`
- `jira.api_token`
