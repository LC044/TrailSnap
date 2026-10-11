"""Compare OCR persistence on isolated SQLite databases; no model inference."""
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
import app.db.models
from app.db.base import Base
from app.db.models.user import User
from app.db.models.photo import Photo, FileType
from app.db.models.ocr import OCR
from app.crud import ocr as crud
from app.schemas.ocr import OCRCreate


def trial(root, batch, round_number):
    engine = create_engine(f'sqlite:///{(root / f"{batch}-{round_number}.sqlite").as_posix()}')
    @event.listens_for(engine, 'connect')
    def configure(conn, _):
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=FULL')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False, autoflush=False) as db:
        owner = uuid4()
        db.add(User(id=owner, username=str(owner), settings={}))
        photos = [Photo(id=uuid4(), owner_id=owner, filename=f'{i}.jpg', file_path=f'/{i}.jpg',
                        file_type=FileType.image, processed_tasks={}) for i in range(10)]
        db.add_all(photos); db.commit()
        commits = []
        event.listen(engine, 'commit', lambda _: commits.append(True))
        started = time.perf_counter()
        for photo_index, photo in enumerate(photos):
            crud.delete_ocr_by_photo_id(db, photo.id, commit=not batch)
            for i in range(100):
                crud.create_ocr(db, OCRCreate(photo_id=photo.id, text=f'text {i}', text_score=.95, polygon=[]), commit=not batch)
            photo.processed_tasks = {'ocr': True}
            if not batch or (photo_index + 1) % 2 == 0:
                db.commit()
        elapsed = time.perf_counter() - started
        assert db.query(OCR).count() == 1000
        result = {'seconds': elapsed, 'commits': len(commits)}
    engine.dispose()
    return result


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='trailsnap-ai-benchmark-') as directory:
        root = Path(directory)
        results = {name: [trial(root, batch, i) for i in range(3)]
                   for name, batch in [('before', False), ('after', True)]}
        results['scope'] = '10 photos x 100 OCR regions, batches of 2 after optimization, SQLite WAL FULL, persistence only'
        results['speedup'] = statistics.median(r['seconds'] for r in results['before']) / statistics.median(r['seconds'] for r in results['after'])
        print(json.dumps(results, indent=2))
