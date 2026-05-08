import subprocess
import time
from argparse import ArgumentParser
from pathlib import Path

from agents import BaseAgent, get_agent, AGENT_REGISTRY
from config import read_config
from data_models import WorkItem
from sources import BaseSource, SOURCE_TYPES
from utils import slugify


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
                        entry.strip()
                        for entry in response.split(",")
                        if entry.strip()
                    ]
            confirmed.append(work_item)
    return confirmed


def _get_work_items(sources: list[BaseSource]) -> list[WorkItem]:
    work_items: list[WorkItem] = []

    for source in sources:
        work_items.extend(source.get_work_items())

    confirmed_work_items = _confirm_work_items(work_items)

    return confirmed_work_items


def _create_home_base(work_item_sluggified_title: str) -> Path:
    base_worktrees_dir = read_config()["base_worktrees_dir"]
    home_base = Path(base_worktrees_dir) / work_item_sluggified_title
    home_base.mkdir(parents=True, exist_ok=True)
    return home_base


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


def _copy_relevant_sources(work_item: WorkItem, home_base: Path) -> None:
    for source_dir in work_item["relevant_source_directories"]:
        if not Path(source_dir).is_absolute():
            source_dir = _normalize_source_dir(source_dir)
        try:
            _copy_relevant_source(source_dir, home_base.name, home_base)
        except (ValueError, subprocess.CalledProcessError) as exc:
            print(f"Warning: Failed to copy {source_dir}: {exc}")


def _write_cleanup_script(
    home_base: Path, work_item: WorkItem, agent: BaseAgent
) -> None:
    config = read_config()
    base_source_dir = config["base_source_dir"]
    base_worktrees_dir = config["base_worktrees_dir"]

    tmux_sessions = [f"{home_base.name}"]

    source_repos = []
    worktree_paths = []
    for source_dir in work_item["relevant_source_directories"]:
        source_dir_path = Path(source_dir)
        if source_dir_path.is_absolute():
            source_path = source_dir_path
        else:
            source_path = Path(base_source_dir) / _normalize_source_dir(source_dir)
        source_repos.append(str(source_path))
        worktree_paths.append(str(home_base / source_path.name))

    def bash_array(items: list[str]) -> str:
        return " ".join(f'"{item}"' for item in items)

    template_path = Path(__file__).with_name("cleanup_template.sh")
    script = template_path.read_text(encoding="utf-8")
    script = script.replace("__CONTEXT_NAME__", home_base.name)
    script = script.replace("__HOME_BASE__", str(home_base))
    script = script.replace("__TMUX_SESSIONS__", bash_array(tmux_sessions))
    script = script.replace("__SOURCE_REPOS__", bash_array(source_repos))
    script = script.replace("__WORKTREE_PATHS__", bash_array(worktree_paths))
    script = script.replace("__BASE_WORKTREES_DIR__", str(base_worktrees_dir))

    cleanup_path = home_base / "cleanup.sh"
    cleanup_path.write_text(script, encoding="utf-8")
    cleanup_path.chmod(0o755)


def _write_task_file(home_base: Path, work_item: WorkItem) -> None:
    lines = [
        f"# {work_item['title']}",
        "",
        f"**Link:** {work_item['link']}",
        "",
        "## Description",
        "",
        work_item["description"],
        "",
        "## Relevant source directories",
        "",
    ]
    for source_dir in work_item["relevant_source_directories"]:
        lines.append(f"- {source_dir}")
    task_path = home_base / "task.md"
    task_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _create_context(work_item: WorkItem, agent: BaseAgent) -> Path:
    sluggified_title = slugify(work_item["title"])
    context_name = f"{sluggified_title}-{slugify(agent.name)}"
    home_base = _create_home_base(context_name)
    _copy_relevant_sources(work_item, home_base)
    _write_cleanup_script(home_base, work_item, agent)
    _write_task_file(home_base, work_item)
    return home_base


def _start_agent_in_context(
    context_path: Path, agent: BaseAgent, agent_prompt: str
) -> None:
    if not agent.cmd:
        raise ValueError("Agent command is empty.")
    session_name = context_path.name
    launch_cmd = agent.build_launch_cmd(session_name, agent_prompt)

    start_dir = read_config().get("tmux_start_dir") or str(context_path)

    subprocess.run(
        [
            "tmux",
            "new-session",
            "-s",
            session_name,
            "-d",
            "-c",
            start_dir,
            launch_cmd,
        ],
        check=True,
    )

    # Accept the agent's initial directory trust prompt
    time.sleep(2)
    subprocess.run(
        ["tmux", "send-keys", "-t", session_name, "Enter"],
        check=False,
    )


def _resolve_agent(agent_name: str | None) -> BaseAgent:
    if agent_name:
        return get_agent(agent_name)
    config_agent = read_config().get("default_agent")
    if config_agent:
        return get_agent(config_agent)
    available = ", ".join(sorted(AGENT_REGISTRY))
    raise ValueError(
        f"No agent specified. Use --agent or set default_agent in config.toml. "
        f"Available agents: {available}"
    )


def lift_off(sources: list[BaseSource], agent: BaseAgent):
    for work_item in _get_work_items(sources):
        context_path = _create_context(work_item, agent)
        prompt = agent.generate_prompt()
        _start_agent_in_context(context_path, agent, prompt)


def start_launch_sequence(argv: list[str] | None = None) -> None:
    parser = ArgumentParser(
        description="Launch agent workflows from one or more work-item sources."
    )
    for source_type in SOURCE_TYPES:
        source_type.add_arguments(parser)
    available_agents = ", ".join(sorted(AGENT_REGISTRY))
    parser.add_argument(
        "--agent",
        default=None,
        metavar="NAME",
        help=f"Agent to use (available: {available_agents}). "
        "Overrides default_agent in config.toml.",
    )
    args = parser.parse_args(argv)

    sources: list[BaseSource] = []
    for source_type in SOURCE_TYPES:
        sources.extend(source_type.from_args(args))

    agent = _resolve_agent(args.agent)
    lift_off(sources, agent)


if __name__ == "__main__":
    start_launch_sequence()
