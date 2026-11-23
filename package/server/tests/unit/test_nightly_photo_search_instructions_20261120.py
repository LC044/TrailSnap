"""Search prompt assembly for the photo-search agent."""
from datetime import datetime

import pytest

from app.service.agent.photo_search import search_instructions

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def test_search_only_variant_extends_the_shared_instructions():
    shared = search_instructions(False)
    specific = search_instructions(True)
    assert specific.endswith(shared)
    assert len(specific) > len(shared)


def test_search_only_variant_mentions_the_current_date():
    assert datetime.now().strftime("%Y-%m-%d") in search_instructions(True)
