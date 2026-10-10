import hashlib
import io
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.api import media
from app.db.models.photo import FileType

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def photo_at(tmp_path):
    path = tmp_path / 'stored.jpg'
    path.write_bytes(b'image')
    return SimpleNamespace(id=uuid4(), owner_id=uuid4(), filename=path.name, file_path=str(path),
                           file_type=FileType.live_photo, size=5, upload_time=datetime.now(),
                           photo_time=None, md5=hashlib.md5(b'image').hexdigest())


def test_live_preflight_requires_exact_video_bytes(tmp_path):
    photo = photo_at(tmp_path)
    video = tmp_path / 'stored.mp4'
    video.write_bytes(b'old-video')
    lookup = lambda db, user, digest: photo if digest == photo.md5 else None
    with patch.object(media, '_existing_content_photo', side_effect=lookup):
        image, clip, complete = media._live_content_state(MagicMock(), photo.owner_id, photo.md5, hashlib.md5(b'old-video').hexdigest())
        assert image is photo and clip == str(video) and complete
        _, clip, complete = media._live_content_state(MagicMock(), photo.owner_id, photo.md5, hashlib.md5(b'new-video').hexdigest())
        assert clip is None and not complete


@pytest.mark.asyncio
@pytest.mark.parametrize('with_video', [True, False])
async def test_existing_image_never_needs_image_upload(tmp_path, with_video):
    photo = photo_at(tmp_path)
    data = b'video'
    stored = tmp_path / 'standalone.mp4'
    stored.write_bytes(data)
    video = UploadFile(file=io.BytesIO(data), filename='phone.mp4') if with_video else None
    db = MagicMock()
    captured = []
    def attach(db, image, upload, key, user):
        captured.append((image.id, upload.file.read(), upload.filename))
    with patch.object(media, '_live_content_state', return_value=(photo, None if with_video else str(stored), False)), \
         patch.object(media, '_attach_live_photo_video', side_effect=attach), \
         patch.object(media, 'upload_photo_generic') as upload_image:
        response = await media.upload_missing_live_content(
            image_md5=photo.md5, video_md5=hashlib.md5(data).hexdigest(), video_name='phone.mp4',
            backup_key='new-phone-key', companion_backup_key=None, folder=None, source_photo_time=None,
            image=None, video=video, db=db, current_user=SimpleNamespace(id=photo.owner_id),
        )
    assert response.code == 0
    assert captured == [(photo.id, data, 'stored.mp4')]
    upload_image.assert_not_called()


@pytest.mark.asyncio
async def test_complete_live_pair_needs_no_uploaded_files(tmp_path):
    photo = photo_at(tmp_path)
    with patch.object(media, '_live_content_state', return_value=(photo, 'stored.mp4', True)), \
         patch.object(media, '_attach_live_photo_video') as attach:
        result = await media.upload_missing_live_content(
            image_md5=photo.md5, video_md5=hashlib.md5(b'video').hexdigest(), video_name='phone.mp4',
            backup_key='alias', companion_backup_key=None, folder=None, source_photo_time=None,
            image=None, video=None, db=MagicMock(), current_user=SimpleNamespace(id=photo.owner_id),
        )
    assert result.code == 0
    attach.assert_not_called()


@pytest.mark.asyncio
async def test_changed_or_missing_parts_require_retry(tmp_path):
    photo = photo_at(tmp_path)
    with patch.object(media, '_live_content_state', return_value=(photo, None, False)), pytest.raises(HTTPException) as error:
        await media.upload_missing_live_content(
            image_md5=photo.md5, video_md5=hashlib.md5(b'video').hexdigest(), video_name='phone.mp4',
            backup_key='alias', companion_backup_key=None, folder=None, source_photo_time=None,
            image=None, video=None, db=MagicMock(), current_user=SimpleNamespace(id=photo.owner_id),
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('upload_video', [True, False])
async def test_new_image_can_reuse_a_server_video(tmp_path, upload_video):
    photo = photo_at(tmp_path)
    clip = tmp_path / 'existing.mp4'
    clip.write_bytes(b'video')
    image = UploadFile(file=io.BytesIO(b'image'), filename='phone.jpg')
    video = UploadFile(file=io.BytesIO(b'video'), filename='phone.mp4') if upload_video else None
    with patch.object(media, '_live_content_state', return_value=(None, None if upload_video else str(clip), False)), \
         patch.object(media, 'upload_photo_generic', new_callable=AsyncMock, return_value=photo) as save_image, \
         patch.object(media, '_attach_live_photo_video') as attach:
        result = await media.upload_missing_live_content(
            image_md5=photo.md5, video_md5=hashlib.md5(b'video').hexdigest(), video_name='phone.mp4',
            backup_key='alias', companion_backup_key=None, folder=None, source_photo_time=None,
            image=image, video=video, db=MagicMock(), current_user=SimpleNamespace(id=photo.owner_id),
        )
    assert result.code == 0
    assert save_image.await_args.kwargs['file'] is image
    assert save_image.await_args.kwargs['live_photo_video'] is None
    assert attach.call_count == 1


@pytest.mark.asyncio
async def test_corrupt_video_never_overwrites_existing_content(tmp_path):
    photo = photo_at(tmp_path)
    with patch.object(media, '_live_content_state', return_value=(photo, None, False)), \
         patch.object(media, '_attach_live_photo_video') as attach, pytest.raises(HTTPException) as error:
        await media.upload_missing_live_content(
            image_md5=photo.md5, video_md5=hashlib.md5(b'video').hexdigest(), video_name='phone.mp4',
            backup_key='alias', companion_backup_key=None, folder=None, source_photo_time=None,
            image=None, video=UploadFile(file=io.BytesIO(b'corrupt'), filename='phone.mp4'),
            db=MagicMock(), current_user=SimpleNamespace(id=photo.owner_id),
        )
    assert error.value.status_code == 400
    attach.assert_not_called()
