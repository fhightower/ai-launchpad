from argparse import ArgumentParser

from ai_launchpad.agents import AGENT_REGISTRY, resolve_agent
from ai_launchpad.multiplexers import MULTIPLEXER_REGISTRY, resolve_multiplexer
from ai_launchpad.sources import BaseSource, SOURCE_TYPES
from ai_launchpad.work_items import (
    get_work_items,
)
from ai_launchpad.work_trees import setup_worktree


def _setup_parser():
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
    available_multiplexers = ", ".join(sorted(MULTIPLEXER_REGISTRY))
    parser.add_argument(
        "--multiplexer",
        default=None,
        metavar="NAME",
        help=f"Terminal multiplexer to run agents in "
        f"(available: {available_multiplexers}). "
        "Overrides multiplexer in config.toml.",
    )
    return parser


def start_launch_sequence(argv: list[str] | None = None) -> None:
    parser = _setup_parser()
    args = parser.parse_args(argv)

    sources: list[BaseSource] = []
    for source_type in SOURCE_TYPES:
        sources.extend(source_type.from_args(args))

    agent = resolve_agent(args.agent)
    multiplexer = resolve_multiplexer(args.multiplexer)

    for work_item in get_work_items(sources):
        context_path = setup_worktree(work_item, agent, multiplexer)
        prompt = agent.generate_prompt()
        agent.start_agent_in_context(context_path, prompt, multiplexer)


if __name__ == "__main__":
    start_launch_sequence()
