import pytest
from argparse import ArgumentParser, Namespace
from unittest.mock import patch, MagicMock

import requests

from data_models import WorkItem
from sources import (
    BaseSource,
    LocalTodoFileSource,
    GitHubIssuesSource,
    JiraJqlSource,
    SOURCE_TYPES,
)

BASE_CONFIG = {
    "base_contexts_dir": "/tmp",
    "base_source_dir": "/tmp",
}


# ---------------------------------------------------------------------------
# BaseSource
# ---------------------------------------------------------------------------
class TestBaseSource:
    def test_handle_request_error_http_error(self):
        response = MagicMock()
        response.status_code = 404
        response.text = "Not Found"
        exc = requests.HTTPError(response=response)
        with pytest.raises(RuntimeError, match="404"):
            BaseSource._handle_request_error(exc, "https://x", "TestSource")

    def test_handle_request_error_http_error_no_response(self):
        exc = requests.HTTPError("connection failed")
        exc.response = None
        with pytest.raises(RuntimeError, match="TestSource"):
            BaseSource._handle_request_error(exc, "https://x", "TestSource")

    def test_handle_request_error_generic(self):
        exc = requests.ConnectionError("timeout")
        with pytest.raises(RuntimeError, match="timeout"):
            BaseSource._handle_request_error(exc, "https://x", "TestSource")

    def test_default_add_arguments_is_noop(self):
        parser = ArgumentParser()
        BaseSource.add_arguments(parser)

    def test_default_from_args_returns_empty(self):
        assert BaseSource.from_args(Namespace()) == []


# ---------------------------------------------------------------------------
# LocalTodoFileSource
# ---------------------------------------------------------------------------
class TestLocalTodoFileSource:
    def test_get_work_items(self, tmp_path):
        todo = tmp_path / "todo.txt"
        todo.write_text("- Fix login bug\n- Update docs\nignored line\n- \n")
        source = LocalTodoFileSource(todo)
        items = source.get_work_items()
        assert len(items) == 2
        assert items[0]["title"] == "Fix login bug"
        assert items[1]["title"] == "Update docs"
        assert items[0]["description"] == ""
        assert items[0]["relevant_source_directories"] == [str(tmp_path)]

    def test_empty_file(self, tmp_path):
        todo = tmp_path / "empty.txt"
        todo.write_text("")
        assert LocalTodoFileSource(todo).get_work_items() == []

    def test_add_arguments(self):
        parser = ArgumentParser()
        LocalTodoFileSource.add_arguments(parser)
        args = parser.parse_args(["--todo-file", "a.txt", "--todo-file", "b.txt"])
        assert args.todo_file == ["a.txt", "b.txt"]

    def test_from_args(self):
        args = Namespace(todo_file=["a.txt", "b.txt"])
        sources = LocalTodoFileSource.from_args(args)
        assert len(sources) == 2

    def test_from_args_none(self):
        args = Namespace(todo_file=None)
        assert LocalTodoFileSource.from_args(args) == []


