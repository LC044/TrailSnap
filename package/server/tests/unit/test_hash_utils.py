"""Tests for chunked synchronous and asynchronous file hashing."""
import hashlib
import pytest
from app.utils.hash import calculate_file_md5, calculate_file_md5_async

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]

def test_calculate_file_md5_reads_multiple_chunks(tmp_path):
    payload = b"trail-snap" * 100
    path = tmp_path / "photo.bin"
    path.write_bytes(payload)
    assert calculate_file_md5(str(path), chunk_size=7) == hashlib.md5(payload).hexdigest()

def test_calculate_file_md5_returns_empty_for_missing_file(tmp_path):
    assert calculate_file_md5(str(tmp_path / "missing.bin")) == ""

@pytest.mark.asyncio
async def test_calculate_file_md5_async_matches_sync_result(tmp_path):
    path = tmp_path / "photo.bin"
    path.write_bytes(b"async hash")
    assert await calculate_file_md5_async(str(path), chunk_size=2) == calculate_file_md5(str(path), 2)
