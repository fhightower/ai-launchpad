import re
import shlex
import subprocess
import time
from argparse import ArgumentParser
from pathlib import Path

from agents import AGENTS
from config import read_config
from data_models import WorkItem
from sources import BaseSource, SOURCE_TYPES


def _confirm_work_items(work_items: list[WorkItem]) -> list[WorkItem]:
    confirmed: list[WorkItem] = []
    for work_item in work_items:
        print(f"\n--- {work_item['title']} ---")
        print(work_item["link"])
        print(work_item["description"][:200])
        print(f"Source dirs: {', '.join(work_item['relevant_source_directories'])}")
        response = input("Queue this work item? [y/N]: ").strip().lower()
        if response == "y":
            confirmed.append(work_item)
    return confirmed


def _get_work_items(sources: list[BaseSource]) -> list[WorkItem]:
    work_items: list[WorkItem] = []

    for source in sources:
        work_items.extend(source.get_work_items())

    return work_items


def _create_home_base(work_item_sluggified_title: str) -> Path:
    base_contexts_dir = read_config()["base_contexts_dir"]
    home_base = Path(base_contexts_dir) / work_item_sluggified_title
    home_base.mkdir(parents=True, exist_ok=True)
    return home_base


def _copy_relevant_source(source_dir: str, new_branch: str, home_base: Path) -> None:
    base_source_dir = read_config()["base_source_dir"]
    source_path = Path(base_source_dir) / source_dir
    destination_path = home_base / source_path.name

    if not source_path.is_dir():
        raise ValueError(
            f"Source directory {source_path} does not exist or is not a directory."
        )
    if destination_path.exists():
        raise ValueError(f"Destination path {destination_path} already exists.")

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


def _copy_relevant_sources(work_item: WorkItem, home_base: Path) -> None:
    for source_dir in work_item["relevant_source_directories"]:
        source_dir = source_dir.lower()
        try:
            _copy_relevant_source(source_dir, home_base.name, home_base)
        except (ValueError, subprocess.CalledProcessError) as exc:
            print(f"Warning: Failed to copy {source_dir}: {exc}")


def _write_cleanup_script(home_base: Path, work_item: WorkItem) -> None:
    base_source_dir = read_config()["base_source_dir"]

    tmux_sessions = []
    for agent in AGENTS:
        safe_agent = re.sub(r"[^a-z0-9]+", "-", agent.cmd.lower()).strip("-") or "agent"
        tmux_sessions.append(f"{home_base.name}-{safe_agent}")

    source_repos = []
    worktree_paths = []
    for source_dir in work_item["relevant_source_directories"]:
        source_path = Path(base_source_dir) / source_dir.lower()
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

    cleanup_path = home_base / "cleanup.sh"
    cleanup_path.write_text(script, encoding="utf-8")
    cleanup_path.chmod(0o755)


def _create_context(work_item: WorkItem) -> Path:
    sluggified_title = re.sub(r"[^a-z0-9]+", "-", work_item["title"].lower()).strip("-")
    home_base = _create_home_base(sluggified_title)
    _copy_relevant_sources(work_item, home_base)
    _write_cleanup_script(home_base, work_item)
    return home_base


def _start_agent_in_context(
    context_path: Path, agent_cmd: str, agent_prompt: str
) -> None:
    agent_args = shlex.split(agent_cmd)
    if not agent_args:
        raise ValueError("Agent command is empty.")
    safe_agent = re.sub(r"[^a-z0-9]+", "-", agent_cmd.lower()).strip("-") or "agent"
    session_name = f"{context_path.name}-{safe_agent}"

    prompt_path = context_path / f"agent_prompt_{safe_agent}.txt"
    prompt_path.write_text(agent_prompt, encoding="utf-8")

    subprocess.run(
        [
            "tmux",
            "new-session",
            "-s",
            session_name,
            "-d",
            "-c",
            str(context_path),
            *agent_args,
        ],
        check=True,
    )
    target = f"{session_name}:0.0"
    # Wait for some time to let the agent start and wait for confirmation
    time.sleep(3)
    # Affirm the agent has access to the dir
    subprocess.run(
        ["tmux", "send-keys", "-t", target, "C-m"],
        check=True,
    )
    prompt_instruction = f"Please read and act on the prompt from {prompt_path.name} in the current directory."
    subprocess.run(
        ["tmux", "send-keys", "-t", target, "-l", prompt_instruction],
        check=True,
    )
    subprocess.run(
        ["tmux", "send-keys", "-t", target, "C-m"],
        check=True,
    )
    subprocess.run(
        ["tmux", "send-keys", "-t", target, "C-m"],
        check=True,
    )


def launch(sources: list[BaseSource]):
    for work_item in _get_work_items(sources):
        context_path = _create_context(work_item)
        for agent in AGENTS:
            prompt = agent.generate_prompt(work_item)
            _start_agent_in_context(context_path, agent.cmd, prompt)


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Launch agent workflows from one or more work-item sources."
    )
    for source_type in SOURCE_TYPES:
        source_type.add_arguments(parser)
    args = parser.parse_args()

    sources: list[BaseSource] = []
    for source_type in SOURCE_TYPES:
        sources.extend(source_type.from_args(args))

    launch(sources)
