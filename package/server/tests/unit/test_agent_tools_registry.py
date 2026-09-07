import pytest

from app.service.agent.tools import get_agent_tools

pytestmark = [pytest.mark.smoke]


def test_agent_tool_registry_contains_core_tools():
    tools = get_agent_tools("unit-user", "unit-session")
    names = {tool.name for tool in tools}

    assert len(tools) == 23
    assert len(names) == len(tools)
    assert {
        "search_photos_tool",
        "search_photos_v2",
        "get_trip_tickets",
        "create_artifact_draft",
        "propose_album_organization",
    }.issubset(names)