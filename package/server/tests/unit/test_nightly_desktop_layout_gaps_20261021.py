"""Nightly gap tests: ``app/utils/desktop_layout.py``.

``test_portable_library.py::test_installer_and_zip_share_layout_without_overwriting_instance_data``
already drives ``stage_program``'s happy path, but it never triggers a repair.
That leaves the WebView2 validation, the staleness checks inside ``intact()``
and -- most importantly -- the guards that refuse to repair a program
directory containing a user's library uncovered (18 missed statements).

Those guards are the highest-risk code in the module: they are the last thing
standing between a content-hash drift and deleting a real photo library, and
nothing exercised them.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils.desktop_layout import stage_program


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _program_source(tmp_path: Path) -> Path:
    """A minimally complete program tree accepted by ``stage_program``."""
    source = tmp_path / "source"
    (source / "server").mkdir(parents=True)
    (source / "trailsnap-desktop.exe").write_bytes(b"shell__TAURI_BUNDLE_TYPE_VAR_UNK")
    (source / "server" / "trailsnap-server.exe").write_bytes(b"server")
    (source / "portable-launcher.exe").write_bytes(b"launcher")
    (source / "ai-extensions.json").write_text("{}")
    return source


def _stage(source: Path, root: Path, **kwargs) -> str:
    return stage_program(
        root,
        source,
        source / "server",
        source / "portable-launcher.exe",
        source / "ai-extensions.json",
        "1.0.0",
        "x86_64",
        **kwargs,
    )


class TestStageProgramValidation:
    def test_incomplete_webview_runtime_is_rejected(self, tmp_path):
        """A Fixed Version runtime without msedgewebview2.exe would install a
        package that never renders a window."""
        source = _program_source(tmp_path)
        webview = tmp_path / "webview"
        webview.mkdir()
        (webview / "readme.txt").write_text("incomplete")

        with pytest.raises(ValueError, match="WebView2 runtime is incomplete"):
            _stage(source, tmp_path / "zip", webview_runtime=webview)

    def test_complete_webview_runtime_is_staged(self, tmp_path):
        source = _program_source(tmp_path)
        webview = tmp_path / "webview"
        webview.mkdir()
        (webview / "msedgewebview2.exe").write_bytes(b"webview")

        build = _stage(source, tmp_path / "zip", webview_runtime=webview)
        staged = tmp_path / "zip" / "app" / build / "webview-runtime" / "msedgewebview2.exe"
        assert staged.read_bytes() == b"webview"

    def test_webview_runtime_changes_the_build_id(self, tmp_path):
        """The runtime is hashed into the build id, so swapping it must not
        resolve to an already-installed build directory."""
        source = _program_source(tmp_path)
        without = _stage(source, tmp_path / "zip")

        webview = tmp_path / "webview"
        webview.mkdir()
        (webview / "msedgewebview2.exe").write_bytes(b"webview")
        with_runtime = _stage(source, tmp_path / "zip2", webview_runtime=webview)

        assert with_runtime != without

    def test_missing_server_executable_is_rejected(self, tmp_path):
        """Refuse to build a package whose backend cannot start."""
        source = _program_source(tmp_path)
        (source / "server" / "trailsnap-server.exe").unlink()

        with pytest.raises(ValueError, match="安装包缺少完整后端"):
            _stage(source, tmp_path / "zip")


class TestStageProgramRepair:
    """Everything below forces ``intact()`` to return False so the repair
    branch runs. The declared inputs never change, so the build id is stable."""

    @staticmethod
    def _drift(root: Path, build: str) -> Path:
        target = root / "app" / build
        (target / "manifest.json").write_text("{not json")
        return target

    def test_manifest_drift_triggers_restage(self, tmp_path):
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        (root / "app" / build / "manifest.json").write_text(json.dumps({"schemaVersion": 99}))

        assert _stage(source, root) == build
        restored = json.loads((root / "app" / build / "manifest.json").read_text())
        assert restored["schemaVersion"] == 1
        assert restored["buildId"] == build

    def test_corrupt_manifest_is_treated_as_drift(self, tmp_path):
        """A truncated manifest raises ValueError inside ``intact()``; that must
        read as "needs repair", not as a hard failure."""
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        self._drift(root, build)

        assert _stage(source, root) == build
        assert (root / "app" / build / "server" / "trailsnap-server.exe").is_file()

    def test_unexpected_file_triggers_restage(self, tmp_path):
        """Unknown files in the program directory mean the install is not what
        we think it is; repair rebuilds from the declared inputs only."""
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        intruder = root / "app" / build / "server" / "stowaway.dll"
        intruder.write_bytes(b"unexpected")

        _stage(source, root)
        assert not intruder.exists()
        assert (root / "app" / build / "server" / "trailsnap-server.exe").is_file()

    def test_unexpected_directory_entry_triggers_restage(self, tmp_path):
        """Same check, but the intruder is a nested directory: ``rglob`` walks
        recursively, so a planted payload deep in the tree is still caught."""
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        nested = root / "app" / build / "server" / "plugins" / "rogue.dll"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"unexpected")

        _stage(source, root)
        assert not nested.exists()

    def test_modified_payload_triggers_restage(self, tmp_path):
        """Same manifest, tampered binary: the per-file hash check catches it."""
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        (root / "app" / build / "server" / "trailsnap-server.exe").write_bytes(b"tampered")

        assert _stage(source, root) == build
        assert (
            root / "app" / build / "server" / "trailsnap-server.exe"
        ).read_bytes() == b"server"

    def test_repair_refuses_when_program_dir_holds_library_json(self, tmp_path):
        """Repairing a program directory must never delete a user's library."""
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        self._drift(root, build)
        (root / "app" / build / "library.json").write_text("{}")

        with pytest.raises(ValueError, match="程序目录含图库数据"):
            _stage(source, root)

    def test_repair_refuses_when_program_dir_holds_sqlite(self, tmp_path):
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        self._drift(root, build)
        (root / "app" / build / "data").mkdir()
        (root / "app" / build / "data" / "trailsnap.sqlite").write_bytes(b"sqlite")

        with pytest.raises(ValueError, match="程序目录含图库数据"):
            _stage(source, root)

    def test_repair_refuses_when_library_lives_inside_program_dir(self, tmp_path):
        """instance.json points into app/<build>, so renaming that directory
        would move the live library out from under the running app."""
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        target = self._drift(root, build)
        (target / "userdata").mkdir()
        (root / "instance.json").write_text(
            json.dumps({"dataRoot": {"kind": "relative", "path": f"app/{build}/userdata"}})
        )

        with pytest.raises(ValueError, match="图库位于程序目录内"):
            _stage(source, root)

    def test_repair_allows_external_data_root(self, tmp_path):
        """The same descriptor pointing outside the program directory is fine."""
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        self._drift(root, build)
        library = tmp_path / "mylib"
        library.mkdir()
        (root / "instance.json").write_text(
            json.dumps({"dataRoot": {"kind": "absolute", "path": str(library)}})
        )

        assert _stage(source, root) == build

    def test_publish_failure_restores_previous_build(self, tmp_path):
        """If the atomic publish fails, the retired directory must be put back
        so a transient AV lock cannot leave the user with no program at all."""
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        target = self._drift(root, build)

        with patch(
            "app.utils.desktop_layout.publish_directory",
            side_effect=OSError("publish failed"),
        ):
            with pytest.raises(OSError, match="publish failed"):
                _stage(source, root)

        assert (target / "server" / "trailsnap-server.exe").is_file()
        assert not list((root / "app").glob(".repair-*"))
        assert not list((root / "app").glob(".install-*"))

    def test_repair_leaves_no_retired_directories(self, tmp_path):
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        self._drift(root, build)

        _stage(source, root)
        assert not list((root / "app").glob(".repair-*"))

    def test_repair_refuses_when_program_dir_is_a_link(self, tmp_path):
        """Never traverse a reparse point: ``target.rename`` on a link would
        move whatever it points at, not the build we validated."""
        source = _program_source(tmp_path)
        root = tmp_path / "zip"
        build = _stage(source, root)
        self._drift(root, build)

        original = Path.is_junction if hasattr(Path, "is_junction") else Path.is_symlink
        with patch.object(Path, "is_junction", lambda self: self.name == build, create=True):
            with pytest.raises(ValueError, match="已有程序目录含链接"):
                _stage(source, root)
        assert original is not None


