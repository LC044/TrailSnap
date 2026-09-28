"""Bounded relation exploration; the service checks every object's ownership."""

from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.dependencies import BaseResponse, get_db
from app.service.relations import Relations
from app.schemas.relations import EvidencePage, NeighborPage, NodePage

router = APIRouter()


def _respond(db: Session, operation):
    sqlite_connection = None
    try:
        # Bound expensive aggregates as well as response size. Reset the SQLite
        # connection callback before returning it to the shared connection pool.
        connection = db.connection()
        if connection.dialect.name == "postgresql":
            db.execute(text("SET LOCAL statement_timeout = '8000ms'"))
        elif connection.dialect.name == "sqlite":
            deadline = monotonic() + 8
            sqlite_connection = connection.connection.driver_connection
            sqlite_connection.set_progress_handler(
                lambda: int(monotonic() > deadline), 10000
            )
        return BaseResponse.success(data=operation())
    except HTTPException as exc:
        return BaseResponse.fail(code=exc.status_code, msg=str(exc.detail))
    except OperationalError as exc:
        if (
            getattr(exc.orig, "pgcode", None) == "57014"
            or str(exc.orig) == "interrupted"
        ):
            if sqlite_connection is not None:
                sqlite_connection.set_progress_handler(None, 0)
                sqlite_connection = None
            db.rollback()
            return BaseResponse.fail(code=503, msg="关联查询耗时较长，请稍后重试")
        raise
    finally:
        if sqlite_connection is not None:
            sqlite_connection.set_progress_handler(None, 0)


@router.get("/neighbors", response_model=BaseResponse[NeighborPage])
def neighbors(
    root: str = Query(max_length=2000),
    types: str = "person,place,memory",
    limit: int = Query(20, ge=1, le=40),
    cursor: str | None = Query(None, max_length=4000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _respond(
        db,
        lambda: Relations(db, user.id).neighbors(root, types.split(","), limit, cursor),
    )


@router.get("/common-memories", response_model=BaseResponse[EvidencePage])
def common_memories(
    left: str = Query(max_length=2000),
    right: str = Query(max_length=2000),
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None, max_length=4000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _respond(
        db,
        lambda: Relations(db, user.id).evidence(left, right, "memory", limit, cursor),
    )


@router.get("/evidence", response_model=BaseResponse[EvidencePage])
def evidence(
    left: str = Query(max_length=2000),
    right: str = Query(max_length=2000),
    kind: str = "photo",
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None, max_length=4000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _respond(
        db, lambda: Relations(db, user.id).evidence(left, right, kind, limit, cursor)
    )


@router.get("/search", response_model=BaseResponse[NodePage])
def search(
    type: str = "person",
    q: str = Query("", max_length=200),
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None, max_length=4000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _respond(db, lambda: Relations(db, user.id).search(type, q, limit, cursor))
