"""Editable CLIP rules and independent classification tag associations."""

import threading
from collections import OrderedDict
from contextlib import contextmanager
from uuid import UUID, uuid4
from weakref import WeakKeyDictionary

import requests
from sqlalchemy import event, func, insert, update
from sqlalchemy.orm import Session
from app.db.models.clip_classification import (
    ClipCategory,
    ClipRuleRevision,
    TagDecision,
)
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.photo import Photo, FileType
from app.db.models.image_vector import ImageVector
from app.core.config_manager import config_manager
from app.service.clip_catalog import load_catalog

_cache = OrderedDict()
_lock = threading.Lock()
_vector_locks = {}
_initialized_presets = WeakKeyDictionary()
_PENDING_PRESETS = "clip_initialized_presets"
_PRESET_CACHE_LIMIT = 4096
STRICTNESS = {"relaxed": -0.025, "standard": 0.0, "strict": 0.025}
DEFAULT_THRESHOLD = 0.42


@event.listens_for(Session, "after_commit")
def _publish_initialized_presets(session):
    # A savepoint commit is still subject to the outer transaction's rollback.
    if session.in_nested_transaction():
        return
    pending = session.info.pop(_PENDING_PRESETS, set())
    with _lock:
        for engine, key in pending:
            cache = _initialized_presets.setdefault(engine, OrderedDict())
            cache[key] = True
            cache.move_to_end(key)
            while len(cache) > _PRESET_CACHE_LIMIT:
                cache.popitem(last=False)


@event.listens_for(Session, "after_soft_rollback")
def _discard_initialized_presets(session, previous_transaction):
    session.info.pop(_PENDING_PRESETS, None)


@event.listens_for(Session, "after_transaction_end")
def _clear_closed_preset_transaction(session, transaction):
    if transaction.parent is None:
        session.info.pop(_PENDING_PRESETS, None)


def normalize(vectors):
    import numpy as np

    data = np.asarray(vectors, dtype=np.float32)
    if data.ndim != 2 or not len(data) or not np.isfinite(data).all():
        raise ValueError("向量格式无效")
    norms = np.linalg.norm(data, axis=1, keepdims=True)
    if np.any(norms < 1e-12):
        raise ValueError("不能使用零向量")
    return data / norms


def prototype(vectors):
    return normalize(normalize(vectors).mean(axis=0, keepdims=True))[0]


def ai_url(owner_id, db):
    return config_manager.get_user_config(owner_id, db).ai.ai_api_url.rstrip("/")


def selected_embedding_model(url):
    response = ai_request(requests.get, url + "/ai/models", timeout=15)
    data = response.json()
    selected = data["tasks"]["embedding"]["selected"]
    return next(model["runtimeName"] for model in data["models"] if model["id"] == selected)


def ai_request(method, url, **kwargs):
    """Keep startup and model preparation failures resumable by the worker."""
    try:
        response = method(url, **kwargs)
        response.raise_for_status()
        return response
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise RuntimeError("等待 AI 模型：AI 服务暂不可达，恢复后自动继续") from exc
    except requests.HTTPError as exc:
        response = exc.response
        if response is not None and response.status_code in (409, 502, 503, 504):
            raise RuntimeError("等待 AI 模型：AI 服务或模型尚未就绪，稍后自动继续") from exc
        if response is not None and "not ready" in response.text.lower():
            raise RuntimeError("等待 AI 模型：文本模型尚未就绪，稍后自动继续") from exc
        raise


@contextmanager
def vector_generation_lock(url, model):
    """Serialize cold fills per endpoint/model, including concurrent previews."""
    key = (url, model)
    with _lock:
        mutex, users = _vector_locks.get(key, (threading.Lock(), 0))
        _vector_locks[key] = (mutex, users + 1)
    try:
        with mutex:
            yield
    finally:
        with _lock:
            _, users = _vector_locks[key]
            if users == 1:
                del _vector_locks[key]
            else:
                _vector_locks[key] = (mutex, users - 1)