# ---------------------------------------------------------------------------
# GitHubIssuesSource
# ---------------------------------------------------------------------------
class TestGitHubIssuesSource:
    def test_empty_query_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            GitHubIssuesSource("")

    def test_whitespace_query_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            GitHubIssuesSource("   ")

    @patch("sources.read_config", return_value={**BASE_CONFIG})
    def test_init_without_token(self, _mock_config):
        source = GitHubIssuesSource("repo:a/b is:open")
        assert "Authorization" not in source._session.headers

    @patch("sources.read_config", return_value={**BASE_CONFIG, "github": {"access_token": "ghp_test123"}})
    def test_init_with_token(self, _mock_config):
        source = GitHubIssuesSource("repo:a/b is:open")
        assert source._session.headers["Authorization"] == "Bearer ghp_test123"

    def test_add_arguments(self):
        parser = ArgumentParser()
        GitHubIssuesSource.add_arguments(parser)
        args = parser.parse_args(["--github-issue-query", "is:open"])
        assert args.github_issue_query == ["is:open"]

    def test_from_args_empty(self):
        args = Namespace(github_issue_query=None)
        assert GitHubIssuesSource.from_args(args) == []

    def test_from_args(self):
        args = Namespace(github_issue_query=["q1", "q2"])
        sources = GitHubIssuesSource.from_args(args)
        assert len(sources) == 2

    # --- owner/repo parsing ---
    def test_owner_repo_from_api_url(self):
        url = "https://api.github.com/repos/octocat/Hello-World"
        assert GitHubIssuesSource._owner_repo_from_api_url(url) == "octocat/Hello-World"

    def test_owner_repo_from_api_url_invalid(self):
        assert GitHubIssuesSource._owner_repo_from_api_url("https://example.com") == ""

    def test_owner_repo_from_api_url_too_many_segments(self):
        url = "https://api.github.com/repos/a/b/c"
        assert GitHubIssuesSource._owner_repo_from_api_url(url) == ""

    def test_owner_repo_from_issue_url(self):
        url = "https://github.com/octocat/Hello-World/issues/42"
        assert GitHubIssuesSource._owner_repo_from_issue_url(url) == "octocat/Hello-World"

    def test_owner_repo_from_issue_url_invalid(self):
        assert GitHubIssuesSource._owner_repo_from_issue_url("https://example.com") == ""

    def test_owner_repo_from_issue_url_short(self):
        assert GitHubIssuesSource._owner_repo_from_issue_url("https://github.com/x") == ""

    # --- issue to work item ---
    def test_issue_to_work_item(self):
        source = GitHubIssuesSource("repo:a/b")
        issue = {
            "number": 42,
            "title": "Bug title",
            "body": "Bug body",
            "html_url": "https://github.com/octocat/Hello-World/issues/42",
            "repository_url": "https://api.github.com/repos/octocat/Hello-World",
        }
        item = source._issue_to_work_item(issue)
        assert item["title"] == "octocat/Hello-World#42: Bug title"
        assert item["description"] == "Bug body"
        assert item["link"] == "https://github.com/octocat/Hello-World/issues/42"
        assert item["relevant_source_directories"] == ["Hello-World"]

    def test_issue_to_work_item_no_body(self):
        source = GitHubIssuesSource("repo:a/b")
        issue = {
            "number": 1,
            "title": "No body",
            "body": None,
            "html_url": "https://github.com/a/b/issues/1",
            "repository_url": "https://api.github.com/repos/a/b",
        }
        item = source._issue_to_work_item(issue)
        assert item["description"] == "No description provided."

    def test_issue_to_work_item_no_title(self):
        source = GitHubIssuesSource("repo:a/b")
        issue = {
            "number": 5,
            "title": "",
            "body": "desc",
            "html_url": "https://github.com/a/b/issues/5",
            "repository_url": "https://api.github.com/repos/a/b",
        }
        item = source._issue_to_work_item(issue)
        assert "Issue #5" in item["title"]

    def test_issue_to_work_item_no_repo_info(self):
        source = GitHubIssuesSource("repo:a/b")
        issue = {
            "number": 1,
            "title": "Orphan",
            "body": "desc",
            "html_url": "",
            "repository_url": "",
        }
        item = source._issue_to_work_item(issue)
        assert item["title"] == "#1: Orphan"
        assert item["relevant_source_directories"] == []

    # --- get_work_items filters PRs ---
    def test_get_work_items_filters_pull_requests(self):
        source = GitHubIssuesSource("repo:a/b")
        issues = [
            {
                "number": 1,
                "title": "Real issue",
                "body": "",
                "html_url": "https://github.com/a/b/issues/1",
                "repository_url": "https://api.github.com/repos/a/b",
            },
            {
                "number": 2,
                "title": "A PR",
                "body": "",
                "html_url": "https://github.com/a/b/pull/2",
                "repository_url": "https://api.github.com/repos/a/b",
                "pull_request": {"url": "..."},
            },
        ]
        with patch.object(source, "_fetch_issues_from_search", return_value=issues):
            items = source.get_work_items()
        assert len(items) == 1
        assert items[0]["title"].endswith("Real issue")

    # --- fetch_issues_from_search pagination ---
    def test_fetch_issues_from_search_single_page(self):
        source = GitHubIssuesSource("repo:a/b")
        payload = {"total_count": 1, "items": [{"id": 1}]}
        with patch.object(source, "_get_json", return_value=payload):
            result = source._fetch_issues_from_search()
        assert result == [{"id": 1}]

    def test_fetch_issues_from_search_invalid_response(self):
        source = GitHubIssuesSource("repo:a/b")
        with patch.object(source, "_get_json", return_value="not a dict"):
            with pytest.raises(RuntimeError, match="expected an object"):
                source._fetch_issues_from_search()

    def test_fetch_issues_from_search_missing_items(self):
        source = GitHubIssuesSource("repo:a/b")
        with patch.object(source, "_get_json", return_value={"total_count": 0}):
            with pytest.raises(RuntimeError, match="missing items list"):
                source._fetch_issues_from_search()


