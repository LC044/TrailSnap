import asyncio
from datetime import date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User
from app.schemas.chapter import ChapterDefinition, ChapterDiaryGenerate, ChapterMerge, ChapterSplit, ChapterUpdate
from app.service import chapter
from app.api import chapter as chapter_api
from app.crud import task as crud_task
from app.db.models.task import TaskStatus, TaskType

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def user(db, name):
    row = User(id=uuid4(), username=name, hashed_password="x")
    db.add(row)
    db.commit()
    return row


def photo(db, owner, when, number, city="杭州"):
    row = Photo(id=uuid4(), owner_id=owner.id, filename=f"chapter-{number}.jpg",
                file_path=f"/photos/chapter-{number}.jpg", file_type=FileType.image,
                photo_time=when, upload_time=when, is_deleted=False)
    db.add(row)
    db.flush()
    db.add(PhotoMetadata(photo_id=row.id, city=city, province="浙江省"))
    return row


def test_chapter_time_membership_preview_and_owner_boundary(face_sqlite_session):
    db = face_sqlite_session
    owner, stranger = user(db, "chapter-owner"), user(db, "chapter-stranger")
    first = photo(db, owner, datetime(2022, 1, 1, 0, 0), 1)
    last = photo(db, owner, datetime(2022, 1, 31, 23, 59), 2)
    photo(db, owner, datetime(2022, 2, 1, 0, 0), 3)
    photo(db, stranger, datetime(2022, 1, 15, 12, 0), 4)
    db.commit()
    row = chapter.create(db, owner.id, ChapterDefinition(
        title="  一月 ", start_date=date(2022, 1, 1), end_date=date(2022, 1, 31), cover_photo_id=first.id))
    assert row.title == "一月"
    assert chapter.serialize(db, row)["photo_count"] == 2
    assert chapter.year_links(db, owner.id, [2021, 2022, 2023]) == {
        "2021": [], "2022": [{"id": str(row.id), "title": "一月"}], "2023": []}
    assert [item["id"] for item in chapter.photos(db, row, 0, 10)["items"]] == [str(first.id), str(last.id)]
    assert chapter.photos(db, row, 0, 10, 2022)["featured"]["id"] == str(last.id)
    range_preview = chapter.preview(db, owner.id, date(2022, 1, 1), date(2022, 2, 1), row.id)
    assert range_preview["photo_count"] == 3
    assert range_preview["added_photo_count"] == 1
    assert range_preview["removed_photo_count"] == 0
    assert range_preview["month_counts"] == [{"month": "2022-01", "count": 2}, {"month": "2022-02", "count": 1}]
    assert str(last.id) in range_preview["preview_photo_ids"]
    assert chapter.cover_options(db, owner.id, date(2022, 1, 1), date(2022, 2, 1), 0, 2)["total"] == 3
    assert chapter.cover_options(db, stranger.id, date(2022, 1, 1), date(2022, 2, 1), 0, 2)["total"] == 1
    with pytest.raises(HTTPException) as exc:
        chapter.get(db, stranger.id, row.id)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        chapter.update(db, owner.id, row.id, ChapterUpdate(
            title="bad", start_date=date(2022, 1, 1), end_date=date(2022, 1, 31),
            cover_photo_id=last.id, version=row.version + 1))
    assert exc.value.status_code == 409


