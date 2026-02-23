from config import read_config
from data_models import WorkItem


class BaseAgent:
    name: str = ""

    @property
    def cmd(self) -> str:
        return self.name.lower()

    def generate_prompt(self, work_item: WorkItem) -> str:
        lines = [
            "Please solve the work item below. Feel free to ask me any questions!",
            "",
        ]
        if custom_message := read_config().get("custom_agent_message"):
            lines.append(custom_message)
            lines.append("")
        for key, value in work_item.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)


class ClaudeAgent(BaseAgent):
    name = "claude"


class CodexAgent(BaseAgent):
    name = "codex"


AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "claude": ClaudeAgent,
    "codex": CodexAgent,
}


def get_agent(name: str) -> BaseAgent:
    agent_class = AGENT_REGISTRY.get(name)
    if agent_class is None:
        available = ", ".join(sorted(AGENT_REGISTRY))
        raise ValueError(
            f"Unknown agent {name!r}. Available agents: {available}"
        )
    return agent_class()
