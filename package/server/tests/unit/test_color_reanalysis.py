"""Upgrade backfill updates old colors without repeatedly retrying bad files."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from PIL import Image
from datetime import datetime, timedelta, timezone
import pytest

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.photo_color import PhotoColor
from app.db.models.user import User
from app.service.jobs import color_reanalysis
from app.utils.color import CURRENT_COLOR_ANALYSIS_VERSION


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_upgrade_reanalyzes_available_photo_and_defers_missing_file(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'photos.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    make_session = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(color_reanalysis, 'SessionLocal', make_session)

    image_path = tmp_path / 'photo.png'
    Image.new('RGB', (20, 20), (220, 30, 30)).save(image_path)
    with make_session() as db:
        user = User(username='color-upgrade', email='color@example.com', hashed_password='unused')
        db.add(user)
        db.flush()
        photos = [
            Photo(filename='photo.png', file_path=str(image_path), file_type=FileType.image, owner_id=user.id),
            Photo(filename='missing.png', file_path=str(tmp_path / 'missing.png'), file_type=FileType.image, owner_id=user.id),
        ]
        db.add_all(photos)
        db.flush()
        for photo in photos:
            db.add(PhotoColor(photo_id=photo.id, dominant_colors=[{'hex': '#333333', 'ratio': 0.1}],
                              brightness=0.03, saturation=0, emotion_hint='muted', analysis_version=1))
        db.commit()
        photo_ids = [photo.id for photo in photos]

    monkeypatch.setattr(color_reanalysis.storage, 'get_available_photo_path',
                        lambda _owner, photo_id, path: path if photo_id == photo_ids[0] else None)
    try:
        assert color_reanalysis.reanalyze_color_batch() == {'processed': 1, 'failed': 1}
        with make_session() as db:
            refreshed = db.query(PhotoColor).filter(PhotoColor.photo_id == photo_ids[0]).one()
            missing = db.query(PhotoColor).filter(PhotoColor.photo_id == photo_ids[1]).one()
            assert refreshed.analysis_version == CURRENT_COLOR_ANALYSIS_VERSION
            assert refreshed.emotion_hint == 'vibrant'
            assert missing.analysis_version == 1
            assert missing.analysis_attempted_at is not None
        assert color_reanalysis.reanalyze_color_batch() == {'processed': 0, 'failed': 0}
        with make_session() as db:
            missing = db.query(PhotoColor).filter(PhotoColor.photo_id == photo_ids[1]).one()
            missing.analysis_attempted_at = datetime.now(timezone.utc) - timedelta(days=2)
            db.commit()
        monkeypatch.setattr(color_reanalysis.storage, 'get_available_photo_path',
                            lambda _owner, _photo_id, _path: str(image_path))
        assert color_reanalysis.reanalyze_color_batch() == {'processed': 1, 'failed': 0}
    finally:
        engine.dispose()