# ---------------------------------------------------------------------------
# JiraJqlSource
# ---------------------------------------------------------------------------
class TestJiraJqlSource:
    @pytest.fixture(autouse=True)
    def _clear_config_cache(self):
        from config import read_config

        read_config.cache_clear()
        yield
        read_config.cache_clear()

    def _make_source(self, jql="project = X", org_name="myorg"):
        config = {
            **BASE_CONFIG,
            "jira": {
                "org_name": org_name,
                "email": "user@example.com",
                "api_token": "tok",
            },
        }
        with patch("sources.read_config", return_value=config):
            return JiraJqlSource(jql)

    def test_empty_jql_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            self._make_source(jql="")

    def test_missing_org_raises(self):
        config = {**BASE_CONFIG, "jira": {"email": "a@b.c", "api_token": "t"}}
        with (
            patch("sources.read_config", return_value=config),
            pytest.raises(ValueError, match="org_name"),
        ):
            JiraJqlSource("project = X")

    def test_missing_email_raises(self):
        config = {**BASE_CONFIG, "jira": {"org_name": "org", "api_token": "t"}}
        with (
            patch("sources.read_config", return_value=config),
            pytest.raises(ValueError, match="jira.email"),
        ):
            JiraJqlSource("project = X")

    def test_base_url(self):
        source = self._make_source(org_name="acme")
        assert source.base_url == "https://acme.atlassian.net"

    def test_add_arguments(self):
        parser = ArgumentParser()
        JiraJqlSource.add_arguments(parser)
        args = parser.parse_args(["--jira-jql", "project = X"])
        assert args.jira_jql == ["project = X"]

    def test_from_args_empty(self):
        args = Namespace(jira_jql=None)
        assert JiraJqlSource.from_args(args) == []

    # --- extract_components ---
    def test_extract_components(self):
        fields = {"components": [{"name": "backend"}, {"name": "frontend"}]}
        assert JiraJqlSource._extract_components(fields) == ["backend", "frontend"]

    def test_extract_components_empty(self):
        assert JiraJqlSource._extract_components({}) == []

    def test_extract_components_not_list(self):
        assert JiraJqlSource._extract_components({"components": "bad"}) == []

    def test_extract_components_skips_bad_entries(self):
        fields = {"components": ["not-a-dict", {"name": "ok"}, {"name": ""}]}
        assert JiraJqlSource._extract_components(fields) == ["ok"]

    # --- extract_adf_text ---
    def test_extract_adf_text_string(self):
        source = self._make_source()
        assert source._extract_adf_text("  hello  ") == "hello"

    def test_extract_adf_text_text_node(self):
        source = self._make_source()
        node = {"type": "text", "text": "content"}
        assert source._extract_adf_text(node) == "content"

    def test_extract_adf_text_nested(self):
        source = self._make_source()
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "World"}],
                },
            ],
        }
        assert source._extract_adf_text(doc) == "Hello\nWorld"

    def test_extract_adf_text_non_dict(self):
        source = self._make_source()
        assert source._extract_adf_text(42) == ""
        assert source._extract_adf_text(None) == ""

    # --- issue_to_work_item ---
    def test_issue_to_work_item(self):
        source = self._make_source(org_name="acme")
        issue = {
            "key": "PROJ-42",
            "fields": {
                "summary": "Fix the thing",
                "description": "plain text desc",
                "components": [{"name": "api"}],
            },
        }
        item = source._issue_to_work_item(issue)
        assert item["title"] == "PROJ-42: Fix the thing"
        assert item["link"] == "https://acme.atlassian.net/browse/PROJ-42"
        assert item["relevant_source_directories"] == ["api"]

    def test_issue_to_work_item_no_key(self):
        source = self._make_source()
        issue = {"fields": {"summary": "Title only"}}
        item = source._issue_to_work_item(issue)
        assert item["title"] == "Title only"

    def test_issue_to_work_item_no_fields(self):
        source = self._make_source()
        issue = {"key": "X-1", "fields": None}
        item = source._issue_to_work_item(issue)
        assert item["title"] == "X-1"

    def test_issue_to_work_item_no_key_no_summary(self):
        source = self._make_source()
        issue = {"fields": {}}
        item = source._issue_to_work_item(issue)
        assert item["title"] == "Jira issue"

    # --- fetch_issues pagination ---
    def test_fetch_issues_single_page(self):
        source = self._make_source()
        payload = {"issues": [{"key": "X-1"}], "isLast": True}
        with patch.object(source, "_get_json", return_value=payload):
            result = source._fetch_issues()
        assert result == [{"key": "X-1"}]

    def test_fetch_issues_multiple_pages(self):
        source = self._make_source()
        payloads = [
            {"issues": [{"key": "X-1"}], "isLast": False},
            {"issues": [{"key": "X-2"}], "isLast": True},
        ]
        with patch.object(source, "_get_json", side_effect=payloads):
            result = source._fetch_issues()
        assert result == [{"key": "X-1"}, {"key": "X-2"}]

    def test_fetch_issues_invalid_response(self):
        source = self._make_source()
        with patch.object(source, "_get_json", return_value="bad"):
            with pytest.raises(RuntimeError, match="expected an object"):
                source._fetch_issues()

    def test_fetch_issues_missing_issues_key(self):
        source = self._make_source()
        with patch.object(source, "_get_json", return_value={"isLast": True}):
            with pytest.raises(RuntimeError, match="missing issues list"):
                source._fetch_issues()

    def test_fetch_issues_missing_is_last(self):
        source = self._make_source()
        payload = {"issues": [{"key": "X-1"}]}
        with patch.object(source, "_get_json", return_value=payload):
            with pytest.raises(RuntimeError, match="isLast"):
                source._fetch_issues()


# ---------------------------------------------------------------------------
# SOURCE_TYPES registry
# ---------------------------------------------------------------------------
class TestSourceTypes:
    def test_all_types_registered(self):
        assert LocalTodoFileSource in SOURCE_TYPES
        assert GitHubIssuesSource in SOURCE_TYPES
        assert JiraJqlSource in SOURCE_TYPES
