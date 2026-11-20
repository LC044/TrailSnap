"""Single-edit distance used by the OCR station-name repair."""
import pytest

from app.service.ticket_journey import _one_edit

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def test_identical_names_are_not_one_edit():
    assert _one_edit("beijing", "beijing") is False


def test_single_substitution_counts_as_one_edit():
    assert _one_edit("beijing", "beajing") is True


def test_two_substitutions_do_not_count():
    assert _one_edit("beijing", "beajmng") is False


def test_single_insertion_counts_as_one_edit():
    assert _one_edit("beijing", "beijings") is True


def test_two_insertions_do_not_count():
    assert _one_edit("beijing", "beijingss") is False


def test_different_content_of_similar_length_is_not_one_edit():
    assert _one_edit("beijing", "shanghai") is False


def test_empty_strings_are_not_one_edit():
    assert _one_edit("", "") is False
