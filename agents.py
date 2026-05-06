from config import read_config


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


def get_agent(name: str) -> BaseAgent:
    agent_class = AGENT_REGISTRY.get(name)
    if agent_class is None:
        available = ", ".join(sorted(AGENT_REGISTRY))
        raise ValueError(f"Unknown agent {name!r}. Available agents: {available}")
    return agent_class()