def test_chapter_merge_split_hidden_and_candidate_idempotence(face_sqlite_session):
    db = face_sqlite_session
    owner = user(db, "chapter-merge-owner")
    for month in range(1, 8):
        for day in (2, 10, 20):
            photo(db, owner, datetime(2020, month, day, 12), month * 100 + day)
    db.commit()
    suggestions = chapter.discover(db, owner.id)
    assert suggestions
    assert chapter.discover(db, owner.id) == []
    candidate = suggestions[0]
    assert candidate.status == "candidate"
    chapter.transition(db, owner.id, candidate.id, "ignore", candidate.version)
    assert chapter.discover(db, owner.id) == []
    chapter.transition(db, owner.id, candidate.id, "restore", candidate.version)
    chapter.transition(db, owner.id, candidate.id, "confirm", candidate.version)
    chapter.transition(db, owner.id, candidate.id, "hide", candidate.version)
    assert chapter.list_owned(db, owner.id)["total"] == 0
    assert chapter.list_owned(db, owner.id, hidden=True)["total"] == 1
    hidden_item = chapter.list_owned(db, owner.id, hidden=True)["items"][0]
    assert hidden_item["title"] == "已隐藏的章节"
    assert hidden_item["cover_photo_id"] is None
    assert hidden_item["photo_count"] == 0
    assert chapter.list_owned(db, owner.id, hidden=True, reveal=True)["items"][0]["title"] == candidate.title
    with pytest.raises(HTTPException):
        chapter.get(db, owner.id, candidate.id)
    chapter.transition(db, owner.id, candidate.id, "unhide", candidate.version)
    other = chapter.create(db, owner.id, ChapterDefinition(
        title="后篇", start_date=date(2020, 6, 1), end_date=date(2020, 7, 31)))
    start = min(candidate.start_date, other.start_date)
    end = max(candidate.end_date, other.end_date)
    merged = chapter.merge(db, owner.id, ChapterMerge(
        title="完整阶段", start_date=start, end_date=end,
        chapter_ids=[candidate.id, other.id], versions={candidate.id: candidate.version, other.id: other.version}))
    assert merged.status == "confirmed"
    parts = chapter.split(db, owner.id, merged.id, ChapterSplit(
        split_date=date(2020, 5, 1), first_title="前篇", second_title="新后篇", version=merged.version))
    assert parts[0].end_date == date(2020, 4, 30)
    assert parts[1].start_date == date(2020, 5, 1)
    assert sum(chapter.serialize(db, part)["photo_count"] for part in parts) == chapter.preview(db, owner.id, start, end)["photo_count"]


def test_year_link_requires_photo_and_open_chapter_split_cannot_be_future(face_sqlite_session):
    db = face_sqlite_session
    owner = user(db, "chapter-year-owner")
    photo(db, owner, datetime(2020, 3, 1, 12), 1)
    db.commit()
    row = chapter.create(db, owner.id, ChapterDefinition(
        title="持续中", start_date=date(2020, 1, 1)))
    assert chapter.year_links(db, owner.id, [2020, 2021])["2021"] == []
    with pytest.raises(HTTPException) as exc:
        chapter.split(db, owner.id, row.id, ChapterSplit(
            split_date=date.today().replace(year=date.today().year + 1),
            first_title="前篇", second_title="后篇", version=row.version))
    assert exc.value.status_code == 400


def test_discovery_task_is_owner_scoped_and_reused_while_active(face_sqlite_session, monkeypatch):
    from app.service.task_manager import TaskManager

    db = face_sqlite_session
    owner, stranger = user(db, "chapter-task-owner"), user(db, "chapter-task-stranger")

    class FakeManager:
        starts = 0

        def add_task(self, session, type, payload, owner_id):
            return crud_task.add_task(session, type, payload, owner_id=owner_id)

        def start_worker_if_needed(self):
            self.starts += 1

    manager = FakeManager()
    monkeypatch.setattr(TaskManager, "get_instance", classmethod(lambda cls: manager))

    first = chapter_api.discover_chapters(owner, db).data
    second = chapter_api.discover_chapters(owner, db).data
    assert first["id"] == second["id"]
    assert manager.starts == 1
    assert chapter_api.latest_discovery_task(owner, db).data["id"] == first["id"]
    assert chapter_api.latest_discovery_task(stranger, db).data is None
    with pytest.raises(HTTPException) as exc:
        chapter_api.get_discovery_task(UUID(first["id"]), stranger, db)
    assert exc.value.status_code == 404

    task = crud_task.get_task(db, UUID(first["id"]))
    assert task.type == TaskType.DISCOVER_CHAPTERS
    task.status = TaskStatus.COMPLETED
    task.result = {"created": 2}
    db.commit()
    assert chapter_api.latest_discovery_task(owner, db).data is None
    assert chapter_api.get_discovery_task(task.id, owner, db).data["created"] == 2


