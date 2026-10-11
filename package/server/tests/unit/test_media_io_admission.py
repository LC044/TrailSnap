"""Media computation must leave volume admission available to AI readers."""
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from types import SimpleNamespace

import pytest
from PIL import Image

from app.core.config_manager import ImageSettings
from app.service import disk_budget as budget_module, storage
from app.service.tasks import metadata
from app.db.models.photo import FileType
from app.utils.hash import calculate_file_md5

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.mark.parametrize('format', ['JPEG', 'PNG', 'WEBP', 'TIFF'])
def test_lazy_image_read_and_thumbnail_roundtrip(tmp_path, monkeypatch, format):
    budget = budget_module.DiskBudget(limit=1)
    monkeypatch.setattr(budget_module, 'disk_budget', budget)
    monkeypatch.setattr(storage, '_get_storage_root', lambda *args: str(tmp_path))
    source = tmp_path / ('source.' + format.lower())
    Image.new('RGB', (100, 60), 'red').save(source, format=format)
    with budget_module.budgeted_open(source) as stream, Image.open(stream) as image:
        # Loading happens after Image.open(), with admission still enforced.
        image.load()
        assert image.size == (100, 60)
        preview = storage._save_thumbnails(image, uuid4(), uuid4(), config=ImageSettings())
    with Image.open(preview) as image:
        assert image.size == (100, 60)
        assert image.getpixel((0, 0))[0] > 240
    assert calculate_file_md5(str(source), 7) == hashlib.md5(source.read_bytes()).hexdigest()
    assert not any(budget._active.values())


def test_classification_reader_can_run_during_metadata_color_analysis(tmp_path, monkeypatch):
    budget = budget_module.DiskBudget(limit=1)
    monkeypatch.setattr(budget_module, 'disk_budget', budget)
    monkeypatch.setattr(storage, '_get_storage_root', lambda *args: str(tmp_path))
    source = tmp_path / 'source.png'
    Image.new('RGB', (100, 60), 'red').save(source)
    preview = tmp_path / 'preview.webp'
    Image.new('RGB', (100, 60), 'blue').save(preview)
    Image.new('RGB', (100, 60), 'red').save(tmp_path / 'preview-thumb.webp')
    monkeypatch.setattr(storage, 'get_preview_path', lambda *_: str(preview))
    computing, finish = threading.Event(), threading.Event()
    def color(image):
        image.load()
        computing.set()
        assert finish.wait(5)
        return {}
    monkeypatch.setattr(metadata, 'extract_color_info', color)
    def reader():
        # Match classification's file-read admission on the same volume.
        with budget.slot(source), open(source, 'rb') as stream:
            return stream.read()
    with ThreadPoolExecutor(max_workers=2) as pool:
        photo = SimpleNamespace(id=uuid4(), owner_id=uuid4(), file_type=FileType.image, file_path=str(source))
        job = pool.submit(metadata.update_photo_color_from_thumbnail, None, photo, colors={})
        try:
            assert computing.wait(5)
            assert pool.submit(reader).result(timeout=2) == source.read_bytes()
        finally:
            finish.set()
        job.result(timeout=5)


def test_read_failure_releases_admission(tmp_path, monkeypatch):
    budget = budget_module.DiskBudget(limit=1)
    monkeypatch.setattr(budget_module, 'disk_budget', budget)
    source = tmp_path / 'source.bin'
    source.write_bytes(b'x')
    with budget_module.budgeted_open(source) as stream:
        with pytest.raises(TypeError):
            stream.readinto(b'read-only')
        with budget.slot(source):
            pass
    assert not any(budget._active.values())


def test_thumbnail_encoding_leaves_previous_preview_readable(tmp_path, monkeypatch):
    budget = budget_module.DiskBudget(limit=1)
    monkeypatch.setattr(budget_module, 'disk_budget', budget)
    # storage also uses admission for atomic publication.
    monkeypatch.setattr(storage, 'disk_budget', budget)
    path = tmp_path / 'preview.webp'
    Image.new('RGB', (10, 10), 'red').save(path, 'WEBP')
    previous = path.read_bytes()
    save = Image.Image.save
    def encode(image, output, *args, **kwargs):
        assert not any(budget._active.values())
        with budget_module.budgeted_open(path) as source:
            assert source.read() == previous
        return save(image, output, *args, **kwargs)
    monkeypatch.setattr(Image.Image, 'save', encode)
    storage._save_webp(Image.new('RGB', (20, 20), 'blue'), str(path), quality=80, method=0)
    with Image.open(path) as image:
        assert image.size == (20, 20)
    assert not list(tmp_path.glob('*.tmp'))