def category_vector(url, model, descriptions):
    return category_vectors(url, model, [descriptions])[0]


def category_vectors(url, model, description_groups):
    """Warm uncached rules in bounded inference batches, then reuse prototypes."""
    with vector_generation_lock(url, model):
        return _category_vectors(url, model, description_groups)


def _category_vectors(url, model, description_groups):
    missing = []
    seen = set()
    values = {}
    with _lock:
        for descriptions in description_groups:
            key = (url, model, tuple(descriptions), "mean-normalize-v1")
            if key in _cache:
                values[key] = _cache[key]
                _cache.move_to_end(key)
            elif key not in seen:
                missing.append((key, descriptions))
                seen.add(key)
    for start in range(0, len(missing), 16):
        batch = missing[start : start + 16]
        texts = [text for _, descriptions in batch for text in descriptions]
        response = ai_request(
            requests.post,
            url + "/embedding/text",
            json={"texts": texts, "model": model, "cache": True},
            timeout=120,
        )
        if response.headers.get("X-Embedding-Model") != model:
            raise ValueError("AI 服务未确认文本模型身份，请升级 AI 服务")
        encoded = response.json()
        if len(encoded) != len(texts):
            raise ValueError("AI 服务返回的文本向量数量不一致")
        offset = 0
        for key, descriptions in batch:
            value = prototype(encoded[offset : offset + len(descriptions)])
            offset += len(descriptions)
            values[key] = value
            with _lock:
                _cache[key] = value
                while len(_cache) > 512:
                    _cache.popitem(last=False)
    return [
        values[(url, model, tuple(descriptions), "mean-normalize-v1")].copy()
        for descriptions in description_groups
    ]


def apply_results(db, photo, prepared):
    """Update a photo's category associations with bounded queries and ordered locks."""
    if not prepared:
        return 0
    lock_photo(db, photo.id)
    category_ids = [cat.id for cat, *_ in prepared]
    current = {
        c.id: c
        for c in db.query(ClipCategory)
        .filter(ClipCategory.id.in_(category_ids))
        .order_by(ClipCategory.id)
        .populate_existing()
        .with_for_update()
        .all()
    }
    tag_ids = [c.tag_id for c in current.values()]
    relations = {
        r.tag_id: r
        for r in db.query(PhotoTagRelation).filter(
            PhotoTagRelation.photo_id == photo.id, PhotoTagRelation.tag_id.in_(tag_ids)
        )
    }
    decisions = {
        d.tag_id: d.keep
        for d in db.query(TagDecision).filter(
            TagDecision.photo_id == photo.id, TagDecision.tag_id.in_(tag_ids)
        )
    }
    found = 0
    for cat, revision, score, threshold in prepared:
        cat = current.get(cat.id)
        if not cat or cat.revision != revision or not cat.enabled or cat.is_deleted:
            continue
        matched = score >= threshold
        relation = relations.get(cat.tag_id)
        keep = decisions.get(cat.tag_id, matched)
        if keep:
            confidence = 1.0 if decisions.get(cat.tag_id) else score
            if relation is None:
                relation = PhotoTagRelation(
                    photo_id=photo.id, tag_id=cat.tag_id, confidence=confidence
                )
                relations[cat.tag_id] = relation
                db.add(relation)
            else:
                relation.confidence, relation.is_deleted = confidence, False
        elif relation is not None:
            db.delete(relation)
            del relations[cat.tag_id]
        found += int(matched)
    return found


