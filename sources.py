import os
from abc import ABC, abstractmethod
from typing import NoReturn
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from requests.auth import HTTPBasicAuth

from config import read_config
from data_models import WorkItem

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 20
GITHUB_ACCESS_TOKEN_ENV_VAR = "GITHUB_ACCESS_TOKEN"

JIRA_SEARCH_ENDPOINT = "/rest/api/3/search/jql"
JIRA_PAGE_SIZE = 100
JIRA_EMAIL_ENV_VAR = "JIRA_EMAIL"
JIRA_API_TOKEN_ENV_VAR = "JIRA_API_TOKEN"
JIRA_ORG_NAME_ENV_VAR = "JIRA_ORG_NAME"


class BaseSource(ABC):
    @classmethod
    def add_arguments(cls, parser: ArgumentParser) -> None:
        pass

    @classmethod
    def from_args(cls, args: Namespace) -> list["BaseSource"]:
        return []

    @abstractmethod
    def get_work_items(self) -> list[WorkItem]: ...

    @staticmethod
    def _handle_request_error(
        exc: requests.RequestException, url: str, source_name: str
    ) -> NoReturn:
        if isinstance(exc, requests.HTTPError):
            status_code = exc.response.status_code if exc.response is not None else "?"
            detail = exc.response.text if exc.response is not None else str(exc)
            raise RuntimeError(
                f"{source_name} API request failed ({status_code}) for {url}: {detail}"
            ) from exc
        raise RuntimeError(
            f"{source_name} API request failed for {url}: {exc}"
        ) from exc


class LocalTodoFileSource(BaseSource):
    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)

    @classmethod
    def add_arguments(cls, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--todo-file",
            action="append",
            default=None,
            help="Path to a local TODO text file (can be repeated)",
        )

    @classmethod
    def from_args(cls, args: Namespace) -> list["BaseSource"]:
        return [cls(path) for path in (args.todo_file or [])]

    def get_work_items(self) -> list[WorkItem]:
        lines = self.file_path.read_text(encoding="utf-8").splitlines()
        work_items: list[WorkItem] = []
        for line in lines:
            if line.startswith("- "):
                title = line[2:].strip()
                if title:
                    work_items.append(
                        WorkItem(
                            title=title,
                            description="",
                            link="",
                            relevant_source_directories=[],
                        )
                    )
        return work_items


class GitHubIssuesSource(BaseSource):
    def __init__(self, query: str) -> None:
        self.query = query.strip()
        if not self.query:
            raise ValueError("GitHub issue query cannot be empty.")

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        github_access_token = os.environ.get(GITHUB_ACCESS_TOKEN_ENV_VAR, "").strip()
        if github_access_token:
            self._session.headers["Authorization"] = f"Bearer {github_access_token}"

    @classmethod
    def add_arguments(cls, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--github-issue-query",
            action="append",
            default=None,
            metavar="QUERY",
            help=(
                "GitHub issue query (can be repeated). "
                'For a single repo, include it in the query, for example: --github-issue-query "repo:octocat/Hello-World is:open label:bug".'
            ),
        )

    @classmethod
    def from_args(cls, args: Namespace) -> list["BaseSource"]:
        issue_queries = args.github_issue_query or []
        if not issue_queries:
            return []

        return [cls(query=query) for query in issue_queries]

    def get_work_items(self) -> list[WorkItem]:
        issues = self._fetch_issues_from_search()
        work_items: list[WorkItem] = []
        for issue in issues:
            # The list/search APIs can include pull requests; skip them.
            if "pull_request" in issue:
                continue
            work_items.append(self._issue_to_work_item(issue))
        return work_items

    def _get_json(self, url: str) -> Any:
        try:
            response = self._session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            self._handle_request_error(exc, url, "GitHub")

    def _fetch_issues_from_search(self) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        total_count: int | None = None
        page = 1
        while True:
            search_query = f"is:issue {self.query}"
            params = urlencode(
                {"q": search_query, "per_page": GITHUB_PAGE_SIZE, "page": page}
            )
            url = f"{GITHUB_API_BASE_URL}/search/issues?{params}"
            payload = self._get_json(url)
            if not isinstance(payload, dict):
                raise RuntimeError(
                    f"Unexpected GitHub search response for query '{self.query}': expected an object."
                )
            page_items = payload.get("items")
            if not isinstance(page_items, list):
                raise RuntimeError(
                    f"Unexpected GitHub search response for query '{self.query}': missing items list."
                )
            issues.extend(page_items)
            if total_count is None and isinstance(payload.get("total_count"), int):
                total_count = min(payload["total_count"], 1000)
            if (
                not page_items
                or len(page_items) < GITHUB_PAGE_SIZE
                or (total_count is not None and len(issues) >= total_count)
            ):
                break
            page += 1
        return issues

    def _issue_to_work_item(self, issue: dict[str, Any]) -> WorkItem:
        issue_number = issue.get("number")
        issue_number_text = (
            str(issue_number) if issue_number is not None else "unknown-issue"
        )
        owner_repo, repo_name = self._repo_info_from_issue(issue)
        raw_title = str(issue.get("title") or "").strip()
        title = raw_title or f"Issue #{issue_number_text}"
        body = str(issue.get("body") or "").strip()
        description = body or "No description provided."
        link = str(issue.get("html_url") or "").strip()
        if not link:
            if issue_number and owner_repo:
                link = f"https://github.com/{owner_repo}/issues/{issue_number}"
            else:
                link = "https://github.com/issues"

        if owner_repo:
            work_item_title = f"{owner_repo}#{issue_number_text}: {title}"
        else:
            work_item_title = f"#{issue_number_text}: {title}"
        return WorkItem(
            title=work_item_title,
            description=description,
            link=link,
            relevant_source_directories=[repo_name] if repo_name else [],
        )

    def _repo_info_from_issue(self, issue: dict[str, Any]) -> tuple[str, str]:
        owner_repo = self._owner_repo_from_api_url(
            str(issue.get("repository_url") or "").strip()
        ) or self._owner_repo_from_issue_url(str(issue.get("html_url") or "").strip())
        if owner_repo:
            return owner_repo, owner_repo.split("/", maxsplit=1)[1]
        return "", ""

    @staticmethod
    def _owner_repo_from_api_url(repository_url: str) -> str:
        marker = "/repos/"
        marker_index = repository_url.find(marker)
        if marker_index == -1:
            return ""
        owner_repo = repository_url[marker_index + len(marker) :].strip("/")
        if owner_repo.count("/") != 1:
            return ""
        return owner_repo

    @staticmethod
    def _owner_repo_from_issue_url(issue_url: str) -> str:
        marker = "github.com/"
        marker_index = issue_url.find(marker)
        if marker_index == -1:
            return ""
        tail = issue_url[marker_index + len(marker) :]
        parts = tail.strip("/").split("/")
        if len(parts) < 2:
            return ""
        return f"{parts[0]}/{parts[1]}"


