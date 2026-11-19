"""2026-11-18 nightly coverage for the vendor live-photo parsers.

The 2026-11-18 blind-spot scan found that **no** test file references
``app/service/live_photo/android.py``, ``apple.py`` or ``vivo.py``.  These
parsers decide whether two files on disk form a live-photo pair, so a
mismatch in the stem they return silently disables live-photo detection for
that vendor.

The tests pin down:

* which extensions each vendor claims;
* that unsupported extensions return ``None`` instead of a bogus stem;
* that the Apple parser strips ``.heic`` / ``.MOV`` case-insensitively
  (Linux/NAS tooling frequently lower-cases the extension);
* that the Android / vivo parsers strip the image and the video extension
  so both sides of a pair end up with the same stem.
"""

from __future__ import annotations

import pytest

from app.service.live_photo.android import AndroidLivePhotoParser
from app.service.live_photo.apple import AppleLivePhotoParser
from app.service.live_photo.vivo import VivoLivePhotoParser


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.mark.parametrize(
    ("parser", "name", "supported"),
    [
        (AppleLivePhotoParser(), "a.heic", True),
        (AppleLivePhotoParser(), "a.HEIC", True),
        (AppleLivePhotoParser(), "a.mov", True),
        (AppleLivePhotoParser(), "a.MOV", True),
        # NOTE: ``parse`` understands .mp4 but ``is_supported`` does not claim it;'
        # the Apple live-photo pair is always .heic + .MOV. Pinned as-is.
        (AppleLivePhotoParser(), "a.mp4", False),
        (AppleLivePhotoParser(), "a.jpg", False),
        (AndroidLivePhotoParser(), "a.jpg", True),
        (AndroidLivePhotoParser(), "a.JPEG", True),
        (AndroidLivePhotoParser(), "a.mp4", True),
        (AndroidLivePhotoParser(), "a.mov", False),
        (AndroidLivePhotoParser(), "a.heic", False),
        (VivoLivePhotoParser(), "a.jpg", True),
        (VivoLivePhotoParser(), "a.jpeg", True),
        (VivoLivePhotoParser(), "a.mp4", True),
        (VivoLivePhotoParser(), "a.mov", True),
        (VivoLivePhotoParser(), "a.heic", False),
    ],
)
def test_is_supported_only_claims_the_vendor_extensions(parser, name, supported):
    assert parser.is_supported(name) is supported

def test_apple_parses_a_heic_image_to_its_stem():
    assert AppleLivePhotoParser().parse("/photos/IMG_0001.HEIC") == "/photos/IMG_0001"


def test_apple_parses_a_mov_clip_to_its_stem():
    assert AppleLivePhotoParser().parse("/photos/IMG_0001.mov") == "/photos/IMG_0001"


def test_apple_returns_none_for_an_unsupported_extension():
    assert AppleLivePhotoParser().parse("/photos/IMG_0001.jpg") is None


def test_android_parses_the_image_and_the_clip_to_the_same_stem():
    parser = AndroidLivePhotoParser()

    assert parser.parse("/photos/IMG_0002.jpg") == "/photos/IMG_0002"
    assert parser.parse("/photos/IMG_0002.mp4") == "/photos/IMG_0002"


def test_android_returns_none_for_an_unsupported_extension():
    assert AndroidLivePhotoParser().parse("/photos/IMG_0002.heic") is None


def test_vivo_parses_the_image_and_the_clip_to_the_same_stem():
    parser = VivoLivePhotoParser()

    assert parser.parse("/photos/IMG_0003.jpeg") == "/photos/IMG_0003"
    assert parser.parse("/photos/IMG_0003.mov") == "/photos/IMG_0003"


def test_vivo_returns_none_for_an_unsupported_extension():
    assert VivoLivePhotoParser().parse("/photos/IMG_0003.heic") is None