def apply_batch_results(db, prepared_by_photo):
    """Publish a bounded batch under the same photo/category locks as manual edits."""
    from sqlalchemy import delete, insert, update, bindparam

    if not prepared_by_photo:
        return {}
    photo_ids = sorted(prepared_by_photo)
    db.query(Photo.id).filter(Photo.id.in_(photo_ids)).order_by(Photo.id).with_for_update().all()
    ids = {c.id for rows in prepared_by_photo.values() for c, *_ in rows}
    current = {c.id: c for c in db.query(ClipCategory).filter(ClipCategory.id.in_(ids))
               .order_by(ClipCategory.id).populate_existing().with_for_update().all()}
    tag_ids = [c.tag_id for c in current.values()]
    relations = {(r.photo_id, r.tag_id): r for r in db.query(PhotoTagRelation).filter(
        PhotoTagRelation.photo_id.in_(photo_ids), PhotoTagRelation.tag_id.in_(tag_ids))}
    decisions = {(d.photo_id, d.tag_id): d.keep for d in db.query(TagDecision).filter(
        TagDecision.photo_id.in_(photo_ids), TagDecision.tag_id.in_(tag_ids))}
    additions, updates, removals, found = [], [], [], {}
    for photo_id, rows in prepared_by_photo.items():
        found[photo_id] = 0
        for old, revision, score, threshold in rows:
            cat = current.get(old.id)
            if not cat or cat.revision != revision or not cat.enabled or cat.is_deleted:
                continue
            key = (photo_id, cat.tag_id)
            matched = score >= threshold
            found[photo_id] += int(matched)
            relation = relations.get(key)
            if decisions.get(key, matched):
                confidence = 1.0 if decisions.get(key) else score
                if relation is None:
                    additions.append(dict(photo_id=photo_id, tag_id=cat.tag_id, confidence=confidence, is_deleted=False))
                elif relation.confidence != confidence or relation.is_deleted:
                    updates.append(dict(row_id=relation.id, score=confidence))
            elif relation is not None:
                removals.append(relation.id)
    table = PhotoTagRelation.__table__
    connection = db.connection()
    for start in range(0, len(removals), 500):
        connection.execute(delete(table).where(table.c.id.in_(removals[start:start + 500])))
    if updates:
        connection.execute(update(table).where(table.c.id == bindparam('row_id'))
                           .values(confidence=bindparam('score'), is_deleted=False), updates)
    if additions:
        connection.execute(insert(table), additions)
    return found


def get_tag(db, owner_id, name):
    tag = db.query(PhotoTag).filter_by(
        owner_id=owner_id, tag_name=name, type="clip", is_deleted=False
    ).first()
    if tag is None:
        tag = PhotoTag(owner_id=owner_id, tag_name=name, type="clip")
        db.add(tag)
        db.flush()
    return tag


def ensure_presets(db, owner_id):
    from app.db.models.user import User

    data = load_catalog()
    engine = db.get_bind().engine
    cache_key = (str(owner_id), data["version"])
    pending_key = (engine, cache_key)
    with _lock:
        cache = _initialized_presets.get(engine)
        if cache is not None and cache_key in cache:
            cache.move_to_end(cache_key)
            return False
    if pending_key in db.info.get(_PENDING_PRESETS, ()):
        return False
    catalog = data["categories"]
    keys = {item["key"] for item in catalog}
    present = {
        key for (key,) in db.query(ClipCategory.preset_key).filter_by(owner_id=owner_id)
    }
    if keys <= present:
        db.info.setdefault(_PENDING_PRESETS, set()).add(pending_key)
        return False
    # Recheck after locking: another request may have initialized this owner.
    if db.get_bind().dialect.name == "sqlite":
        # A no-op write reserves SQLite's writer across processes until commit.
        db.execute(update(User).where(User.id == owner_id).values(id=User.id))
    else:
        db.query(User).filter_by(id=owner_id).with_for_update().first()
    present = {
        key for (key,) in db.query(ClipCategory.preset_key).filter_by(owner_id=owner_id)
    }
    missing = [item for item in catalog if item["key"] not in present]
    if not missing:
        db.info.setdefault(_PENDING_PRESETS, set()).add(pending_key)
        return False
    tags = {
        tag.tag_name: tag.id
        for tag in db.query(PhotoTag).filter(
            PhotoTag.owner_id == owner_id,
            PhotoTag.type == "clip",
            PhotoTag.is_deleted.is_(False),
            PhotoTag.tag_name.in_([item["name"] for item in missing]),
        )
    }
    additions, categories, rules = [], [], []
    for item in missing:
        if item["name"] not in tags:
            tags[item["name"]] = uuid4()
            additions.append(dict(
                id=tags[item["name"]], owner_id=owner_id,
                tag_name=item["name"], type="clip", is_deleted=False,
            ))
        category_id = uuid4()
        categories.append(dict(
            id=category_id, owner_id=owner_id, tag_id=tags[item["name"]],
            preset_key=item["key"], groups=item["groups"],
            enabled=True, is_deleted=False, revision=1,
        ))
        rules.append(dict(
            category_id=category_id, revision=1, descriptions=item["descriptions"],
            strictness="standard", thresholds=item["thresholds"],
        ))
    if additions:
        db.execute(insert(PhotoTag.__table__), additions)
    db.execute(insert(ClipCategory.__table__), categories)
    db.execute(insert(ClipRuleRevision.__table__), rules)
    db.flush()
    db.info.setdefault(_PENDING_PRESETS, set()).add(pending_key)
    return True