class TestTauriBundleMarker:
    @pytest.mark.parametrize(
        "bundle_type",
        [
            b"UNK",
            b"NSS",
            b"WIX",
        ],
    )
    def test_bundle_type_is_format_metadata_not_a_separate_build(self, tmp_path, bundle_type):
        """NSIS patches the three-byte distribution marker, then restores UNK.
        Hashing it as UNK keeps the NSIS and plain-ZIP packages on one build id
        instead of publishing the same program twice."""
        source = _program_source(tmp_path)
        payload = b"shell__TAURI_BUNDLE_TYPE_VAR_" + bundle_type
        (source / "trailsnap-desktop.exe").write_bytes(payload)

        reference = _program_source(tmp_path / "ref")
        build = _stage(source, tmp_path / "zip")
        expected = _stage(reference, tmp_path / "refzip")

        assert build == expected

    @pytest.mark.parametrize("bundle_type", [b"UNK", b"NSS", b"WIX"])
    def test_staged_copy_is_byte_identical_to_the_source(self, tmp_path, bundle_type):
        """Only the digest is normalised. The copy itself must stay verbatim --
        rewriting it could invalidate a platform code signature."""
        source = _program_source(tmp_path)
        payload = b"shell__TAURI_BUNDLE_TYPE_VAR_" + bundle_type
        (source / "trailsnap-desktop.exe").write_bytes(payload)

        build = _stage(source, tmp_path / "zip")

        staged = (tmp_path / "zip" / "app" / build / "trailsnap-desktop.exe").read_bytes()
        assert staged == payload

    def test_unknown_marker_is_left_alone(self, tmp_path):
        """A marker value we do not recognise must not be folded into UNK --
        it may be real program content, and collapsing it would collide two
        genuinely different binaries onto one build id."""
        source = _program_source(tmp_path)
        (source / "trailsnap-desktop.exe").write_bytes(b"shell__TAURI_BUNDLE_TYPE_VAR_ZZZ")
        reference = _program_source(tmp_path / "ref")

        assert _stage(source, tmp_path / "zip") != _stage(reference, tmp_path / "refzip")

    def test_repeated_marker_is_left_alone(self, tmp_path):
        """``count(marker) == 1`` guards against rewriting a binary that merely
        mentions the token twice."""
        source = _program_source(tmp_path)
        (source / "trailsnap-desktop.exe").write_bytes(
            b"__TAURI_BUNDLE_TYPE_VAR_NSS__TAURI_BUNDLE_TYPE_VAR_NSS"
        )
        reference = _program_source(tmp_path / "ref")

        assert _stage(source, tmp_path / "zip") != _stage(reference, tmp_path / "refzip")
