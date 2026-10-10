import hashlib
import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile

from app.api import media

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_verified_upload_preserves_every_byte(tmp_path):
    original = bytes(range(256)) * 1001
    chunks = tmp_path / 'chunks'
    chunks.mkdir()
    parts = [original[:12345], original[12345:]]
    for index, data in enumerate(parts):
        (chunks / str(index)).write_bytes(data)
    target = tmp_path / 'original.HEIC'
    with patch.object(media.storage, 'prepare_upload_path', return_value=str(target)), patch.object(media.storage, 'validate_target_path'):
        media._finalize_chunk_upload(str(chunks), [0, 1], target.name, uuid4(), None, MagicMock(),
                                     len(original), 2, hashlib.sha256(original).hexdigest())
    assert target.read_bytes() == original
    assert not chunks.exists()


@pytest.mark.parametrize('indices,size,count,digest', [
    ([0, 2], 6, 2, None), ([0, 1], 6, 3, None),
    ([0, 1], 7, 2, None), ([0, 1], 6, 2, '0' * 64),
])
def test_incomplete_or_corrupt_upload_never_committed(tmp_path, indices, size, count, digest):
    chunks = tmp_path / 'chunks'
    chunks.mkdir()
    for index in indices:
        (chunks / str(index)).write_bytes(b'abc')
    target = tmp_path / 'original.mp4'
    with patch.object(media.storage, 'prepare_upload_path', return_value=str(target)), patch.object(media.storage, 'validate_target_path'), pytest.raises(ValueError):
        media._finalize_chunk_upload(str(chunks), indices, target.name, uuid4(), None, MagicMock(), size, count, digest)
    assert not target.exists()
    assert not list(tmp_path.glob('*.uploading'))


@pytest.mark.asyncio
async def test_bad_chunk_retry_keeps_previous_good_chunk(tmp_path):
    (tmp_path / '0').write_bytes(b'good')
    with patch.object(media, '_chunk_dir', return_value=str(tmp_path)), pytest.raises(HTTPException) as error:
        await media.upload_chunk(uuid4(), 0, UploadFile(file=io.BytesIO(b'bad')), MagicMock(), SimpleNamespace(id=uuid4()), hashlib.sha256(b'good').hexdigest())
    assert error.value.status_code == 400
    assert (tmp_path / '0').read_bytes() == b'good'
    assert sorted(path.name for path in tmp_path.iterdir()) == ['0']


@pytest.mark.asyncio
async def test_chunk_upload_accepts_nonsequential_arrival(tmp_path):
    data = b'\x00\xfforiginal chunk bytes'
    with patch.object(media, '_chunk_dir', return_value=str(tmp_path)):
        await media.upload_chunk(uuid4(), 2, UploadFile(file=io.BytesIO(data)), MagicMock(), SimpleNamespace(id=uuid4()), hashlib.sha256(data).hexdigest())
    assert (tmp_path / '2').read_bytes() == data


@pytest.mark.parametrize('digest', [hashlib.md5(b'abcdef').hexdigest(), '0' * 32])
def test_mobile_md5_checked_during_chunk_merge(tmp_path, digest):
    chunks = tmp_path / 'chunks'
    chunks.mkdir()
    (chunks / '0').write_bytes(b'abc')
    (chunks / '1').write_bytes(b'def')
    target = tmp_path / 'phone.mp4'
    with patch.object(media.storage, 'prepare_upload_path', return_value=str(target)), patch.object(media.storage, 'validate_target_path'):
        if digest == '0' * 32:
            with pytest.raises(ValueError, match='MD5'):
                media._finalize_chunk_upload(str(chunks), [0, 1], target.name, uuid4(), None, MagicMock(), 6, 2, None, digest)
            assert not target.exists()
        else:
            media._finalize_chunk_upload(str(chunks), [0, 1], target.name, uuid4(), None, MagicMock(), 6, 2, None, digest)
            assert target.read_bytes() == b'abcdef'


@pytest.mark.asyncio
async def test_resume_status_reports_only_committed_chunks_in_user_session(tmp_path):
    (tmp_path / '0').write_bytes(b'first')
    (tmp_path / '1.uploading').write_bytes(b'partial')
    with patch.object(media, '_chunk_dir', return_value=str(tmp_path)):
        result = await media.get_upload_status(uuid4(), MagicMock(), SimpleNamespace(id=uuid4()))
    assert result.data == {'chunks': {0: 5}}


def test_upload_acknowledgement_does_not_decode_media(tmp_path):
    from app.crud import photo as crud_photo
    original = tmp_path / 'phone.jpg'
    original.write_bytes(b'original')
    db = MagicMock()
    with patch.object(crud_photo.storage, 'generate_thumbnail') as thumbnail, \
         patch.object(crud_photo.storage, 'get_image_dimensions') as dimensions, \
         patch.object(crud_photo, 'extract_metadata') as metadata, \
         patch.object(crud_photo, 'create_photo', return_value=SimpleNamespace(id=uuid4())):
        crud_photo.save_and_create_photo(db, str(original), original.name, None, uuid4())
    thumbnail.assert_not_called()
    dimensions.assert_not_called()
    metadata.assert_not_called()


def test_simple_upload_wrong_digest_never_publishes_partial_original(tmp_path):
    target = tmp_path / 'phone.jpg'
    with patch.object(media.storage, 'prepare_upload_path', return_value=str(target)), patch.object(media.storage, 'validate_target_path'):
        with pytest.raises(ValueError, match='MD5'):
            media.storage.save_upload_file(UploadFile(file=io.BytesIO(b'original'), filename='phone.jpg'), uuid4(), uuid4(), expected_md5='0' * 32)
    assert not target.exists()
    assert not list(tmp_path.glob('*.uploading'))