def owned_category(db, owner_id, category_id, lock=False):
    q = db.query(ClipCategory).filter_by(
        id=UUID(str(category_id)), owner_id=owner_id, is_deleted=False
    )
    if lock:
        q = q.with_for_update()
    cat = q.first()
    if cat is None:
        raise ValueError("分类不存在")
    return cat


def serialize_category(db, cat, *, rule=None, tag=None):
    if rule is None:
        rule = db.get(ClipRuleRevision, (cat.id, cat.revision))
    if tag is None:
        tag = db.get(PhotoTag, cat.tag_id)
    builtin = next(
        (c for c in load_catalog()["categories"] if c["key"] == cat.preset_key), None
    )
    return {
        "id": str(cat.id),
        "tag_id": str(cat.tag_id),
        "name": tag.tag_name,
        "groups": cat.groups,
        "enabled": cat.enabled,
        "revision": cat.revision,
        "descriptions": rule.descriptions,
        "strictness": rule.strictness,
        "thresholds": rule.thresholds,
        "builtin": cat.preset_key is not None,
        "calibration": (
            builtin["calibration"]
            if builtin
            and rule.descriptions == builtin["descriptions"]
            and rule.thresholds == builtin["thresholds"]
            else {"status": "custom"}
        ),
    }


def threshold_for(rule, model):
    base = rule.thresholds.get(model, DEFAULT_THRESHOLD)
    return float(base) + STRICTNESS[rule.strictness]


def lock_photo(db, photo_id):
    db.query(Photo.id).filter(Photo.id == photo_id).with_for_update().first()


def decide_tag(db, photo_id, tag_id, keep):
    lock_photo(db, photo_id)
    decision = db.get(TagDecision, (photo_id, tag_id))
    if decision is None:
        db.add(TagDecision(photo_id=photo_id, tag_id=tag_id, keep=keep))
    else:
        decision.keep = keep
    publish_tag(db, photo_id, tag_id, 1.0 if keep else None)


def publish_tag(db, photo_id, tag_id, score=None):
    """Replace one independent category association, honoring manual decisions."""
    if not isinstance(tag_id, UUID):
        # Callers may pass the string form (for example the YOLO classifier's
        # cached tag ids); normalize once instead of forcing every caller.
        tag_id = UUID(str(tag_id))
    lock_photo(db, photo_id)
    db.flush()
    decision = db.get(TagDecision, (photo_id, tag_id))
    keep = decision.keep if decision else score is not None
    relation = db.query(PhotoTagRelation).filter_by(
        photo_id=photo_id, tag_id=tag_id
    ).first()
    if keep:
        confidence = 1.0 if decision and decision.keep else score
        if relation is None:
            db.add(PhotoTagRelation(photo_id=photo_id, tag_id=tag_id, confidence=confidence))
        else:
            relation.confidence, relation.is_deleted = confidence, False
    elif relation is not None:
        db.delete(relation)



