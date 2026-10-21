"""Nightly coverage gap tests for ``app/utils/panorama.py`` (2026-10-21).

Targets the validation helpers in ``app.utils.panorama`` whose edge-case
branches remain uncovered by ``test_panorama.py`` (which mostly exercises the
API surface):

- ``validate_geometry`` rejects non-integer (bool) values, asymmetric 2:1 canvases,
  posePitch / initialPitch outside ``[-90, 90]``, poseRoll outside ``[-180, 180]``,
  and initialFov outside ``[1, 179]``.
- ``parse_gpano`` ignores XMP that does not declare an equirectangular projection.
- ``scaled_geometry`` rounds XMP coordinates against the live image dimensions.
- ``apply_detection`` writes ``panorama_detected`` even when ``panorama_override``
  is already set, leaves ``width``/``height`` untouched when ``data`` is None,
  and clears ``panorama_projection`` when detection is absent.
"""
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.smoke]


def _geom(width=800, height=400, **overrides):
    """Return a valid full equirectangular geometry payload."""
    payload = {
        "fullWidth": width,
        "fullHeight": height,
        "croppedWidth": width,
        "croppedHeight": height,
        "croppedX": 0,
        "croppedY": 0,
    }
    payload.update(overrides)
    return payload


def test_validate_geometry_rejects_bool_dimension():
    """``True``/``False`` sneak past ``str(value).isdigit()`` so must be caught."""
    from app.utils.panorama import validate_geometry

    with pytest.raises(ValueError, match="整数"):
        validate_geometry({**_geom(), "fullWidth": True}, 800, 400)

    with pytest.raises(ValueError, match="整数"):
        validate_geometry({**_geom(), "croppedX": False}, 800, 400)


def test_validate_geometry_rejects_non_integer_string_dimension():
    from app.utils.panorama import validate_geometry

    with pytest.raises(ValueError, match="整数"):
        validate_geometry({**_geom(), "fullHeight": "12.5"}, 800, 400)


def test_validate_geometry_rejects_asymmetric_two_to_one_canvas():
    """``fw == 2 * fh`` is strict; off-by-one is still rejected."""
    from app.utils.panorama import validate_geometry

    # fullHeight not exactly half of fullWidth
    with pytest.raises(ValueError, match="2:1"):
        validate_geometry({**_geom(fullWidth=800, fullHeight=399)}, 800, 399)


def test_validate_geometry_rejects_pitch_out_of_range():
    from app.utils.panorama import validate_geometry

    over = {**_geom(), "posePitch": 90.0001}
    with pytest.raises(ValueError, match="范围"):
        validate_geometry(over, 800, 400)

    under = {**_geom(), "initialPitch": -90.0001}
    with pytest.raises(ValueError, match="范围"):
        validate_geometry(under, 800, 400)


def test_validate_geometry_accepts_pitch_boundary_values():
    """Boundary values ``-90`` and ``90`` stay inside the inclusive range."""
    from app.utils.panorama import validate_geometry

    upper = validate_geometry({**_geom(), "posePitch": 90.0}, 800, 400)
    assert upper["posePitch"] == 90.0

    lower = validate_geometry({**_geom(), "initialPitch": -90.0}, 800, 400)
    assert lower["initialPitch"] == -90.0


def test_validate_geometry_rejects_roll_out_of_range():
    from app.utils.panorama import validate_geometry

    with pytest.raises(ValueError, match="横滚角"):
        validate_geometry({**_geom(), "poseRoll": -180.5}, 800, 400)

    with pytest.raises(ValueError, match="横滚角"):
        validate_geometry({**_geom(), "poseRoll": 180.5}, 800, 400)


def test_validate_geometry_rejects_initial_fov_out_of_range():
    from app.utils.panorama import validate_geometry

    with pytest.raises(ValueError, match="视野"):
        validate_geometry({**_geom(), "initialFov": 0.5}, 800, 400)

    with pytest.raises(ValueError, match="视野"):
        validate_geometry({**_geom(), "initialFov": 180.0}, 800, 400)


def test_validate_geometry_keeps_pose_heading_outside_pitch_branch():
    """``poseHeading`` is not pitch/roll/FoV — always passes through untouched."""
    from app.utils.panorama import validate_geometry

    out = validate_geometry({**_geom(), "poseHeading": 359.999}, 800, 400)
    assert out["poseHeading"] == pytest.approx(359.999)


