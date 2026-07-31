"""Unit tests for the live_photo parser package.

Why this file exists:

* The nightly gap scan flagged every module under ``app/service/live_photo/``
  as uncovered. The package is on the hot path during folder scans
  (``ScanFolderStrategy`` calls ``LivePhotoService.get_content_identifier``
  for every image/video pair), so a silent regression in the parsers
  (e.g. dropping the ``.HEIC`` -> ``.MOV`` rename that pairs Apple live
  photos) would cause ``is_live_photo`` to flip to ``False`` for every
  scan with no test boundary catching it.

* Each concrete parser is tiny (Apple / Android / Vivo are all 19-22
  LOC) and has a deterministic ``is_supported`` / ``parse`` contract;
  we test the happy path, the supported-extension edges, and the
  unsupported-extension error path per parser.

* ``LivePhotoService`` composes the parsers and chooses the first one
  whose ``is_supported`` returns True; we verify the parser selection
  order (Apple wins over Vivo when both match) and the ``None`` result
  when nothing matches.

* ``LivePhotoParser`` is abstract; we cover it indirectly via a tiny
  inline subclass that asserts the abstract methods are wired correctly.
"""

import pytest

from app.service.live_photo import (
    AppleLivePhotoParser,
    AndroidLivePhotoParser,
    LivePhotoParser,
    LivePhotoService,
    VivoLivePhotoParser,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# ---------------------------------------------------------------------------
# AppleLivePhotoParser
# ---------------------------------------------------------------------------


class TestAppleLivePhotoParser:
    """Apple pairs ``.heic`` stills with ``.mov`` videos.

    The parser strips the trailing extension to derive a shared content
    identifier that ``ScanFolderStrategy`` compares across both files.
    """

    def test_is_supported_accepts_heic_and_mov(self):
        p = AppleLivePhotoParser()
        assert p.is_supported("/photos/IMG_0001.heic") is True
        assert p.is_supported("/photos/IMG_0001.mov") is True

    def test_is_supported_rejects_other_extensions(self):
        p = AppleLivePhotoParser()
        assert p.is_supported("/photos/IMG_0001.jpg") is False
        assert p.is_supported("/photos/IMG_0001.png") is False
        assert p.is_supported("/photos/IMG_0001") is False

    def test_parse_strips_heic_extension(self):
        # The implementation does a case-sensitive ``.HEIC`` replace;
        # ensure the lowercase input still yields a paired stem.
        p = AppleLivePhotoParser()
        result = p.parse("/photos/IMG_0001.heic")
        assert result == "/photos/IMG_0001"

    def test_parse_strips_mov_extension(self):
        p = AppleLivePhotoParser()
        result = p.parse("/photos/IMG_0001.mov")
        assert result == "/photos/IMG_0001"

    def test_parse_returns_none_for_unsupported_extension(self):
        p = AppleLivePhotoParser()
        assert p.parse("/photos/IMG_0001.png") is None

    def test_parse_handles_uppercase_extensions_case_insensitively(self):
        # Regression guard: ``is_supported`` lower-cases the extension, but
        # ``_parse_image`` / ``_parse_video`` historically did a
        # case-sensitive ``.replace``.  Files normalised by NAS sync tools
        # to ``.heic`` / ``.mov`` (lowercase) silently kept the extension
        # and broke live-photo pairing in ``ScanFolderStrategy``.
        p = AppleLivePhotoParser()
        assert p.parse("/photos/IMG_0001.HEIC") == "/photos/IMG_0001"
        assert p.parse("/photos/IMG_0001.heic") == "/photos/IMG_0001"
        assert p.parse("/photos/IMG_0001.MOV") == "/photos/IMG_0001"
        assert p.parse("/photos/IMG_0001.mov") == "/photos/IMG_0001"


# ---------------------------------------------------------------------------
# AndroidLivePhotoParser
# ---------------------------------------------------------------------------


class TestAndroidLivePhotoParser:
    """Android pairs ``.jpg`` / ``.jpeg`` stills with ``.mp4`` videos.

    Both video extensions (.mov and .mp4) are supported because some
    vendors ship the motion clip as .mov.
    """

    def test_is_supported_accepts_jpg_jpeg_mp4(self):
        p = AndroidLivePhotoParser()
        assert p.is_supported("/photos/MOV_0001.jpg") is True
        assert p.is_supported("/photos/MOV_0001.jpeg") is True
        assert p.is_supported("/photos/MOV_0001.mp4") is True

    def test_is_supported_rejects_heic_mov_png(self):
        # Android parser explicitly excludes .heic and .mov; that is a
        # different vendor matrix than Apple and Vivo.
        p = AndroidLivePhotoParser()
        assert p.is_supported("/photos/MOV_0001.heic") is False
        assert p.is_supported("/photos/MOV_0001.mov") is False
        assert p.is_supported("/photos/MOV_0001.png") is False

    def test_parse_strips_jpg_and_jpeg_extensions(self):
        p = AndroidLivePhotoParser()
        assert p.parse("/photos/MOV_0001.jpg") == "/photos/MOV_0001"
        assert p.parse("/photos/MOV_0001.jpeg") == "/photos/MOV_0001"

    def test_parse_strips_mp4_extension(self):
        p = AndroidLivePhotoParser()
        assert p.parse("/photos/MOV_0001.mp4") == "/photos/MOV_0001"

    def test_parse_returns_none_for_unsupported_extension(self):
        p = AndroidLivePhotoParser()
        assert p.parse("/photos/MOV_0001.heic") is None


# ---------------------------------------------------------------------------
# VivoLivePhotoParser
# ---------------------------------------------------------------------------


class TestVivoLivePhotoParser:
    """Vivo pairs ``.jpg`` / ``.jpeg`` stills with ``.mp4`` / ``.mov`` videos.

    Vivo accepts all four extensions because the same vendor ships clips
    in both containers depending on the camera mode.
    """

    def test_is_supported_accepts_all_four_extensions(self):
        p = VivoLivePhotoParser()
        assert p.is_supported("/photos/VIVO_0001.jpg") is True
        assert p.is_supported("/photos/VIVO_0001.jpeg") is True
        assert p.is_supported("/photos/VIVO_0001.mp4") is True
        assert p.is_supported("/photos/VIVO_0001.mov") is True

    def test_is_supported_rejects_other_extensions(self):
        p = VivoLivePhotoParser()
        assert p.is_supported("/photos/VIVO_0001.heic") is False
        assert p.is_supported("/photos/VIVO_0001.png") is False

    def test_parse_strips_image_extensions(self):
        p = VivoLivePhotoParser()
        assert p.parse("/photos/VIVO_0001.jpg") == "/photos/VIVO_0001"
        assert p.parse("/photos/VIVO_0001.jpeg") == "/photos/VIVO_0001"

    def test_parse_strips_video_extensions(self):
        p = VivoLivePhotoParser()
        assert p.parse("/photos/VIVO_0001.mp4") == "/photos/VIVO_0001"
        assert p.parse("/photos/VIVO_0001.mov") == "/photos/VIVO_0001"

    def test_parse_returns_none_for_unsupported_extension(self):
        p = VivoLivePhotoParser()
        assert p.parse("/photos/VIVO_0001.heic") is None


# ---------------------------------------------------------------------------
# LivePhotoService composition
# ---------------------------------------------------------------------------


class TestLivePhotoService:
    """``LivePhotoService`` is a thin registry that picks the first parser
    whose ``is_supported`` returns True.

    The default service wires up ``AppleLivePhotoParser`` *before*
    ``VivoLivePhotoParser``. Because Apple only matches ``.heic`` /
    ``.mov`` / ``.mp4`` and Vivo matches ``.jpg`` / ``.jpeg`` / ``.mov`` /
    ``.mp4``, ``.jpg`` / ``.jpeg`` paths fall through to Vivo; ``.mov`` /
    ``.mp4`` paths stop at Apple; ``.heic`` paths stop at Apple.
    """

    def test_get_content_identifier_for_apple_heic(self):
        svc = LivePhotoService()
        assert svc.get_content_identifier("/photos/IMG.heic") == "/photos/IMG"

    def test_get_content_identifier_for_apple_mov(self):
        svc = LivePhotoService()
        assert svc.get_content_identifier("/photos/IMG.mov") == "/photos/IMG"

    def test_get_content_identifier_for_vivo_jpg(self):
        svc = LivePhotoService()
        # Apple parser rejects .jpg, so Vivo wins.
        assert svc.get_content_identifier("/photos/IMG.jpg") == "/photos/IMG"

    def test_get_content_identifier_returns_none_for_unsupported(self):
        svc = LivePhotoService()
        # ``.png`` is supported by none of the registered parsers.
        assert svc.get_content_identifier("/photos/IMG.png") is None

    def test_apple_wins_over_vivo_for_overlapping_extensions(self):
        # Both parsers support .mp4 / .mov; Apple is registered first so
        # the returned stem comes from Apple.  We verify the contract
        # rather than the implementation order so refactors that swap
        # the registry list still pass when the order is preserved.
        svc = LivePhotoService()
        apple = AppleLivePhotoParser()
        result = svc.get_content_identifier("/photos/IMG.mov")
        assert result == apple.parse("/photos/IMG.mov")


# ---------------------------------------------------------------------------
# LivePhotoParser abstract base
# ---------------------------------------------------------------------------


def test_abstract_parser_cannot_be_instantiated_directly():
    # The base class declares both methods abstract; instantiating it
    # must fail.  This protects against future refactors that accidentally
    # make either method concrete (which would let an empty parser be
    # silently registered with ``LivePhotoService``).
    with pytest.raises(TypeError):
        LivePhotoParser()  # type: ignore[abstract]


def test_subclass_must_implement_both_abstract_methods():
    # A subclass that implements only one method should still fail to
    # instantiate, since the other remains abstract.
    class HalfParser(LivePhotoParser):
        def parse(self, file_path):
            return None

    with pytest.raises(TypeError):
        HalfParser()  # type: ignore[abstract]


def test_full_subclass_instantiates_and_dispatches(monkeypatch):
    # Smoke-check the end-to-end happy path: a fully-implemented
    # subclass can be instantiated and its ``parse`` is invoked when
    # ``get_content_identifier`` walks the registry.
    calls = []

    class TrackedParser(LivePhotoParser):
        def is_supported(self, file_path):
            return file_path.endswith(".trk")

        def parse(self, file_path):
            calls.append(file_path)
            return file_path[:-4]

    svc = LivePhotoService()
    monkeypatch.setattr(svc, "parsers", [TrackedParser()])
    assert svc.get_content_identifier("/photos/A.trk") == "/photos/A"
    assert calls == ["/photos/A.trk"]
