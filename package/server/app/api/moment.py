"""朋友圈日文案 API。

MVP 只支持 scope_type='all'（全部照片视图）。相册/搜索场景由前端在展示层隐藏入口。
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.crud import moment as moment_crud
from app.db.models.user import User
from app.dependencies import get_db
from app.schemas.moment import (
    MomentDayCaption,
    MomentDayCaptionGenerateRequest,
    MomentDayCaptionUpsert,
)
from app.service.moment.day_caption_service import (
    generate_caption_stream,
    generate_caption_sync,
)

router = APIRouter()


@router.get("/day-captions", response_model=List[MomentDayCaption], summary="批量获取日文案")
def list_day_captions(
    start: date = Query(..., description="起始日期（含），YYYY-MM-DD"),
    end: date = Query(..., description="截止日期（含），YYYY-MM-DD"),
    scope_type: str = Query("all"),
    scope_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if start > end:
        raise HTTPException(status_code=400, detail="start 必须早于或等于 end")
    if (end - start).days > 366:
        raise HTTPException(status_code=400, detail="日期区间过长（最多 366 天）")
    return moment_crud.list_captions(db, current_user.id, scope_type, scope_id, start, end)


@router.put("/day-captions/{day}", response_model=MomentDayCaption, summary="手动保存日文案")
def upsert_day_caption(
    day: date,
    payload: MomentDayCaptionUpsert,
    scope_type: str = Query("all"),
    scope_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    caption = payload.caption.strip()
    if not caption:
        raise HTTPException(status_code=400, detail="caption 不能为空")
    obj = moment_crud.upsert_caption(
        db, current_user.id, scope_type, scope_id, day, caption, source="manual"
    )
    return obj


@router.delete("/day-captions/{day}", summary="清除日文案")
def delete_day_caption(
    day: date,
    scope_type: str = Query("all"),
    scope_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ok = moment_crud.delete_caption(db, current_user.id, scope_type, scope_id, day)
    return {"deleted": ok}


@router.post("/day-captions/generate", summary="AI 生成日文案（可流式）")
async def generate_day_caption(
    request: MomentDayCaptionGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """- ``stream=true`` 返回 SSE，每 chunk 一句 ``data: {"content": "..."}\\n\\n``；
    - ``stream=false`` 一次性返回 JSON ``{caption, cached, source, model_name}``。
    """
    if request.scope_type != "all":
        raise HTTPException(status_code=400, detail="目前只支持 scope_type='all' 场景")

    try:
        if request.stream:
            return StreamingResponse(
                generate_caption_stream(
                    user_id=current_user.id,
                    db=db,
                    day=request.day,
                    tz_name=request.timezone,
                    scope_type=request.scope_type,
                    scope_id=request.scope_id,
                    style=request.style,
                    connection_id=request.connection_id,
                    model_name=request.model_name,
                    force=request.force,
                ),
                media_type="text/event-stream",
            )
        result = await generate_caption_sync(
            user_id=current_user.id,
            db=db,
            day=request.day,
            tz_name=request.timezone,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            style=request.style,
            connection_id=request.connection_id,
            model_name=request.model_name,
            force=request.force,
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"内部错误: {e}")
