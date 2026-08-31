import subprocess
import time

from ai_launchpad.config import read_config


TRUST_PROMPT_DELAY_SECONDS = 2


class BaseMultiplexer:
    """Starts each agent in its own terminal session."""

    name: str = ""
    session_noun: str = "session"

    def start_session(self, session_name: str, start_dir: str, launch_cmd: str) -> None:
        raise NotImplementedError

    def cleanup_script_body(self) -> str:
        """Bash body for the cleanup script's `kill_session` function.

        The function receives the session name in the local `session` variable.
        Every line must survive being indented, so avoid multi-line here-docs.
        """
        raise NotImplementedError


class TmuxMultiplexer(BaseMultiplexer):
    name = "tmux"
    session_noun = "session"

    def start_session(self, session_name: str, start_dir: str, launch_cmd: str) -> None:
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
        time.sleep(TRUST_PROMPT_DELAY_SECONDS)
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "Enter"],
            check=False,
        )

    def cleanup_script_body(self) -> str:
        return (
            'tmux kill-session -t "$session" 2>/dev/null'
            ' || echo "  Session not found: $session"'
        )


class CmuxMultiplexer(BaseMultiplexer):
    name = "cmux"
    session_noun = "workspace"

    def start_session(self, session_name: str, start_dir: str, launch_cmd: str) -> None:
        result = subprocess.run(
            [
                "cmux",
                "new-workspace",
                "--name",
                session_name,
                "--cwd",
                start_dir,
                "--command",
                launch_cmd,
                "--focus",
                "false",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        workspace_ref = _parse_workspace_ref(result.stdout)
        if not workspace_ref:
            print(f"Could not determine cmux workspace for {session_name!r}.")
            return

        # Accept the agent's initial directory trust prompt
        time.sleep(TRUST_PROMPT_DELAY_SECONDS)
        subprocess.run(
            ["cmux", "send-key", "--workspace", workspace_ref, "Enter"],
            check=False,
            capture_output=True,
        )

    def cleanup_script_body(self) -> str:
        find_ref = (
            "import json, sys; "
            'print(next((w.get("ref", "") '
            'for w in json.load(sys.stdin).get("workspaces", []) '
            'if w.get("custom_title") == sys.argv[1]), ""))'
        )
        return "\n".join(
            [
                "local ref",
                "ref=$(CMUX_QUIET=1 cmux workspace list --json 2>/dev/null"
                f" | python3 -c '{find_ref}'"
                ' "$session" 2>/dev/null || true)',
                'if [[ -z "$ref" ]]; then',
                '    echo "  Workspace not found: $session"',
                "    return",
                "fi",
                'CMUX_QUIET=1 cmux close-workspace --workspace "$ref" >/dev/null 2>&1'
                ' || echo "  Failed to close: $session"',
            ]
        )


def _parse_workspace_ref(output: str) -> str:
    """Pull the `workspace:N` ref out of `cmux new-workspace` output."""
    for token in output.split():
        if token.startswith("workspace:"):
            return token
    return ""


MULTIPLEXER_REGISTRY: dict[str, type[BaseMultiplexer]] = {
    "tmux": TmuxMultiplexer,
    "cmux": CmuxMultiplexer,
}

DEFAULT_MULTIPLEXER = "tmux"


def resolve_multiplexer(multiplexer_name: str | None = None) -> BaseMultiplexer:
    name = multiplexer_name or read_config().get("multiplexer") or DEFAULT_MULTIPLEXER
    multiplexer_class = MULTIPLEXER_REGISTRY.get(name)
    if multiplexer_class is None:
        available = ", ".join(sorted(MULTIPLEXER_REGISTRY))
        raise ValueError(
            f"Unknown multiplexer {name!r}. Available multiplexers: {available}"
        )
    return multiplexer_class()
