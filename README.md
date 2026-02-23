# AI Launchpad

A light-weight framework for making simultaneous agentic updates to a multiple repositories.

## Initial Setup

The first time you are setting up this project, you will need to:

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
2. Run `uv sync` to create a virtual environment and install all dependencies
3. Copy `.env.example` to `.env` and fill in any required credentials (e.g. GitHub access token, Jira credentials)
4. Copy `config-example.toml` to `config.toml` and fill in any required configuration (e.g. Jira org name)

## Quickstart

Once this project is [setup](#initial-setup), you can get started with:

```bash
uv run python launch_pad.py -h
```

### GitHub Issue Sources

You can load work items directly from GitHub issues:

Set `GITHUB_ACCESS_TOKEN` in your environment if queries need private-repo access.

```bash
# Pull issues using a GitHub issue query for one repo
uv run python launch_pad.py --github-issue-query "repo:owner/repo is:open label:bug sort:updated-desc"

# Mix and match multiple sources
uv run python launch_pad.py \
  --todo-file ./todo \
  --github-issue-query "repo:owner/repo-a is:open assignee:@me" \
  --github-issue-query "org:owner is:open label:bug"
```

### Jira Sources

You can load work items from Jira using JQL:

```bash
uv run python launch_pad.py --jira-jql "project = CORE AND status = 'Backlog' ORDER BY created DESC"
```

Required environment/config for Jira:

- Set `JIRA_EMAIL` and `JIRA_API_TOKEN` in the environment.
- Set `jira.org_name` in `config.toml` (or set `JIRA_ORG_NAME` in the environment).

## Principles

- Credentials are in `.env` (loaded with [direnv](https://direnv.net/))
