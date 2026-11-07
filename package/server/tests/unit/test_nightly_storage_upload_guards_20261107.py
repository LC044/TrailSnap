import io
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.service import storage

pytestmark = [pytest.mark.smoke, pytest.mark.module_storage]


def test_simple_upload_size_mismatch_never_publishes_partial_original(tmp_path):
    """A mismatched declared size must reject the upload before os.replace()."""
    target = tmp_path / "phone.jpg"
    upload = UploadFile(file=io.BytesIO(b"original"), filename="phone.jpg", size=999)

    with patch.object(storage, "prepare_upload_path", return_value=str(target)), \
         patch.object(storage, "validate_target_path"), \
         pytest.raises(ValueError, match="size"):
        storage.save_upload_file(upload, uuid4(), uuid4())

    assert not target.exists()
    assert not list(tmp_path.glob("*.uploading"))


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (0.0, [0.0]),
        (0.04, [0.0]),
        (0.2, [0.0, 0.01, 0.02, 0.05, 0.1]),
        (8.0, [0.0, 0.4, 0.8, 2.0, 4.0]),
    ],
)
def test_video_thumbnail_candidate_seconds_are_unique_and_in_bounds(duration, expected):
    assert storage._video_thumbnail_candidate_seconds(duration) == expected