def test_parse_gpano_ignores_non_equirectangular_projection():
    """cylindrical / mesh / cubic XMP must short-circuit out via ``return None``."""
    from app.utils.panorama import parse_gpano

    xmp = (
        b'<root xmlns:p="http://ns.google.com/photos/1.0/panorama/"'
        b' p:ProjectionType="cylindrical"'
        b' p:FullPanoWidthPixels="800"'
        b' p:FullPanoHeightPixels="400"'
        b' p:CroppedAreaImageWidthPixels="800"'
        b' p:CroppedAreaImageHeightPixels="400"'
        b' p:CroppedAreaLeftPixels="0"'
        b' p:CroppedAreaTopPixels="0"/>'
    )
    assert parse_gpano(xmp, 800, 400) is None


def test_parse_gpano_returns_none_when_projection_missing():
    from app.utils.panorama import parse_gpano

    xmp = (
        b'<root xmlns:p="http://ns.google.com/photos/1.0/panorama/"'
        b' p:FullPanoWidthPixels="800"'
        b' p:FullPanoHeightPixels="400"'
        b' p:CroppedAreaImageWidthPixels="800"'
        b' p:CroppedAreaImageHeightPixels="400"'
        b' p:CroppedAreaLeftPixels="0"'
        b' p:CroppedAreaTopPixels="0"/>'
    )
    assert parse_gpano(xmp, 800, 400) is None


def test_scaled_geometry_rounds_xmp_coordinates_to_image_size():
    """``scaled_geometry`` keeps angles as-is and rounds pixel dimensions."""
    from app.utils.panorama import scaled_geometry

    geometry = {
        "fullWidth": 800,
        "fullHeight": 400,
        "croppedWidth": 1600,
        "croppedHeight": 800,
        "croppedX": 400,
        "croppedY": 200,
        "poseHeading": 17.5,
        "posePitch": -8.25,
    }

    scaled = scaled_geometry(geometry, 800, 400)

    # Width-relative axes scale by 0.5x.
    assert scaled["fullWidth"] == 400
    assert scaled["croppedWidth"] == 800
    assert scaled["croppedX"] == 200
    # Height-relative axes scale by 0.5x.
    assert scaled["fullHeight"] == 200
    assert scaled["croppedHeight"] == 400
    assert scaled["croppedY"] == 100
    # Non-dimension keys survive untouched.
    assert scaled["poseHeading"] == 17.5
    assert scaled["posePitch"] == -8.25


def test_apply_detection_keeps_width_height_when_no_data():
    """Without detection, ``width``/``height`` are NOT overwritten."""
    from app.utils.panorama import apply_detection

    photo = SimpleNamespace(
        panorama_detected=None,
        panorama_override=None,
        width=800,
        height=400,
        panorama_metadata={"legacy": True},
        panorama_projection="equirectangular",
    )

    apply_detection(photo, None)

    assert photo.panorama_detected is None
    assert photo.width == 800 and photo.height == 400
    assert photo.panorama_metadata is None
    assert photo.panorama_projection is None


def test_apply_detection_overrides_dimensions_with_data():
    from app.utils.panorama import apply_detection

    photo = SimpleNamespace(
        panorama_detected=None,
        panorama_override=None,
        width=800,
        height=400,
        panorama_metadata=None,
        panorama_projection=None,
    )
    data = {
        "fullWidth": 800, "fullHeight": 400,
        "croppedWidth": 600, "croppedHeight": 250,
        "croppedX": 100, "croppedY": 50,
    }

    apply_detection(photo, data)

    assert photo.panorama_detected is data
    assert photo.width == 600 and photo.height == 250
    assert photo.panorama_metadata is data
    assert photo.panorama_projection == "equirectangular"


def test_apply_detection_preserves_user_override():
    """When ``panorama_override`` is set, automatic metadata must not stomp it."""
    from app.utils.panorama import apply_detection

    photo = SimpleNamespace(
        panorama_detected=None,
        panorama_override="ordinary",
        width=800,
        height=400,
        panorama_metadata="user-chosen",
        panorama_projection="equirectangular",
    )

    apply_detection(photo, {"croppedWidth": 600, "croppedHeight": 250})

    # Detection result always written to panorama_detected, but the user
    # override and the manually stored metadata remain untouched.
    assert photo.panorama_detected["croppedWidth"] == 600
    assert photo.panorama_override == "ordinary"
    assert photo.panorama_metadata == "user-chosen"
    assert photo.panorama_projection == "equirectangular"
