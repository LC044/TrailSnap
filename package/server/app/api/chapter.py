"""Life chapter routes. Hidden content requires the explicit management context."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.models.task import Task, TaskStatus, TaskType
from app.dependencies import BaseResponse, get_db
from app.schemas.chapter import ChapterDefinition, ChapterDiaryDraft, ChapterDiaryGenerate, ChapterMerge, ChapterPreview, ChapterSplit, ChapterUpdate, ChapterVersion
from app.service import chapter as service
from app.schemas.chapter import ChapterDayCaption, ChapterDays
from datetime import date

router = APIRouter()


def _discovery_task(task: Task) -> dict:
    return {"id": str(task.id), "status": task.status,
            "created": (task.result or {}).get("created", 0),
            "error": "发现失败，请重试" if task.status == TaskStatus.FAILED else None}


@router.get("")
def list_chapters(status: str = Query("confirmed"), hidden: bool = Query(False), reveal: bool = Query(False),
                  skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.list_owned(db, user.id, status=status, hidden=hidden, reveal=reveal,
                                                        skip=skip, limit=limit))


@router.get("/year-links")
def chapter_year_links(years: list[int] = Query(default=[]), user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    if len(years) > 30 or any(year < 1900 or year > 2200 for year in years):
        raise HTTPException(400, "年份范围无效")
    return BaseResponse.success(data=service.year_links(db, user.id, years))


@router.post("/preview")
def preview_chapter(payload: ChapterPreview, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.preview(db, user.id, payload.start_date,
                                                     payload.end_date, payload.chapter_id))


@router.post("/cover-options")
def chapter_cover_options(payload: ChapterPreview, skip: int = Query(0, ge=0),
                          limit: int = Query(30, ge=1, le=100),
                          user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.cover_options(db, user.id, payload.start_date,
                                                           payload.end_date, skip, limit))


@router.post("/discover")
def discover_chapters(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.service.task_manager import TaskManager

    # Serialize submissions for one owner on PostgreSQL. A second click
    # returns the active persisted task instead of starting another scan.
    db.query(User).filter(User.id == user.id).with_for_update().first()
    active = db.query(Task).filter(
        Task.owner_id == user.id, Task.type == TaskType.DISCOVER_CHAPTERS,
        Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
    ).order_by(Task.created_at.desc()).first()
    if active:
        db.rollback()
        TaskManager.get_instance().start_worker_if_needed()
        return BaseResponse.success(data=_discovery_task(active))
    task = TaskManager.get_instance().add_task(
        db, type=TaskType.DISCOVER_CHAPTERS, payload={}, owner_id=user.id)
    return BaseResponse.success(data=_discovery_task(task))


@router.get("/discover/tasks/latest")
def latest_discovery_task(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(
        Task.owner_id == user.id, Task.type == TaskType.DISCOVER_CHAPTERS,
        Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
    ).order_by(Task.created_at.desc()).first()
    return BaseResponse.success(data=_discovery_task(task) if task else None)


@router.get("/discover/tasks/{task_id}")
def get_discovery_task(task_id: UUID, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.owner_id == user.id,
                                 Task.type == TaskType.DISCOVER_CHAPTERS).first()
    if not task:
        raise HTTPException(404, "章节发现任务不存在")
    return BaseResponse.success(data=_discovery_task(task))


@router.post("/merge")
def merge_chapters(payload: ChapterMerge, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.serialize(db, service.merge(db, user.id, payload)))


@router.post("")
def create_chapter(payload: ChapterDefinition, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.serialize(db, service.create(db, user.id, payload)))


@router.get("/{chapter_id}")
def get_chapter(chapter_id: UUID, manage: bool = Query(False), user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.get(db, user.id, chapter_id, manage=manage))


@router.get("/{chapter_id}/photos")
def chapter_photos(chapter_id: UUID, skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
                   year: int | None = Query(None, ge=1900, le=2200),
                   manage: bool = Query(False),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = service._owned(db, user.id, chapter_id, manage=manage)
    return BaseResponse.success(data=service.photos(db, row, skip, limit, year))


@router.get("/{chapter_id}/events")
def chapter_events(chapter_id: UUID, skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                   year: int | None = Query(None, ge=1900, le=2200), manage: bool = Query(False),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = service._owned(db, user.id, chapter_id, manage=manage)
    return BaseResponse.success(data=service.events(db, row, skip, limit, year))


@router.patch("/{chapter_id}")
def update_chapter(chapter_id: UUID, payload: ChapterUpdate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.serialize(db, service.update(db, user.id, chapter_id, payload)))


@router.post("/{chapter_id}/split")
def split_chapter(chapter_id: UUID, payload: ChapterSplit, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    rows = service.split(db, user.id, chapter_id, payload)
    return BaseResponse.success(data=[service.serialize(db, row) for row in rows])


@router.post("/{chapter_id}/diary/generate", response_model=BaseResponse[ChapterDiaryDraft])
async def generate_diary(chapter_id: UUID, payload: ChapterDiaryGenerate,
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> BaseResponse[ChapterDiaryDraft]:
    from app.service import chapter_diary

    return BaseResponse.success(data=await chapter_diary.generate(db, user.id, chapter_id, payload))


@router.get("/{chapter_id}/diary/days", response_model=BaseResponse[ChapterDays])
def diary_days(chapter_id: UUID, skip: int = Query(0, ge=0), limit: int = Query(6, ge=1, le=12),
               year: int | None = Query(None, ge=1900, le=2200), month: int | None = Query(None, ge=1, le=12),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> BaseResponse[ChapterDays]:
    from app.service import chapter_days
    return BaseResponse.success(data=chapter_days.list_days(db, user.id, chapter_id, skip, limit, year, month))


@router.post("/{chapter_id}/diary/days/{day}/generate", response_model=BaseResponse[ChapterDayCaption])
async def generate_day(chapter_id: UUID, day: date, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)) -> BaseResponse[ChapterDayCaption]:
    from app.service import chapter_days
    return BaseResponse.success(data=await chapter_days.generate(db, user.id, chapter_id, day))


@router.get("/{chapter_id}/diary/days/{day}/photos", response_model=BaseResponse[dict])
def day_photos(chapter_id: UUID, day: date, skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> BaseResponse[dict]:
    from app.service import chapter_days
    _, scoped = chapter_days.day_scope(db, user.id, chapter_id, day)
    return BaseResponse.success(data=service.photos(db, scoped, skip, limit))


@router.put("/{chapter_id}/diary/days/{day}", response_model=BaseResponse[ChapterDayCaption])
def save_day(chapter_id: UUID, day: date, payload: ChapterDayCaption,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> BaseResponse[ChapterDayCaption]:
    from app.service import chapter_days
    from app.crud import moment
    chapter_days.day_scope(db, user.id, chapter_id, day)
    db.query(User).filter(User.id == user.id).with_for_update().one()
    saved = moment.upsert_caption(db, user.id, "all", None, day, payload.caption.strip(), "manual")
    return BaseResponse.success(data={"caption": saved.caption, "source": saved.source})


@router.post("/{chapter_id}/{action}")
def chapter_action(chapter_id: UUID, action: str, payload: ChapterVersion,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if action not in {"confirm", "ignore", "restore", "hide", "unhide"}:
        raise HTTPException(404, "操作不存在")
    row = service.transition(db, user.id, chapter_id, action, payload.version)
    return BaseResponse.success(data=service.serialize(db, row))


@router.delete("/{chapter_id}")
def delete_chapter(chapter_id: UUID, version: int = Query(..., ge=1),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.delete(db, user.id, chapter_id, version)
    return BaseResponse.success(data={"deleted": True})
