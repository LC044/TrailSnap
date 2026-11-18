"""2026-11-18 nightly coverage for the pure helpers of ``app/service/similar_faces.py``.

No test file referenced ``app/service/similar_faces.py``.  Two of its helpers
guard the "find similar faces and assign them" flow, and both are security
relevant:

* ``_verify`` decodes the short-lived review/undo token and must reject a
  token that was issued for another owner or for another purpose;
* ``_valid_rect`` decides whether a stored face box can be used at all.

``_fingerprint`` is the optimistic-concurrency marker: it must change when
the identity, the confidence or the box of a face changes.
"""

from __future__ import annotations

import math
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.service import similar_faces


pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def test_a_well_formed_rect_is_valid():
    assert similar_faces._valid_rect([0.1, 0.2, 0.5, 0.6]) is True


@pytest.mark.parametrize(
    "rect",
    [
        None,
        "not-a-list",
        [0.1, 0.2, 0.5],
        [0.1, 0.2, 0.5, 0.6, 0.7],
        [0.5, 0.2, 0.1, 0.6],
        [0.1, 0.6, 0.5, 0.2],
        [0.1, 0.2, 0.5, 0.6, 1],
        [-0.1, 0.2, 0.5, 0.6],
        [0.1, 0.2, 0.5, 1.4],
        [0.1, 0.2, 0.5, math.inf],
        [0.1, 0.2, 0.5, math.nan],
        ["a", "b", "c", "d"],
    ],
)
def test_a_malformed_rect_is_rejected(rect):
    assert similar_faces._valid_rect(rect) is False


def test_the_fingerprint_is_stable_for_the_same_face_state():
    rect = [0.1, 0.2, 0.5, 0.6]

    assert similar_faces._fingerprint("id-1", 0.9, rect) == similar_faces._fingerprint("id-1", 0.9, rect)


def test_the_fingerprint_changes_with_the_identity():
    rect = [0.1, 0.2, 0.5, 0.6]

    assert similar_faces._fingerprint("id-1", 0.9, rect) != similar_faces._fingerprint("id-2", 0.9, rect)


def test_the_fingerprint_changes_with_the_confidence():
    rect = [0.1, 0.2, 0.5, 0.6]

    assert similar_faces._fingerprint("id-1", 0.9, rect) != similar_faces._fingerprint("id-1", 0.8, rect)


def test_the_fingerprint_changes_with_the_box():
    assert similar_faces._fingerprint("id-1", 0.9, [0.1, 0.2, 0.5, 0.6]) != similar_faces._fingerprint(
        "id-1", 0.9, [0.1, 0.2, 0.5, 0.7])


def test_a_freshly_signed_token_verifies_for_its_owner():
    owner = uuid4()
    token = similar_faces._sign({"face": 1}, owner, "face-review", 5)

    payload = similar_faces._verify(token, owner, "face-review")

    assert payload["face"] == 1
    assert payload["owner"] == str(owner)


def test_a_token_of_another_owner_is_rejected():
    token = similar_faces._sign({"face": 1}, uuid4(), "face-review", 5)

    with pytest.raises(HTTPException) as excinfo:
        similar_faces._verify(token, uuid4(), "face-review")

    assert excinfo.value.status_code == 409


def test_a_token_for_another_purpose_is_rejected():
    owner = uuid4()
    token = similar_faces._sign({"face": 1}, owner, "face-undo", 5)

    with pytest.raises(HTTPException) as excinfo:
        similar_faces._verify(token, owner, "face-review")

    assert excinfo.value.status_code == 409


def test_a_garbage_token_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        similar_faces._verify("not-a-token", uuid4(), "face-review")

    assert excinfo.value.status_code == 409


def test_the_distance_thresholds_are_ordered_from_strict_to_broad():
    assert similar_faces.DISTANCES["strict"] < similar_faces.DISTANCES["balanced"] < similar_faces.DISTANCES["broad"]
    assert similar_faces.LOW_DISTANCES["strict"] > similar_faces.LOW_DISTANCES["balanced"] > similar_faces.LOW_DISTANCES["broad"]
