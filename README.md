# AI Launchpad

A light-weight framework for making simultaneous agentic updates to a multiple repositories.

## Initial Setup

The first time you are setting up this project, you will need to:

todo: ...

## Quickstart

Once this project is [setup](#initial-setup), you can get started with:

todo: ...

### GitHub Issue Sources

You can load work items directly from GitHub issues:

```bash
# Pull issues using a GitHub issue query for one repo
python launch_pad.py --github-issue-query "repo:owner/repo is:open label:bug sort:updated-desc"

# Mix and match multiple sources
python launch_pad.py \
  --todo-file ./todo \
  --github-issue-query "repo:owner/repo-a is:open assignee:@me" \
  --github-issue-query "org:owner is:open label:bug"
```

## Principles

- Credentials are in `.env` (loaded with [direnv](https://direnv.net/))
