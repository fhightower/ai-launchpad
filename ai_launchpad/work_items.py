from typing import TYPE_CHECKING, TypedDict
from pathlib import Path
import subprocess


from ai_launchpad.config import read_config

if TYPE_CHECKING:
    from ai_launchpad.sources import BaseSource


class WorkItem(TypedDict):
    title: str
    description: str
    link: str
    relevant_source_directories: list[str]


def _get_current_branch(source_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_path), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _wait_for_expected_source_branch(source_path: Path, expected_branch: str) -> None:
    current_branch = _get_current_branch(source_path)
    if current_branch == expected_branch:
        return
    print(
        f"Source repository {source_path} is on branch "
        f"'{current_branch}', expected '{expected_branch}'."
    )
    input(
        f"Switch to '{expected_branch}' and press Enter, "
        "or press Enter to continue on the current branch: "
    )


def _copy_relevant_source(source_dir: str, new_branch: str, home_base: Path) -> None:
    config = read_config()
    source_dir_path = Path(source_dir)
    if source_dir_path.is_absolute():
        source_path = source_dir_path
    else:
        base_source_dir = config["base_source_dir"]
        source_path = Path(base_source_dir) / source_dir
    destination_path = home_base / source_path.name

    if not source_path.is_dir():
        raise ValueError(
            f"Source directory {source_path} does not exist or is not a directory."
        )
    if destination_path.exists():
        raise ValueError(f"Destination path {destination_path} already exists.")
    if expected_branch := config.get("expected_source_repo_branch"):
        _wait_for_expected_source_branch(source_path, expected_branch)

    branch_exists = (
        subprocess.run(
            [
                "git",
                "-C",
                str(source_path),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{new_branch}",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )

    cmd = ["git", "-C", str(source_path), "worktree", "add"]
    if not branch_exists:
        cmd += ["-b", new_branch, str(destination_path)]
    else:
        cmd += [str(destination_path), new_branch]
    subprocess.run(cmd, check=True)


def _normalize_source_dir(source_dir: str) -> str:
    return source_dir.lower().replace(" ", "-")


def copy_relevant_sources(work_item: WorkItem, home_base: Path) -> None:
    for source_dir in work_item["relevant_source_directories"]:
        if not Path(source_dir).is_absolute():
            source_dir = _normalize_source_dir(source_dir)
        try:
            _copy_relevant_source(source_dir, home_base.name, home_base)
        except (ValueError, subprocess.CalledProcessError) as exc:
            print(f"Warning: Failed to copy {source_dir}: {exc}")


def _confirm_work_items(work_items: list[WorkItem]) -> list[WorkItem]:
    confirmed: list[WorkItem] = []
    for work_item in work_items:
        print(f"\n--- {work_item['title']} ---")
        print(work_item["link"])
        print(work_item["description"][:200])
        source_dirs = work_item["relevant_source_directories"]
        source_dirs_text = ", ".join(source_dirs) if source_dirs else "(none)"
        print(f"Source dirs: {source_dirs_text}")
        response = input("Queue this work item? [y/N]: ").strip().lower()
        if response == "y":
            if not source_dirs:
                response = input(
                    "No source directories found. "
                    "Enter source directory path(s) (comma-separated) or leave blank to continue: "
                ).strip()
                if response:
                    work_item["relevant_source_directories"] = [
                        entry.strip() for entry in response.split(",") if entry.strip()
                    ]
            confirmed.append(work_item)
    return confirmed


def get_work_items(sources: "list[BaseSource]") -> list[WorkItem]:
    work_items: list[WorkItem] = []

    for source in sources:
        work_items.extend(source.get_work_items())

    confirmed_work_items = _confirm_work_items(work_items)

    return confirmed_work_items
