"""Owner-scoped, evidence-backed, one-hop memory exploration.

The two SQL membership sets are projections of live business data, not a stored
graph. In particular, stale inferred MemoryPerson/MemoryPlace rows are never
enough to keep a relationship alive after its photo evidence disappears.
"""

from __future__ import annotations

import base64
import hashlib
import json
from uuid import UUID

import numpy as np
from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, func, literal, or_, select, union
from sqlalchemy.orm import Session

from app.db.models.face import Face, FaceIdentity
from app.db.models.image_vector import ImageVector
from app.db.models.memory import (
    Memory,
    MemoryPerson,
    MemoryPhoto,
    MemoryPlace,
    MemoryStatus,
)
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene

TYPES = ("person", "place", "memory", "photo")
REGION_FIELDS = ("country", "province", "city", "district")
PHOTO_DIVERSITY_POOL = 120
PHOTO_SIMILARITY_THRESHOLD = 0.88


def diversify_photos(keys: list[str], embeddings: dict[str, object]) -> list[str]:
    """Keep the existing rank, but postpone near-duplicates until other views appear."""
    vectors = {}
    for key in keys:
        embedding = embeddings.get(key)
        if embedding is None:
            continue
        vector = np.asarray(embedding, dtype=np.float32)
        length = np.linalg.norm(vector)
        if length > 0:
            vectors[key] = vector / length
    remaining = list(keys)
    result = []
    chosen_vectors = []
    while remaining:
        selected = next(
            (
                key for key in remaining
                if key not in vectors or all(
                    float(np.dot(vectors[key], previous)) < PHOTO_SIMILARITY_THRESHOLD
                    for previous in chosen_vectors
                )
            ),
            remaining[0],
        )
        remaining.remove(selected)
        result.append(selected)
        if selected in vectors:
            chosen_vectors.append(vectors[selected])
    return result


def uuid_key(kind: str, value) -> str:
    return f"{kind}:{UUID(str(value)).hex}"


def region_key(level: str, values: list[str]) -> str:
    return f"place:region:{level}:" + "".join(f"{len(v)}:{v}" for v in values)


def parse_key(value: str) -> tuple[str, object]:
    try:
        if len(value) > 2000:
            raise ValueError()
        if value.startswith("place:region:"):
            _, _, level, remaining = value.split(":", 3)
            if level not in REGION_FIELDS[1:]:
                raise ValueError()
            values = []
            for _ in range(REGION_FIELDS.index(level) + 1):
                size, remaining = remaining.split(":", 1)
                size = int(size)
                if size < 0 or size > 100 or len(remaining) < size:
                    raise ValueError()
                values.append(remaining[:size])
                remaining = remaining[size:]
            if remaining or not values[-1] or any(v != v.strip() for v in values):
                raise ValueError()
            return "place", (level, values)
        if value.startswith("place:scene:"):
            return "place", UUID(value.removeprefix("place:scene:"))
        if value.startswith("place:unresolved:"):
            number = int(value.removeprefix("place:unresolved:"))
            if number < 1:
                raise ValueError()
            return "place", number
        kind, raw = value.split(":", 1)
        if kind not in ("person", "memory", "photo"):
            raise ValueError()
        return kind, UUID(raw)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, "无效的关联对象") from None


def canonical_key(value: str) -> str:
    kind, raw = parse_key(value)
    if isinstance(raw, UUID):
        return uuid_key("place:scene" if kind == "place" else kind, raw)
    if isinstance(raw, tuple):
        return region_key(*raw)
    return f"place:unresolved:{raw}"


def _uuid_expr(kind, column):
    return literal(kind + ":") + func.replace(cast(column, String), "-", "")


def _region_expr(level):
    result = literal(f"place:region:{level}:")
    for field in REGION_FIELDS[: REGION_FIELDS.index(level) + 1]:
        value = func.coalesce(func.trim(getattr(PhotoMetadata, field)), "")
        result = result + cast(func.length(value), String) + literal(":") + value
    return result


def region_conditions(key: str):
    """Exact path predicates shared with the existing location photo endpoint."""
    kind, raw = parse_key(key)
    if kind != "place" or not isinstance(raw, tuple):
        raise HTTPException(400, "需要标准行政区地点")
    level, values = raw
    return [
        func.coalesce(func.trim(getattr(PhotoMetadata, field)), "") == value
        for field, value in zip(REGION_FIELDS, values)
    ]


