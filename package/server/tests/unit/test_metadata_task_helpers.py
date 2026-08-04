from datetime import datetime
from types import SimpleNamespace

import pytest

from app.db.models.photo import ImageType
from app.service.tasks import metadata


pytestmark = pytest.mark.smoke


@pytest.mark.parametrize(
    ("filename", "width", "height", "exif_data", "expected"),
    [
        ("Screenshot_001.png", 800, 600, {}, ImageType.SCREENSHOT),
        ("camera.jpg", 4000, 3000, {"Make": "Canon"}, ImageType.CAMERA),
        ("plain.jpg", 800, 600, {}, ImageType.OTHER),
    ],
)
def test_determine_image_type_uses_filename_exif_then_default(
    filename, width, height, exif_data, expected
):
    assert metadata.determine_image_type(filename, width, height, exif_data) == expected


def test_determine_image_type_recognizes_common_screen_dimensions():
    assert metadata.determine_image_type("photo.jpg", 1170, 2532, {}) == ImageType.SCREENSHOT


def test_haversine_distance_is_zero_for_identical_coordinates():
    assert metadata.haversine_distance(30.5, 114.3, 30.5, 114.3) == 0


def test_rebuild_metadata_cpu_job_returns_empty_metadata_for_missing_file():
    result = metadata.rebuild_metadata_cpu_job('missing.jpg', 'photo-1')

    # extract_metadata currently converts an unreadable file into an empty
    # metadata result; preserve that worker-level contract here.
    assert result['success'] is True
    assert result['meta']['exif_info'] is None
    assert result['meta']['width'] is None