def test_discovery_worker_persists_result_and_survives_status_lookup(face_sqlite_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.service import task_worker
    from app.service.tasks import chapter_discovery

    db = face_sqlite_session
    owner = user(db, "chapter-worker-owner")
    for month in range(1, 8):
        for day in (2, 10, 20):
            photo(db, owner, datetime(2020, month, day, 12), month * 100 + day)
    db.commit()
    task = crud_task.add_task(db, TaskType.DISCOVER_CHAPTERS, {}, owner_id=owner.id)
    session_factory = sessionmaker(bind=db.bind, autoflush=False)
    monkeypatch.setattr(chapter_discovery, "SessionLocal", session_factory)
    monkeypatch.setattr(task_worker, "SessionLocal", session_factory)

    worker = task_worker.TaskWorker()
    result = asyncio.run(chapter_discovery.ChapterDiscoveryStrategy().process(worker, task, db))
    assert result["created"] > 0
    asyncio.run(worker._flush_results([{
        "task_id": task.id, "task_type": TaskType.DISCOVER_CHAPTERS,
        "status": TaskStatus.COMPLETED, "result": result,
    }]))

    db.expire_all()
    saved = crud_task.get_task(db, task.id)
    assert saved is not None
    assert saved.status == TaskStatus.COMPLETED
    assert saved.result == result
    suggestions = chapter.list_owned(db, owner.id, status="candidate")
    assert suggestions["total"] == result["created"]
    evidence_id = suggestions["items"][0]["evidence"][0]["photo_ids"][0]
    db.query(Photo).filter(Photo.id == UUID(evidence_id)).update({"is_deleted": True})
    db.commit()
    refreshed = chapter.list_owned(db, owner.id, status="candidate")
    assert evidence_id not in refreshed["items"][0]["evidence"][0]["photo_ids"]


def test_chapter_http_routes_create_read_and_hide(face_sqlite_session):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.api.deps import get_current_user
    from app.dependencies import get_db

    db = face_sqlite_session
    owner = user(db, "chapter-http-owner")
    photo(db, owner, datetime(2022, 1, 1, 12), 1)
    db.commit()
    session_factory = sessionmaker(bind=db.bind, autoflush=False)

    def test_db():
        with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(chapter_api.router, prefix="/chapters")
    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(app) as client:
        response = client.post("/chapters", json={
            "title": "一月", "start_date": "2022-01-01", "end_date": "2022-01-31",
        })
        assert response.status_code == 200
        assert response.json()["code"] == 0
        item = response.json()["data"]
        chapter_id = item["id"]
        assert client.get(f"/chapters/{chapter_id}").json()["data"]["photo_count"] == 1
        assert client.get("/chapters/year-links?years=2022&years=2023").json()["data"]["2022"] == [
            {"id": chapter_id, "title": "一月"}]
        assert client.post(f"/chapters/{chapter_id}/hide", json={"version": item["version"]}).status_code == 200
        assert client.get(f"/chapters/{chapter_id}").status_code == 404
        assert client.get(f"/chapters/{chapter_id}?manage=true").status_code == 200
        assert client.get("/chapters").json()["data"]["total"] == 0


def test_diary_entries_survive_photo_removal_and_definition_edits(face_sqlite_session):
    db = face_sqlite_session
    owner = user(db, "diary-writer")
    first = photo(db, owner, datetime(2021, 1, 1, 12), 1)
    for month in (2, 4, 7, 10, 12):
        photo(db, owner, datetime(2021, month, 1, 12), month)
    db.commit()
    row = chapter.create(db, owner.id, ChapterDefinition(
        title="几年的日记", start_date=date(2020, 1, 1), end_date=date(2022, 12, 31),
        diary_entries={"2020": {"title": "照片之外", "body": "这一年开始学摄影。"}},
    ))
    assert chapter.get(db, owner.id, row.id)["years"] == [2020, 2021]
    samples = chapter.photos(db, row, 0, 2, 2021)["representatives"]
    assert samples[0]["photo_time"].startswith("2021-01")
    assert samples[-1]["photo_time"].startswith("2021-12")
    assert len({item["id"] for item in samples}) == 6
    chapter.update(db, owner.id, row.id, ChapterUpdate(
        title="改个名字", start_date=row.start_date, end_date=row.end_date, version=row.version))
    assert chapter.get(db, owner.id, row.id)["diary_entries"]["2020"]["body"] == "这一年开始学摄影。"
    first.is_deleted = True
    db.commit()
    assert str(first.id) not in {item["id"] for item in chapter.photos(db, row, 0, 2, 2021)["representatives"]}


def test_diary_draft_uses_only_scoped_facts_and_does_not_save(face_sqlite_session, monkeypatch):
    from types import SimpleNamespace
    from app.db.models.image_description import ImageDescription
    from app.service import chapter_diary

    db = face_sqlite_session
    owner, stranger = user(db, "diary-ai-owner"), user(db, "diary-ai-stranger")
    included = photo(db, owner, datetime(2021, 5, 1, 12), 1)
    excluded = photo(db, owner, datetime(2022, 5, 1, 12), 2)
    private = photo(db, stranger, datetime(2021, 5, 1, 12), 3)
    for item, text in ((included, "湖边散步"), (excluded, "另一年的画面"), (private, "其他用户的画面")):
        db.add(ImageDescription(photo_id=item.id, description=text))
    db.commit()
    row = chapter.create(db, owner.id, ChapterDefinition(
        title="我的日记", summary="自己写的简介", start_date=date(2020, 1, 1), end_date=date(2023, 1, 1)))
    version = row.version

    class Model:
        async def ainvoke(self, messages):
            prompt = messages[1].content
            assert "湖边散步" in prompt
            assert "另一年的画面" not in prompt
            assert "其他用户的画面" not in prompt
            return SimpleNamespace(content='{"title":"湖边的一年","body":"五月的照片里，留下了湖边散步的画面。"}')

    monkeypatch.setattr(chapter_diary, "configured_model", lambda *_: Model())
    draft = asyncio.run(chapter_diary.generate(db, owner.id, row.id, ChapterDiaryGenerate(
        scope="year", year=2021, version=version)))
    assert draft["source_photo_ids"] == [str(included.id)]
    assert draft["year"] == 2021
    db.refresh(row)
    assert row.version == version
    assert row.summary == "自己写的简介"
    assert row.diary_entries == {}
    chapter.transition(db, owner.id, row.id, "hide", row.version)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chapter_diary.generate(db, owner.id, row.id, ChapterDiaryGenerate(version=row.version)))
    assert exc.value.status_code == 404


