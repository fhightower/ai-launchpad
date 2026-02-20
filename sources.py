from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from data_models import WorkItem

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_PAGE_SIZE = 100
GITHUB_TIMEOUT_SECONDS = 20


class BaseSource:
    @classmethod
    def add_arguments(cls, parser: ArgumentParser) -> None:
        pass

    @classmethod
    def from_args(cls, args: Namespace) -> list["BaseSource"]:
        return []

    def get_work_items(self) -> list[WorkItem]:
        raise NotImplementedError("This should be implemented by each child class")


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
            response = self._session.get(url, timeout=GITHUB_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "?"
            detail = exc.response.text if exc.response is not None else str(exc)
            raise RuntimeError(
                f"GitHub API request failed ({status_code}) for {url}: {detail}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(
                f"GitHub API request failed for {url}: {exc}"
            ) from exc

    def _fetch_issues_from_search(self) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        total_count: int | None = None
        page = 1
        while True:
            search_query = f"is:issue {self.query}".strip()
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
        repository_url = str(issue.get("repository_url") or "").strip()
        repo_from_api = self._owner_repo_from_api_url(repository_url)
        if repo_from_api:
            owner_repo = repo_from_api
            return owner_repo, owner_repo.split("/", maxsplit=1)[1]

        issue_link = str(issue.get("html_url") or "").strip()
        repo_from_html = self._owner_repo_from_issue_url(issue_link)
        if repo_from_html:
            owner_repo = repo_from_html
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


SOURCE_TYPES: list[type[BaseSource]] = [
    LocalTodoFileSource,
    GitHubIssuesSource,
]
