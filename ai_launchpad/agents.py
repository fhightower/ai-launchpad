from pathlib import Path

from ai_launchpad.config import read_config
from ai_launchpad.multiplexers import BaseMultiplexer, resolve_multiplexer


def resolve_session_start_dir(context_path: Path) -> str:
    config = read_config()
    start_dir = config.get("session_start_dir") or config.get("tmux_start_dir")
    return start_dir or str(context_path)


class BaseAgent:
    name: str = ""

    @property
    def cmd(self) -> str:
        return self.name.lower()

    def build_launch_cmd(self, session_name: str, prompt: str) -> str:
        import shlex

        return f"{self.cmd} {shlex.quote(prompt)}"

    def generate_prompt(self) -> str:
        if custom_message := read_config().get("custom_agent_message"):
            return custom_message
        return "Read task.md for your work item. Feel free to ask me any questions!"

    def start_agent_in_context(
        self,
        context_path: Path,
        agent_prompt: str,
        multiplexer: BaseMultiplexer | None = None,
    ) -> None:
        if not self.cmd:
            raise ValueError("Agent command is empty.")
        session_name = context_path.name
        launch_cmd = self.build_launch_cmd(session_name, agent_prompt)
        start_dir = resolve_session_start_dir(context_path)

        if multiplexer is None:
            multiplexer = resolve_multiplexer()
        multiplexer.start_session(session_name, start_dir, launch_cmd)


class ClaudeAgent(BaseAgent):
    name = "claude"

    def build_launch_cmd(self, session_name: str, prompt: str) -> str:
        import shlex

        return f"{self.cmd} -n {shlex.quote(session_name)} {shlex.quote(prompt)}"


class CodexAgent(BaseAgent):
    name = "codex"


AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "claude": ClaudeAgent,
    "codex": CodexAgent,
}


def _get_agent_from_registry(name: str) -> BaseAgent:
    agent_class = AGENT_REGISTRY.get(name)
    if agent_class is None:
        available = ", ".join(sorted(AGENT_REGISTRY))
        raise ValueError(f"Unknown agent {name!r}. Available agents: {available}")
    return agent_class()


def resolve_agent(agent_name: str | None) -> BaseAgent:
    if agent_name:
        return _get_agent_from_registry(agent_name)
    config_agent = read_config().get("default_agent")
    if config_agent:
        return _get_agent_from_registry(config_agent)
    available = ", ".join(sorted(AGENT_REGISTRY))
    raise ValueError(
        f"No agent specified. Use --agent or set default_agent in config.toml. "
        f"Available agents: {available}"
    )