@pytest.mark.parametrize("change,expected_status", [("invalid", 502), ("version", 409), ("hide", 404), ("delete_photo", 409)])
def test_diary_generation_rejects_invalid_or_stale_drafts(face_sqlite_session, monkeypatch, change, expected_status):
    from types import SimpleNamespace
    from app.service import chapter_diary

    db = face_sqlite_session
    owner = user(db, "diary-conflict")
    image = photo(db, owner, datetime(2021, 3, 1, 12), 1)
    db.commit()
    row = chapter.create(db, owner.id, ChapterDefinition(title="日记", start_date=date(2021, 1, 1)))
    version = row.version

    class Model:
        async def ainvoke(self, messages):
            if change == "version":
                row.version += 1
            elif change == "hide":
                row.is_hidden = True
            elif change == "delete_photo":
                image.is_deleted = True
            db.commit()
            return SimpleNamespace(content="not JSON" if change == "invalid" else '{"title":"","body":"一段日记。"}')

    monkeypatch.setattr(chapter_diary, "configured_model", lambda *_: Model())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chapter_diary.generate(db, owner.id, row.id, ChapterDiaryGenerate(version=version)))
    assert exc.value.status_code == expected_status
    db.refresh(row)
    assert not row.diary_entries
    assert row.summary is None


def test_merging_diaries_keeps_both_texts_and_filters_stale_sources(face_sqlite_session):
    db = face_sqlite_session
    owner, stranger = user(db, "diary-merge"), user(db, "diary-other")
    own = photo(db, owner, datetime(2021, 3, 1, 12), 1)
    other = photo(db, stranger, datetime(2021, 3, 1, 12), 2)
    db.commit()
    definition = dict(start_date=date(2021, 1, 1), end_date=date(2021, 12, 31))
    first = chapter.create(db, owner.id, ChapterDefinition(title="前篇", **definition,
        diary_entries={"2021": {"title": "春天", "body": "春天学摄影。", "source": "ai",
                                "source_photo_ids": [str(own.id), str(other.id)]}}))
    second = chapter.create(db, owner.id, ChapterDefinition(title="后篇", **definition,
        diary_entries={"2021": {"title": "秋天", "body": "秋天出去旅行。"}}))
    merged = chapter.merge(db, owner.id, ChapterMerge(title="完整的一年", **definition,
        chapter_ids=[first.id, second.id], versions={first.id: first.version, second.id: second.version}))
    entry = chapter.get(db, owner.id, merged.id)["diary_entries"]["2021"]
    assert entry["body"] == "春天学摄影。\n\n秋天出去旅行。"
    assert entry["source_photo_ids"] == [str(own.id)]
    own.is_deleted = True
    db.commit()
    detail = chapter.get(db, owner.id, merged.id)
    assert detail["years"] == [2021]
    assert detail["diary_entries"]["2021"]["source_photo_ids"] == []