class JiraJqlSource(BaseSource):
    def __init__(self, jql: str) -> None:
        self.jql = jql.strip()
        if not self.jql:
            raise ValueError("Jira JQL cannot be empty.")

        jira_section = read_config().get("jira", {})
        configured_org_name = str(jira_section.get("org_name") or "").strip()
        org_name = (
            os.environ.get(JIRA_ORG_NAME_ENV_VAR, "").strip() or configured_org_name
        )
        if not org_name:
            raise ValueError(
                f"Set jira.org_name in config.toml or {JIRA_ORG_NAME_ENV_VAR} in the environment."
            )

        email = os.environ.get(JIRA_EMAIL_ENV_VAR, "").strip()
        api_token = os.environ.get(JIRA_API_TOKEN_ENV_VAR, "").strip()
        if not email or not api_token:
            raise ValueError(
                f"{JIRA_EMAIL_ENV_VAR} and {JIRA_API_TOKEN_ENV_VAR} environment variables must be set."
            )

        self.base_url = f"https://{org_name}.atlassian.net"
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(email, api_token)
        self._session.headers.update({"Accept": "application/json"})

    @classmethod
    def add_arguments(cls, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--jira-jql",
            action="append",
            default=None,
            metavar="JQL",
            help=(
                "Jira JQL query (can be repeated), "
                "for example: --jira-jql \"project = CORE AND status = 'Ready for Dev'\"."
            ),
        )

    @classmethod
    def from_args(cls, args: Namespace) -> list["BaseSource"]:
        jql_queries = args.jira_jql or []
        if not jql_queries:
            return []

        return [cls(jql=jql) for jql in jql_queries]

    def get_work_items(self) -> list[WorkItem]:
        issues = self._fetch_issues()
        return [self._issue_to_work_item(issue) for issue in issues]

    def _get_json(self, endpoint: str, params: dict[str, Any]) -> Any:
        url = self.base_url + endpoint
        try:
            response = self._session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            self._handle_request_error(exc, url, "Jira")

    def _fetch_issues(self) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        start_at = 0
        while True:
            payload = self._get_json(
                JIRA_SEARCH_ENDPOINT,
                params={
                    "jql": self.jql,
                    "fields": "summary,description,components",
                    "maxResults": JIRA_PAGE_SIZE,
                    "startAt": start_at,
                },
            )
            if not isinstance(payload, dict):
                raise RuntimeError(
                    f"Unexpected Jira search response for JQL '{self.jql}': expected an object."
                )

            page = payload.get("issues")
            if not isinstance(page, list):
                raise RuntimeError(
                    f"Unexpected Jira search response for JQL '{self.jql}': missing issues list."
                )

            issues.extend(page)
            if not page:
                break

            start_at += len(page)
            total = payload.get("total")
            if isinstance(total, int) and start_at >= total:
                break

        return issues

    def _issue_to_work_item(self, issue: dict[str, Any]) -> WorkItem:
        fields = issue.get("fields")
        if not isinstance(fields, dict):
            fields = {}

        key = str(issue.get("key") or "").strip()
        summary = str(fields.get("summary") or "").strip()
        if key and summary:
            title = f"{key}: {summary}"
        elif key:
            title = key
        elif summary:
            title = summary
        else:
            title = "Jira issue"

        description = (
            self._extract_adf_text(fields.get("description"))
            or "No description provided."
        )
        link = f"{self.base_url}/browse/{key}" if key else self.base_url
        return WorkItem(
            title=title,
            description=description,
            link=link,
            relevant_source_directories=self._extract_components(fields),
        )

    def _extract_adf_text(self, node: Any) -> str:
        if isinstance(node, str):
            return node.strip()
        if not isinstance(node, dict):
            return ""
        if node.get("type") == "text":
            return str(node.get("text") or "")
        child_text = [
            self._extract_adf_text(child) for child in node.get("content", [])
        ]
        return "\n".join(text for text in child_text if text).strip()

    @staticmethod
    def _extract_components(fields: dict[str, Any]) -> list[str]:
        components = fields.get("components")
        if not isinstance(components, list):
            return []
        names: list[str] = []
        for component in components:
            if not isinstance(component, dict):
                continue
            name = str(component.get("name") or "").strip()
            if name:
                names.append(name)
        return names


SOURCE_TYPES: list[type[BaseSource]] = [
    LocalTodoFileSource,
    GitHubIssuesSource,
    JiraJqlSource,
]
