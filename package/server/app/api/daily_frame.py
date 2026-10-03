"""Daily-frame endpoints, including authenticated source and work streaming."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.daily_frame import DailyFrameWork
from app.db.models.user import User
from app.dependencies import BaseResponse, get_db
from app.schemas.daily_frame import BatchFill, CalendarSettings, FilmCreate, FilmSettings, FrameSelection, FrameVersion
from app.service import daily_frame as service


class DailyFrameRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def wrapped(request: Request):
            try:
                return await handler(request)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, headers=exc.headers,
                    content=BaseResponse.fail(code=exc.status_code, msg=str(exc.detail)).model_dump())
            except RequestValidationError:
                return JSONResponse(status_code=422,
                    content=BaseResponse.fail(code=422, msg="请求参数无效，请检查日期和选帧设置").model_dump())
        return wrapped


router = APIRouter(route_class=DailyFrameRoute)


def media_secret() -> str:
    # Separate signing keys prevent a scoped media ticket becoming a login JWT.
    import hashlib
    from app.core.system_config import system_config
    return hashlib.sha256((system_config.config.security.secret_key + "\0daily-frame-media").encode()).hexdigest()


def media_user(request: Request, token: str | None = Query(None), authorization: str | None = Header(None),
               db: Session = Depends(get_db)) -> User:
    """Media elements use a short-lived ticket scoped to one resource and mode.

    A ticket never grants access to JSON APIs or other photos/works. Header JWTs
    remain available for authenticated downloads and still-image previews.
    """
    if authorization and authorization.startswith("Bearer "):
        return get_current_user(request, db, authorization[7:])
    from jose import jwt, JWTError
    from app.core.system_config import system_config
    security = system_config.config.security
    try:
        claims = jwt.decode(token or "", media_secret(), algorithms=[security.algorithm])
        if (claims.get("purpose") != "daily-frame-media" or claims.get("path") != request.url.path
                or claims.get("mode", "still") != request.query_params.get("mode", "still")):
            raise ValueError
        user = db.get(User, UUID(claims["sub"]))
        if user is None or not user.is_active:
            raise ValueError
        return user
    except (JWTError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(401, "播放凭证已过期，请重新加载") from exc


def media_ticket(user: User, request: Request, mode: str = "still") -> dict:
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.core.system_config import system_config
    security = system_config.config.security
    path = request.url.path.removesuffix("/access") + "/file"
    token = jwt.encode({"sub": str(user.id), "purpose": "daily-frame-media", "path": path, "mode": mode,
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
                       media_secret(), algorithm=security.algorithm)
    # Return a relative route; the client handles configured server/root prefixes.
    return {"token": token}


@router.get("/settings", response_model=BaseResponse[dict])
def settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.settings(db, user.id))


@router.put("/settings", response_model=BaseResponse[dict])
def initialize(payload: CalendarSettings, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.initialize(db, user.id, payload))


@router.get("/calendar", response_model=BaseResponse[dict])
def calendar(start: date, end: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.calendar_range(db, user.id, start, end))


@router.get("/days/{day}", response_model=BaseResponse[dict])
def get_frame(day: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.frame(db, user.id, day))


@router.get("/days/{day}/candidates", response_model=BaseResponse[dict])
def candidates(day: date, skip: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100),
               kind: str = Query("all", pattern="^(all|still|motion)$"),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.candidates(db, user.id, day, skip, limit, kind))


@router.put("/days/{day}", response_model=BaseResponse[dict])
def save(day: date, payload: FrameSelection, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.save(db, user.id, day, payload))


@router.post("/days/{day}/remove", response_model=BaseResponse[dict])
def remove(day: date, payload: FrameVersion, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.remove(db, user.id, day, payload.version))


@router.post("/days/{day}/undo-remove", response_model=BaseResponse[dict])
def undo(day: date, payload: FrameVersion, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.undo_remove(db, user.id, day, payload.version))


@router.get("/fill", response_model=BaseResponse[dict])
def fill(start: date, end: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.suggestions(db, user.id, start, end))


@router.post("/fill", response_model=BaseResponse[dict])
def confirm_fill(payload: BatchFill, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    results = []
    for item in payload.items:
        try:
            frame = service.save(db, user.id, item.day, FrameSelection(**item.model_dump(exclude={"day"})), only_empty=True)
            results.append({"day": item.day.isoformat(), "status": "saved", "frame": frame})
        except HTTPException as exc:
            db.rollback()
            results.append({"day": item.day.isoformat(), "status": "skipped" if exc.status_code == 409 else "failed",
                            "reason": str(exc.detail)})
    return BaseResponse.success(data={"items": results})


@router.get("/assets/{photo_id}", response_model=BaseResponse[dict])
def asset(photo_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    photo = service.owned_photo(db, user.id, photo_id)
    if not photo:
        raise HTTPException(404, "素材不存在")
    result = service.serialize_photo(photo)
    result["day"] = service.photo_day(photo, service.profile(db, user.id))
    if result["has_motion"]:
        from app.service.daily_frame_render import probe_duration
        result["duration"] = probe_duration(service.source_path(photo, "motion")[0]) or 0
    return BaseResponse.success(data=result)


@router.get("/assets/{photo_id}/access", response_model=BaseResponse[dict])
def source_access(photo_id: UUID, request: Request, mode: str = Query("motion", pattern="^(still|motion)$"),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    path, reason = service.source_path(service.owned_photo(db, user.id, photo_id), mode)
    if reason:
        raise HTTPException(404, reason)
    return BaseResponse.success(data=media_ticket(user, request, mode))


@router.get("/assets/{photo_id}/file")
def source_file(photo_id: UUID, mode: str = Query("still", pattern="^(still|motion)$"),
                user: User = Depends(media_user), db: Session = Depends(get_db)):
    photo = service.owned_photo(db, user.id, photo_id)
    path, reason = service.source_path(photo, mode)
    if reason:
        raise HTTPException(404, reason)
    if mode == "still":
        # Browsers do not consistently decode HEIC. Serve an EXIF-oriented JPEG
        # preview; exports always read the full original, never this derivative.
        from io import BytesIO
        from PIL import Image, ImageOps
        from fastapi.responses import Response
        try:
            with Image.open(path) as image:
                preview = ImageOps.exif_transpose(image).convert("RGB")
                preview.thumbnail((1920, 1920))
                output = BytesIO()
                preview.save(output, format="JPEG", quality=90)
        except (OSError, ValueError) as exc:
            raise HTTPException(400, "素材无法解码，请重试或更换素材") from exc
        return Response(content=output.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@router.post("/composition", response_model=BaseResponse[dict])
def composition(payload: FilmSettings, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.composition(db, user.id, payload))


@router.post("/works", response_model=BaseResponse[dict])
def create(payload: FilmCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    work = service.create_work(db, user.id, payload)
    return BaseResponse.success(data=service.serialize_work(db, work))


@router.get("/works", response_model=BaseResponse[dict])
def works(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50),
          user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(DailyFrameWork).filter(DailyFrameWork.owner_id == user.id,
        DailyFrameWork.is_preview.is_(False), DailyFrameWork.deleted_at.is_(None))
    return BaseResponse.success(data={"total": query.count(), "items": [service.serialize_work(db, work)
        for work in query.order_by(DailyFrameWork.created_at.desc()).offset(skip).limit(limit).all()]})


@router.get("/works/{work_id}", response_model=BaseResponse[dict])
def work(work_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.serialize_work(db, service.owned_work(db, user.id, work_id)))


@router.get("/works/{work_id}/poster")
def poster(work_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from pathlib import Path
    from app.service.daily_frame_render import output_root
    work = service.owned_work(db, user.id, work_id)
    if work.status != "ready" or not work.output_path:
        raise HTTPException(404, "封面暂不可用")
    path = Path(work.output_path).resolve()
    if path.parent != output_root(user.id).resolve() or path.suffix != ".mp4" or not path.is_file():
        raise HTTPException(404, "作品文件不可用")
    path = path.with_suffix(".jpg")
    if not path.is_file():
        raise HTTPException(404, "封面暂不可用")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/works/{work_id}/cancel", response_model=BaseResponse[dict])
def cancel(work_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.stop_work(db, user.id, work_id)
    return BaseResponse.success(data={"cancelled": True})


@router.post("/works/{work_id}/retry", response_model=BaseResponse[dict])
def retry(work_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BaseResponse.success(data=service.serialize_work(db, service.retry_work(db, user.id, work_id)))


@router.delete("/works/{work_id}", response_model=BaseResponse[dict])
def delete(work_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.stop_work(db, user.id, work_id, delete=True)
    return BaseResponse.success(data={"deleted": True})


@router.get("/works/{work_id}/file")
def work_file(work_id: UUID, download: bool = False,
              user: User = Depends(media_user), db: Session = Depends(get_db)):
    work = service.owned_work(db, user.id, work_id)
    import os
    if work.status != "ready" or not work.output_path or not os.path.isfile(work.output_path):
        raise HTTPException(404, "作品文件尚未生成或不可用")
    from app.service.daily_frame_render import output_root
    from pathlib import Path
    if Path(work.output_path).resolve().parent != output_root(user.id).resolve():
        raise HTTPException(404, "作品文件不可用")
    import re
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', work.snapshot['settings']['title']).rstrip('. ').strip() or '一日一帧'
    name = f"{title}_{work.snapshot['settings']['start_date']}_{len(work.snapshot['frames'])}天.mp4"
    return FileResponse(work.output_path, media_type="video/mp4", filename=name if download else None,
                        headers={"Cache-Control": "no-store"})


@router.get("/works/{work_id}/access", response_model=BaseResponse[dict])
def work_access(work_id: UUID, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    work = service.owned_work(db, user.id, work_id)
    if work.status != "ready":
        raise HTTPException(409, "作品尚未生成")
    return BaseResponse.success(data=media_ticket(user, request))