def preview(
    db, owner_id, descriptions, strictness, thresholds, sample_size=1000, photo_ids=None
):
    url = ai_url(owner_id, db)
    model = selected_embedding_model(url)
    vector = category_vector(url, model, descriptions)
    base = thresholds.get(model, DEFAULT_THRESHOLD)
    threshold = base + STRICTNESS[strictness]
    query = (
        db.query(Photo, ImageVector)
        .join(ImageVector, Photo.id == ImageVector.photo_id)
        .filter(
            Photo.owner_id == owner_id,
            Photo.is_deleted.is_(False),
            Photo.file_type != FileType.video,
            ImageVector.model_name == model,
        )
    )
    if photo_ids:
        query = query.filter(Photo.id.in_(photo_ids))
    # Deterministic bounded sample; never scan/load an unbounded gallery in API.
    rows = query.order_by(Photo.id).limit(sample_size).all()
    scored = []
    for photo, emb in rows:
        score = float(normalize([emb.embedding])[0] @ vector)
        scored.append({"photo": photo, "score": score, "matched": score >= threshold})
    total = (
        db.query(func.count(Photo.id))
        .filter(
            Photo.owner_id == owner_id,
            Photo.is_deleted.is_(False),
            Photo.file_type != FileType.video,
        )
        .scalar()
    )
    available = query.count()
    return {
        "model": model,
        "threshold": threshold,
        "checked": len(rows),
        "available": available,
        "missing": max(0, total - available)
        if not photo_ids
        else max(0, len(photo_ids) - available),
        "matched_count": sum(r["matched"] for r in scored),
        "matches": sorted(
            (r for r in scored if r["matched"]), key=lambda r: -r["score"]
        )[:18],
        "boundary": sorted(scored, key=lambda r: abs(r["score"] - threshold))[:12],
    }


def enqueue_photo(db, photo, category_ids=None):
    tasks = enqueue_photos(db, [photo], category_ids)
    return tasks[0] if tasks else None


def enqueue_photos(db, photos, category_ids=None, model=None):
    """One rule lookup and one pending-task lookup per owner/embedding batch."""
    from app.db.models.task import Task, TaskType, TaskStatus, DEFAULT_PRIORITIES

    if not photos:
        return []
    owner_id = photos[0].owner_id
    if any(p.owner_id != owner_id for p in photos):
        raise ValueError('分类入队批次必须属于同一用户')
    ensure_presets(db, owner_id)
    cats = db.query(ClipCategory).filter_by(
        owner_id=owner_id, enabled=True, is_deleted=False
    )
    if category_ids:
        cats = cats.filter(ClipCategory.id.in_(category_ids))
    revisions = {str(c.id): c.revision for c in cats}
    if not revisions:
        return []
    pending = {t.photo_id: t for t in db.query(Task).filter(
        Task.owner_id == owner_id, Task.type == TaskType.CLASSIFY_IMAGE_CLIP,
        Task.status == TaskStatus.PENDING, Task.photo_id.in_([p.id for p in photos]))}
    created = []
    for photo in photos:
        existing = pending.get(photo.id)
        if existing is not None:
            existing.payload = dict(existing.payload or {},
                revisions={**(existing.payload or {}).get('revisions', {}), **revisions},
                **({'model': model} if model else {}))
            continue
        task = Task(
            type=TaskType.CLASSIFY_IMAGE_CLIP,
            owner_id=photo.owner_id,
            payload={"photo_id": str(photo.id), "revisions": revisions, **({'model': model} if model else {})},
            status=TaskStatus.PENDING,
            priority=DEFAULT_PRIORITIES[TaskType.CLASSIFY_IMAGE_CLIP],
        )
        db.add(task)
        pending[photo.id] = task
        created.append(task)
    return created
