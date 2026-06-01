import asyncio
import unittest
import uuid
from unittest.mock import ANY, patch

from starlette.responses import FileResponse

from app.api import media


class _FakePhoto:
    def __init__(self, photo_id):
        self.id = photo_id
        self.owner_id = uuid.uuid4()
        self.file_path = "/app/SynologyPhotos/rowankid/IMG_0001.HEIC"


class _FakeQuery:
    def __init__(self, photo):
        self.photo = photo

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.photo


class _FakeDb:
    def __init__(self, photo):
        self.photo = photo

    def query(self, _model):
        return _FakeQuery(self.photo)


class MediaFileTest(unittest.TestCase):
    def test_heic_file_endpoint_serves_medium_preview(self):
        photo_id = uuid.uuid4()
        photo = _FakePhoto(photo_id)
        db = _FakeDb(photo)
        preview_path = "/app/data/thumbnails/aa/bb/preview.webp"

        with (
            patch.object(media, "_get_thumbnail_path", return_value=preview_path) as get_thumbnail_path,
            patch.object(media.os.path, "exists", return_value=True),
            patch.object(media.os.path, "getsize", return_value=123),
        ):
            response = asyncio.run(media.get_media_file(photo_id, request=None, range=None, db=db))

        self.assertIsInstance(response, FileResponse)
        self.assertEqual(response.path, preview_path)
        self.assertEqual(response.media_type, "image/webp")
        get_thumbnail_path.assert_called_once_with(photo.owner_id, photo_id, ANY, "medium")


if __name__ == "__main__":
    unittest.main()
