import pytest
from unittest.mock import patch

from data_models import WorkItem
from agents import BaseAgent, ClaudeAgent, CodexAgent, AGENT_REGISTRY, get_agent


def _make_work_item(**overrides) -> WorkItem:
    defaults = dict(
        title="Test item",
        description="A test work item",
        link="https://example.com",
        relevant_source_directories=["repo-a"],
    )
    defaults.update(overrides)
    return WorkItem(**defaults)


class TestBaseAgent:
    def test_cmd_is_lowercase_name(self):
        agent = BaseAgent()
        agent.name = "MyAgent"
        assert agent.cmd == "myagent"

    def test_cmd_empty_when_no_name(self):
        agent = BaseAgent()
        assert agent.cmd == ""

    @patch("agents.read_config", return_value={})
    def test_generate_prompt_without_custom_message(self, _mock_config):
        agent = BaseAgent()
        item = _make_work_item()
        prompt = agent.generate_prompt(item)
        assert "Please solve the work item below" in prompt
        assert "title: Test item" in prompt
        assert "description: A test work item" in prompt
        assert "link: https://example.com" in prompt

    @patch(
        "agents.read_config",
        return_value={"custom_agent_message": "Be thorough!"},
    )
    def test_generate_prompt_with_custom_message(self, _mock_config):
        agent = BaseAgent()
        prompt = agent.generate_prompt(_make_work_item())
        assert "Be thorough!" in prompt


class TestClaudeAgent:
    def test_name(self):
        agent = ClaudeAgent()
        assert agent.name == "claude"

    def test_cmd(self):
        agent = ClaudeAgent()
        assert agent.cmd == "claude"


class TestCodexAgent:
    def test_name(self):
        agent = CodexAgent()
        assert agent.name == "codex"

    def test_cmd(self):
        agent = CodexAgent()
        assert agent.cmd == "codex"


class TestAgentRegistry:
    def test_registry_contains_claude(self):
        assert "claude" in AGENT_REGISTRY
        assert AGENT_REGISTRY["claude"] is ClaudeAgent

    def test_registry_contains_codex(self):
        assert "codex" in AGENT_REGISTRY
        assert AGENT_REGISTRY["codex"] is CodexAgent

    def test_registry_is_not_empty(self):
        assert len(AGENT_REGISTRY) > 0


class TestGetAgent:
    def test_returns_claude_agent(self):
        agent = get_agent("claude")
        assert isinstance(agent, ClaudeAgent)

    def test_returns_codex_agent(self):
        agent = get_agent("codex")
        assert isinstance(agent, CodexAgent)

    def test_unknown_agent_raises(self):
        with pytest.raises(ValueError, match="Unknown agent 'nonexistent'"):
            get_agent("nonexistent")

    def test_error_lists_available_agents(self):
        with pytest.raises(ValueError, match="claude"):
            get_agent("nonexistent")
