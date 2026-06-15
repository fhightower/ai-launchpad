import shlex
from pathlib import Path

from ai_launchpad.agents import BaseAgent
from ai_launchpad.config import read_config
from ai_launchpad.utils import slugify
from ai_launchpad.work_items import (
    WorkItem,
    _normalize_source_dir,
    copy_relevant_sources,
)


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
        return " ".join(shlex.quote(item) for item in items)

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


def _create_home_base(work_item_sluggified_title: str) -> Path:
    base_worktrees_dir = read_config()["base_worktrees_dir"]
    home_base = Path(base_worktrees_dir) / work_item_sluggified_title
    home_base.mkdir(parents=True, exist_ok=True)
    return home_base


def setup_worktree(work_item: WorkItem, agent: BaseAgent) -> Path:
    sluggified_title = slugify(work_item["title"])
    context_name = f"{sluggified_title}-{slugify(agent.name)}"
    home_base = _create_home_base(context_name)
    copy_relevant_sources(work_item, home_base)
    _write_cleanup_script(home_base, work_item, agent)
    _write_task_file(home_base, work_item)
    return home_base