class Relations:
    def __init__(self, db: Session, owner_id: UUID):
        self.db, self.owner = db, owner_id
        self.photo_scope = and_(Photo.owner_id == owner_id, Photo.is_deleted.is_(False))
        self.person_scope = and_(
            FaceIdentity.owner_id == owner_id,
            FaceIdentity.is_hidden.is_(False),
            FaceIdentity.is_deleted.is_(False),
        )
        self.memory_scope = and_(
            Memory.owner_id == owner_id,
            Memory.status == MemoryStatus.CONFIRMED,
            Memory.deleted_at.is_(None),
        )
        self.scene_scope = or_(Scene.owner_id == owner_id, Scene.owner_id.is_(None))
        # Columns: node ID, node kind, photo ID. UNION deduplicates face boxes.
        photo_parts = [
            select(
                _uuid_expr("photo", Photo.id).label("node"),
                literal("photo").label("kind"),
                Photo.id.label("photo_id"),
            ).where(self.photo_scope)
        ]
        photo_parts.append(
            select(_uuid_expr("person", FaceIdentity.id), literal("person"), Photo.id)
            .select_from(Photo)
            .join(Face, Face.photo_id == Photo.id)
            .join(FaceIdentity, FaceIdentity.id == Face.face_identity_id)
            .where(self.photo_scope, self.person_scope, Face.is_deleted.is_(False))
        )
        for level in REGION_FIELDS[1:]:
            photo_parts.append(
                select(_region_expr(level), literal("place"), Photo.id)
                .select_from(Photo)
                .join(PhotoMetadata, PhotoMetadata.photo_id == Photo.id)
                .where(self.photo_scope, func.trim(getattr(PhotoMetadata, level)) != "")
            )
        photo_parts.append(
            select(_uuid_expr("place:scene", Scene.id), literal("place"), Photo.id)
            .select_from(Photo)
            .join(PhotoMetadata, PhotoMetadata.photo_id == Photo.id)
            .join(Scene, Scene.id == PhotoMetadata.scene_id)
            .where(self.photo_scope, self.scene_scope)
        )
        photo_parts.append(
            select(_uuid_expr("memory", Memory.id), literal("memory"), Photo.id)
            .select_from(Photo)
            .join(MemoryPhoto, MemoryPhoto.photo_id == Photo.id)
            .join(Memory, Memory.id == MemoryPhoto.memory_id)
            .where(self.photo_scope, self.memory_scope)
        )
        self.pm = union(*photo_parts).cte("relation_photo_members")

        # Resolve historical name-only memory places only from a unique path in
        # that memory's live photos. Otherwise preserve the text row's identity.
        matches = []
        for level in REGION_FIELDS[1:]:
            matches.append(
                select(
                    MemoryPlace.id.label("link_id"), _region_expr(level).label("node")
                )
                .select_from(MemoryPlace)
                .join(Memory, Memory.id == MemoryPlace.memory_id)
                .join(MemoryPhoto, MemoryPhoto.memory_id == Memory.id)
                .join(Photo, Photo.id == MemoryPhoto.photo_id)
                .join(PhotoMetadata, PhotoMetadata.photo_id == Photo.id)
                .where(
                    self.memory_scope,
                    self.photo_scope,
                    MemoryPlace.scene_id.is_(None),
                    MemoryPlace.level.in_([level, "custom"]),
                    func.trim(MemoryPlace.name)
                    == func.trim(getattr(PhotoMetadata, level)),
                    func.trim(getattr(PhotoMetadata, level)) != "",
                )
            )
        candidates = union(*matches).cte("relation_place_candidates")
        resolved = (
            select(candidates.c.link_id, func.min(candidates.c.node).label("node"))
            .group_by(candidates.c.link_id)
            .having(func.count(func.distinct(candidates.c.node)) == 1)
            .cte("relation_resolved_places")
        )
        scene_evidence = (
            select(Photo.id)
            .join(PhotoMetadata, PhotoMetadata.photo_id == Photo.id)
            .join(MemoryPhoto, MemoryPhoto.photo_id == Photo.id)
            .where(
                self.photo_scope,
                MemoryPhoto.memory_id == MemoryPlace.memory_id,
                PhotoMetadata.scene_id == MemoryPlace.scene_id,
            )
            .correlate(MemoryPlace)
            .exists()
        )
        self.places = (
            select(
                MemoryPlace.id.label("link_id"),
                MemoryPlace.memory_id,
                case(
                    (Scene.id.isnot(None), _uuid_expr("place:scene", Scene.id)),
                    (resolved.c.node.isnot(None), resolved.c.node),
                    else_=literal("place:unresolved:") + cast(MemoryPlace.id, String),
                ).label("node"),
            )
            .select_from(MemoryPlace)
            .join(Memory, Memory.id == MemoryPlace.memory_id)
            .outerjoin(Scene, and_(Scene.id == MemoryPlace.scene_id, self.scene_scope))
            .outerjoin(resolved, resolved.c.link_id == MemoryPlace.id)
            .where(
                self.memory_scope,
                or_(MemoryPlace.scene_id.is_(None), Scene.id.isnot(None)),
                or_(
                    MemoryPlace.source == "user",
                    resolved.c.node.isnot(None),
                    scene_evidence,
                ),
            )
            .cte("relation_memory_places")
        )
        memory_parts = [
            select(self.pm.c.node, self.pm.c.kind, Memory.id.label("memory_id"))
            .select_from(self.pm)
            .join(MemoryPhoto, MemoryPhoto.photo_id == self.pm.c.photo_id)
            .join(Memory, Memory.id == MemoryPhoto.memory_id)
            .where(self.memory_scope, self.pm.c.kind != "memory")
        ]
        memory_parts.append(
            select(_uuid_expr("memory", Memory.id), literal("memory"), Memory.id).where(
                self.memory_scope
            )
        )
        memory_parts.append(
            select(_uuid_expr("person", FaceIdentity.id), literal("person"), Memory.id)
            .select_from(Memory)
            .join(MemoryPerson, MemoryPerson.memory_id == Memory.id)
            .join(FaceIdentity, FaceIdentity.id == MemoryPerson.face_identity_id)
            .where(self.memory_scope, self.person_scope, MemoryPerson.source == "user")
        )
        memory_parts.append(
            select(self.places.c.node, literal("place"), self.places.c.memory_id)
        )
        self.mm = union(*memory_parts).cte("relation_memory_members")

    def photo_ids(self, node):
        return select(self.pm.c.photo_id).where(self.pm.c.node == node)

    def memory_ids(self, node):
        return select(self.mm.c.memory_id).where(self.mm.c.node == node)

    def require(self, value: str) -> dict:
        key = canonical_key(value)
        kind, raw = parse_key(key)
        if kind == "person":
            valid = self.db.scalar(
                select(FaceIdentity.id).where(self.person_scope, FaceIdentity.id == raw)
            )
        elif kind == "memory":
            valid = self.db.scalar(
                select(Memory.id).where(self.memory_scope, Memory.id == raw)
            )
        elif kind == "photo":
            valid = self.db.scalar(
                select(Photo.id).where(self.photo_scope, Photo.id == raw)
            )
        else:
            owned_scene = (
                self.db.scalar(
                    select(Scene.id).where(
                        Scene.id == raw, Scene.owner_id == self.owner
                    )
                )
                if isinstance(raw, UUID)
                else None
            )
            valid = (
                owned_scene
                or self.db.scalar(
                    select(self.pm.c.node).where(self.pm.c.node == key).limit(1)
                )
                or self.db.scalar(
                    select(self.mm.c.node).where(self.mm.c.node == key).limit(1)
                )
            )
        if not valid:
            raise HTTPException(404, "内容已不可用")
        return self.hydrate([key])[0]

    def hydrate(self, keys: list[str]) -> list[dict]:
        """Bounded batch hydration; never use a hidden face as a person's avatar."""
        parsed = {key: parse_key(key) for key in keys}
        groups = {
            kind: [
                raw for k, raw in parsed.values() if k == kind and isinstance(raw, UUID)
            ]
            for kind in TYPES
        }
        people = {
            row.id: row
            for row in self.db.scalars(
                select(FaceIdentity).where(
                    self.person_scope, FaceIdentity.id.in_(groups["person"])
                )
            )
        }
        portraits = dict(
            self.db.execute(
                select(Face.face_identity_id, func.min(cast(Photo.id, String)))
                .select_from(Face)
                .join(Photo, Photo.id == Face.photo_id)
                .where(
                    self.photo_scope,
                    Face.is_deleted.is_(False),
                    Face.face_identity_id.in_(list(people)),
                )
                .group_by(Face.face_identity_id)
            ).all()
        )
        memories = {
            row.id: row
            for row in self.db.scalars(
                select(Memory).where(self.memory_scope, Memory.id.in_(groups["memory"]))
            )
        }
        photo_ids = groups["photo"] + [
            row.cover_photo_id for row in memories.values() if row.cover_photo_id
        ]
        photos = {
            row.id: row
            for row in self.db.scalars(
                select(Photo).where(self.photo_scope, Photo.id.in_(photo_ids))
            )
        }
        photo_locations = {
            row.photo_id: row
            for row in self.db.scalars(
                select(PhotoMetadata).where(
                    PhotoMetadata.photo_id.in_(groups["photo"])
                )
            )
        }
        scenes = {
            row.id: row
            for row in self.db.scalars(
                select(Scene).where(self.scene_scope, Scene.id.in_(groups["place"]))
            )
        }
        text_ids = [
            raw
            for kind, raw in parsed.values()
            if kind == "place" and isinstance(raw, int)
        ]
        texts = {
            row.id: row
            for row in self.db.scalars(
                select(MemoryPlace)
                .join(Memory, Memory.id == MemoryPlace.memory_id)
                .where(self.memory_scope, MemoryPlace.id.in_(text_ids))
            )
        }
        result = []
        for key, (kind, raw) in parsed.items():
            node = {
                "id": key,
                "type": kind,
                "label": "",
                "subtitle": "",
                "photo_id": None,
                "detail_target": None,
            }
            if kind == "person" and raw in people:
                node.update(
                    label=people[raw].identity_name or "未命名人物",
                    photo_id=str(UUID(portraits[raw])) if raw in portraits else None,
                    detail_target={"kind": "person", "id": str(raw)},
                )
            elif kind == "memory" and raw in memories:
                row = memories[raw]
                node.update(
                    label=row.title,
                    subtitle=(
                        row.start_time.isoformat() if row.start_time else "时间待确认"
                    ),
                    photo_id=(
                        str(row.cover_photo_id)
                        if row.cover_photo_id in photos
                        else None
                    ),
                    detail_target={"kind": "memory", "id": str(raw)},
                )
            elif kind == "photo" and raw in photos:
                row = photos[raw]
                metadata = photo_locations.get(raw)
                date = (
                    f"{row.photo_time.year}年{row.photo_time.month}月{row.photo_time.day}日"
                    if row.photo_time
                    else "时间待确认"
                )
                location = (
                    " · ".join(v for v in (metadata.city, metadata.district) if v)
                    if metadata
                    else ""
                )
                if metadata and not location:
                    location = (metadata.address or "").strip()
                node.update(
                    label=row.filename or "照片",
                    subtitle=" · ".join(v for v in (date, location) if v),
                    photo_id=str(raw),
                    detail_target={"kind": "photo", "id": str(raw)},
                )
            elif kind == "place" and isinstance(raw, tuple):
                level, values = raw
                node.update(
                    label=values[-1],
                    subtitle=" · ".join(v for v in values[:-1] if v),
                    detail_target={
                        "kind": "place",
                        "name": values[-1],
                        "level": level,
                        "place_key": key,
                    },
                )
            elif kind == "place" and raw in scenes:
                node.update(
                    label=scenes[raw].name,
                    subtitle=scenes[raw].address or "地点",
                    detail_target={
                        "kind": "place",
                        "name": scenes[raw].name,
                        "level": "scene",
                        "sceneId": str(raw),
                    },
                )
            elif kind == "place" and raw in texts:
                node.update(
                    label=texts[raw].name,
                    subtitle="未关联标准地点 · 查看来源记忆",
                    detail_target={"kind": "memory", "id": str(texts[raw].memory_id)},
                )
            else:
                continue
            result.append(node)
        return result

    def _cursor(self, cursor, context):
        if not cursor:
            return None
        try:
            data = json.loads(
                base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            )
            if data["scope"] != self._scope(context) or not isinstance(
                data["last"], list
            ):
                raise ValueError()
            return data["last"]
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise HTTPException(400, "分页条件已改变，请刷新") from None

    def _scope(self, context):
        return hashlib.sha256(
            json.dumps([str(self.owner), context], ensure_ascii=False).encode()
        ).hexdigest()

    def _next(self, last, context):
        # Cursor is context-bound, not an authorization token. Every page uses
        # the same live SQL permission predicates even for a forged cursor.
        return (
            base64.urlsafe_b64encode(
                json.dumps({"scope": self._scope(context), "last": last}).encode()
            )
            .decode()
            .rstrip("=")
        )

    def neighbors(self, root: str, types: list[str], limit=20, cursor=None):
        center = self.require(root)
        root = center["id"]
        types = sorted(set(types))
        if (
            not types
            or any(kind not in TYPES for kind in types)
            or not 1 <= limit <= 40
        ):
            raise HTTPException(400, "请选择有效类型，数量须为1至40")
        ps = (
            select(
                self.pm.c.node,
                self.pm.c.kind,
                literal(0).label("memories"),
                func.count(func.distinct(self.pm.c.photo_id)).label("photos"),
                func.max(Photo.photo_time).label("latest"),
            )
            .join(Photo, Photo.id == self.pm.c.photo_id)
            .where(self.pm.c.photo_id.in_(self.photo_ids(root)))
            .group_by(self.pm.c.node, self.pm.c.kind)
        )
        ms = (
            select(
                self.mm.c.node,
                self.mm.c.kind,
                func.count(func.distinct(self.mm.c.memory_id)),
                literal(0),
                func.max(Memory.start_time),
            )
            .join(Memory, Memory.id == self.mm.c.memory_id)
            .where(self.mm.c.memory_id.in_(self.memory_ids(root)))
            .group_by(self.mm.c.node, self.mm.c.kind)
        )
        evidence = ps.union_all(ms).subquery()
        ranked = select(
            evidence.c.node,
            evidence.c.kind,
            func.sum(evidence.c.memories).label("mc"),
            func.sum(evidence.c.photos).label("pc"),
            func.max(evidence.c.latest).label("latest"),
        ).where(evidence.c.node != root, evidence.c.kind.in_(types))
        if center["type"] in ("memory", "photo"):
            ranked = ranked.where(evidence.c.kind != center["type"])
        ranked = ranked.group_by(evidence.c.node, evidence.c.kind).subquery()
        # A photo's neighbors must actually occur in that photo, not merely in
        # another photo belonging to the same event.
        direct = select(ranked).where(or_(ranked.c.kind != "photo", ranked.c.pc > 0))
        if center["type"] == "photo":
            direct = direct.where(ranked.c.pc > 0)
        if center["type"] == "place":
            direct = direct.where(or_(ranked.c.kind != "place", ranked.c.mc > 0))
        ranked = direct.subquery()
        if "photo" in types:
            # A recent burst of shots must not crowd every other day and place
            # off the first page. Keep the rank in SQL so cursors stay stable.
            geographic_path = (
                func.coalesce(func.trim(PhotoMetadata.country), "")
                + literal("/")
                + func.coalesce(func.trim(PhotoMetadata.province), "")
                + literal("/")
                + func.coalesce(func.trim(PhotoMetadata.city), "")
                + literal("/")
                + func.coalesce(func.trim(PhotoMetadata.district), "")
            )
            photo_context = (
                select(
                    _uuid_expr("photo", Photo.id).label("node"),
                    cast(func.date(Photo.photo_time), String).label("day"),
                    Photo.photo_time.label("shot_time"),
                    func.coalesce(
                        cast(PhotoMetadata.scene_id, String),
                        func.nullif(func.trim(PhotoMetadata.address), ""),
                        func.nullif(geographic_path, "///"),
                        "未记录地点",
                    ).label("place"),
                )
                .select_from(Photo)
                .outerjoin(PhotoMetadata, PhotoMetadata.photo_id == Photo.id)
                .where(self.photo_scope)
                .subquery()
            )
            candidates = (
                select(ranked, photo_context.c.day, photo_context.c.place, photo_context.c.shot_time)
                .outerjoin(
                    photo_context,
                    and_(
                        ranked.c.kind == "photo",
                        ranked.c.node == photo_context.c.node,
                    ),
                )
                .subquery()
            )
            day_bucket = case(
                (candidates.c.kind == "photo", func.coalesce(candidates.c.day, "未记录日期")),
                else_=candidates.c.node,
            )
            place_bucket = case(
                (candidates.c.kind == "photo", func.coalesce(candidates.c.place, "未记录地点")),
                else_=candidates.c.node,
            )
            balanced = select(
                candidates,
                func.row_number()
                .over(
                    partition_by=(candidates.c.kind, day_bucket),
                    order_by=(candidates.c.shot_time.desc().nullslast(), candidates.c.node),
                )
                .label("day_rank"),
                func.row_number()
                .over(
                    partition_by=(candidates.c.kind, place_bucket),
                    order_by=(candidates.c.shot_time.desc().nullslast(), candidates.c.node),
                )
                .label("place_rank"),
            ).subquery()
            ranked = balanced
            first_diversity_rank = case(
                (ranked.c.day_rank < ranked.c.place_rank, ranked.c.day_rank),
                else_=ranked.c.place_rank,
            )
            second_diversity_rank = case(
                (ranked.c.day_rank > ranked.c.place_rank, ranked.c.day_rank),
                else_=ranked.c.place_rank,
            )
            diversity_order = (
                case((ranked.c.kind == "photo", first_diversity_rank), else_=0),
                case((ranked.c.kind == "photo", second_diversity_rank), else_=0),
            )
        else:
            diversity_order = (literal(0), literal(0))
        # Round-robin category ranks avoid one dominant type hiding the others.
        ordered = select(
            ranked,
            func.row_number()
            .over(
                partition_by=ranked.c.kind,
                order_by=(
                    *diversity_order,
                    ranked.c.mc.desc(),
                    ranked.c.pc.desc(),
                    ranked.c.latest.desc().nullslast(),
                    ranked.c.node,
                ),
            )
            .label("position"),
        ).subquery()
        display_position = ordered.c.position
        if "photo" in types:
            photo_keys = self.db.scalars(
                select(ordered.c.node)
                .where(ordered.c.kind == "photo")
                .order_by(ordered.c.position, ordered.c.node)
                .limit(PHOTO_DIVERSITY_POOL)
            ).all()
            if photo_keys:
                photo_ids = [UUID(key.removeprefix("photo:")) for key in photo_keys]
                embeddings = {
                    uuid_key("photo", photo_id): embedding
                    for photo_id, embedding in self.db.execute(
                        select(ImageVector.photo_id, ImageVector.embedding)
                        .join(Photo, Photo.id == ImageVector.photo_id)
                        .where(self.photo_scope, ImageVector.photo_id.in_(photo_ids))
                    )
                }
                diverse_keys = diversify_photos(photo_keys, embeddings)
                display_position = case(
                    {key: index for index, key in enumerate(diverse_keys, 1)},
                    value=ordered.c.node,
                    else_=ordered.c.position,
                )
        presented = select(ordered, display_position.label("display_position")).subquery()
        context = ["neighbors", root, types, limit, "visual-diversity-v1"]
        query = select(presented)
        last = self._cursor(cursor, context)
        if last is not None:
            if (
                len(last) != 2
                or not isinstance(last[0], int)
                or not isinstance(last[1], str)
            ):
                raise HTTPException(400, "无效分页")
            query = query.where(
                or_(
                    presented.c.display_position > last[0],
                    and_(presented.c.display_position == last[0], presented.c.node > last[1]),
                )
            )
        rows = self.db.execute(
            query.order_by(presented.c.display_position, presented.c.node).limit(limit + 1)
        ).all()
        has_more, rows = len(rows) > limit, rows[:limit]
        nodes = self.hydrate([row.node for row in rows])
        counts = {row.node: row for row in rows}
        edges = []
        for node in nodes:
            row = counts[node["id"]]
            summary = []
            if row.mc:
                summary.append(f"{row.mc} 段相关记忆")
            if row.pc:
                pair_types = {center["type"], node["type"]}
                label = (
                    "共同照片"
                    if pair_types == {"person"}
                    else (
                        "在此地识别到人物的照片"
                        if pair_types == {"person", "place"}
                        else "直接关联照片"
                    )
                )
                summary.append(f"{row.pc} 张{label}")
            edges.append(
                {
                    "source": root,
                    "target": node["id"],
                    "memory_count": row.mc,
                    "photo_count": row.pc,
                    "relation_kinds": (["memory_association"] if row.mc else [])
                    + (["photo_evidence"] if row.pc else []),
                    "evidence_summary": " · ".join(summary),
                }
            )
        return {
            "center": center,
            "nodes": nodes,
            "edges": edges,
            "has_more": has_more,
            "next_cursor": (
                self._next([rows[-1].display_position, rows[-1].node], context)
                if has_more and rows
                else None
            ),
        }

    def evidence(self, left, right, kind="memory", limit=20, cursor=None):
        a, b = self.require(left), self.require(right)
        left, right = a["id"], b["id"]
        if left == right:
            raise HTTPException(400, "请选择两个不同对象")
        if kind not in ("memory", "photo") or not 1 <= limit <= 50:
            raise HTTPException(400, "无效的依据类型或数量")
        model, members = (Memory, self.mm) if kind == "memory" else (Photo, self.pm)
        id_col = members.c.memory_id if kind == "memory" else members.c.photo_id
        timestamp = Memory.start_time if kind == "memory" else Photo.photo_time
        # ISO timestamp + UUID give a portable, stable key including null times.
        time_key = func.coalesce(cast(timestamp, String), "")
        node_key = _uuid_expr(kind, model.id)
        query = select(node_key.label("node"), time_key.label("time")).where(
            model.id.in_(select(id_col).where(members.c.node == left)),
            model.id.in_(select(id_col).where(members.c.node == right)),
            self.memory_scope if kind == "memory" else self.photo_scope,
        )
        context = ["evidence", *sorted([left, right]), kind, limit]
        last = self._cursor(cursor, context)
        if last is not None:
            if len(last) != 2 or not all(isinstance(v, str) for v in last):
                raise HTTPException(400, "无效分页")
            query = query.where(
                or_(time_key < last[0], and_(time_key == last[0], node_key > last[1]))
            )
        rows = self.db.execute(
            query.order_by(time_key.desc(), node_key).limit(limit + 1)
        ).all()
        has_more, rows = len(rows) > limit, rows[:limit]
        return {
            "objects": [a, b],
            "items": self.hydrate([row.node for row in rows]),
            "has_more": has_more,
            "next_cursor": (
                self._next([rows[-1].time, rows[-1].node], context)
                if has_more and rows
                else None
            ),
        }

    def search(self, kind="person", q="", limit=20, cursor=None):
        if kind not in TYPES or not 1 <= limit <= 50:
            raise HTTPException(400, "无效的类型或数量")
        if kind == "person":
            query = select(
                _uuid_expr(kind, FaceIdentity.id).label("node"),
                func.coalesce(FaceIdentity.identity_name, "未命名人物").label("label"),
            ).where(self.person_scope)
        elif kind == "memory":
            query = select(
                _uuid_expr(kind, Memory.id).label("node"), Memory.title.label("label")
            ).where(self.memory_scope)
        elif kind == "photo":
            query = select(
                _uuid_expr(kind, Photo.id).label("node"), Photo.filename.label("label")
            ).where(self.photo_scope)
        else:
            parts = []
            for level in REGION_FIELDS[1:]:
                parts.append(
                    select(
                        _region_expr(level).label("node"),
                        getattr(PhotoMetadata, level).label("label"),
                    )
                    .select_from(Photo)
                    .join(PhotoMetadata, PhotoMetadata.photo_id == Photo.id)
                    .where(
                        self.photo_scope, func.trim(getattr(PhotoMetadata, level)) != ""
                    )
                )
            parts.append(
                select(_uuid_expr("place:scene", Scene.id), Scene.name)
                .select_from(Photo)
                .join(PhotoMetadata, PhotoMetadata.photo_id == Photo.id)
                .join(Scene, Scene.id == PhotoMetadata.scene_id)
                .where(self.photo_scope, self.scene_scope)
            )
            parts.append(
                select(_uuid_expr("place:scene", Scene.id), Scene.name).where(
                    Scene.owner_id == self.owner
                )
            )
            parts.append(
                select(self.places.c.node, MemoryPlace.name).join(
                    MemoryPlace, MemoryPlace.id == self.places.c.link_id
                )
            )
            sources = union(*parts).subquery()
            query = select(
                sources.c.node, func.min(sources.c.label).label("label")
            ).group_by(sources.c.node)
        source = query.subquery()
        query = select(source).where(
            source.c.label.contains(q.strip(), autoescape=True)
        )
        context = ["search", kind, q.strip(), limit]
        last = self._cursor(cursor, context)
        if last is not None:
            if len(last) != 1 or not isinstance(last[0], str):
                raise HTTPException(400, "无效分页")
            query = query.where(source.c.node > last[0])
        rows = self.db.execute(query.order_by(source.c.node).limit(limit + 1)).all()
        has_more, rows = len(rows) > limit, rows[:limit]
        return {
            "items": self.hydrate([row.node for row in rows]),
            "has_more": has_more,
            "next_cursor": (
                self._next([rows[-1].node], context) if has_more and rows else None
            ),
        }
