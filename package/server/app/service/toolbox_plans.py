"""Read-only planning, frozen destinations and per-item operation history."""
import hashlib
import itertools
import math
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func
from app.db.models.album import Album
from app.db.models.image_vector import ImageVector
from app.db.models.photo import Photo, FileType
from app.db.models.toolbox import ToolboxPlan, ToolboxPlanItem
from app.schemas.toolbox import PlanRequest, ToolConfig
from app.service.toolbox_scope import allowed_directory, canonical, iter_scope, scope_preview
from app.utils.export_formatter import format_export_filename
from app.utils.path_validation import validate_filename, validate_target_path

VARIABLES = {
    "date", "time", "year", "month", "day", "hour", "minute", "city", "location",
    "original", "index", "sequence3", "sequence4", "camera", "lens", "iso",
    "province", "district", "extension", "second",
}
TIME_VARIABLES = {"date", "time", "year", "month", "day", "hour", "minute", "second"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def validate_template(template: str):
    variables = re.findall(r"\{([^{}]*)\}", template)
    unknown = set(variables) - VARIABLES
    literal = re.sub(r"\{[^{}]*\}", "", template)
    if unknown or "{" in literal or "}" in literal:
        raise ValueError("未知或不完整的模板变量：" + ", ".join(sorted(unknown)))
    if not template.strip() or any(c in literal for c in '/\\:*?"<>|\x00'):
        raise ValueError("命名模板为空或包含非法路径字符")
    return set(variables)


def photo_data(photo):
    metadata = photo.metadata_info
    return {
        "time": str(photo.photo_time), "upload": str(photo.upload_time),
        "metadata": {key: getattr(metadata, key, None) for key in
                     ("province", "city", "district", "address", "make", "model", "exif_info")},
        "tags": sorted((str(tag.id), tag.tag_name) for tag in photo.tags),
        "people": sorted((str(face.identity.id), face.identity.identity_name)
                         for face in photo.faces if face.identity),
    }


def fingerprint(photo):
    stat = os.stat(photo.file_path)
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "data": digest(photo_data(photo))}


def rule_groups(photo, rule, config):
    metadata = photo.metadata_info
    if rule.strategy == "time":
        value = photo.photo_time or (photo.upload_time if config.missing == "upload" else None)
        if not value:
            groups = [("unknown", ["未知时间"])] if config.missing == "placeholder" else []
        else:
            parts = [value.strftime("%Y")]
            if rule.granularity in {"month", "day"}:
                parts.append(value.strftime("%m"))
            if rule.granularity == "day":
                parts.append(value.strftime("%d"))
            groups = [("-".join(parts), parts)]
    elif rule.strategy == "location":
        keys = rule.granularity.split("_")
        values = [getattr(metadata, key, None) for key in keys]
        if any(not value for value in values):
            groups = [("unknown", ["未知位置"])] if config.missing == "placeholder" else []
        else:
            parts = list(dict.fromkeys(values))
            groups = [(json.dumps(values, ensure_ascii=False), parts)]
    elif rule.strategy == "category":
        groups = [(str(tag.id), [tag.tag_name]) for tag in sorted(photo.tags, key=lambda t: (t.tag_name, str(t.id)))]
    else:
        identities = {str(face.identity.id): face.identity.identity_name for face in photo.faces
                      if face.identity and face.identity.identity_name}
        groups = [(key, [value]) for key, value in sorted(identities.items(), key=lambda p: (p[1], p[0]))]
    if not groups and config.missing == "placeholder":
        groups = [("unknown", ["未分类" if rule.strategy == "category" else "未命名"])]
    if rule.groups is not None:
        groups = [group for group in groups if group[0] in rule.groups]
    return [(key, parts if rule.nested else ["-".join(parts)]) for key, parts in groups]


def group_options(db, user, scope, rule):
    config = ToolConfig(kind="album", rules=[rule], missing="placeholder")
    counts, labels = Counter(), {}
    for photo in iter_scope(db, user, scope, relations=True):
        for key, parts in rule_groups(photo, rule, config):
            counts[key] += 1
            labels[key] = " / ".join(parts)
    return [{"id": key, "name": labels[key], "count": counts[key]} for key in sorted(counts, key=lambda k: labels[k])]


def grouping_paths(photo, config):
    groups = [rule_groups(photo, rule, config) for rule in config.rules]
    if any(not group for group in groups):
        return [], "缺少归档信息或不在指定分组"
    if any(len(group) > 1 for group in groups) and config.multi_group == "skip":
        return [], "多个分组存在歧义，请明确归属"
    if config.multi_group == "first":
        groups = [group[:1] for group in groups]
    if math.prod(len(group) for group in groups) > 100:
        return [], "单个影像匹配分组过多，请缩小分组"
    paths = []
    for combination in itertools.product(*groups):
        parts = [part for _, values in combination for part in values]
        for part in parts:
            validate_filename(part, ".")
            if part in {".", ".."} or any(c in part for c in '/\\:*?"<>|'):
                raise ValueError("归档分组包含非法目录名称")
        paths.append(parts)
    return paths, ""


def rename_path(photo, config, index):
    variables = validate_template(config.template)
    value = photo.photo_time or (photo.upload_time if config.missing == "upload" else None)
    if variables & TIME_VARIABLES and not value:
        raise ValueError("缺少拍摄时间")
    metadata = photo.metadata_info
    if config.missing == "skip":
        for key in variables & {"city", "location", "province", "district", "camera"}:
            field = {"location": "address", "camera": "make"}.get(key, key)
            if not getattr(metadata, field, None):
                raise ValueError("缺少命名所需的地点或设备信息")
    template = config.template
    replacements = {
        "province": getattr(metadata, "province", None) or "未知省份",
        "district": getattr(metadata, "district", None) or "未知区县",
        "extension": os.path.splitext(photo.filename)[1].lstrip("."),
        "second": value.strftime("%S") if value else "00",
    }
    for key, replacement in replacements.items():
        replacement = re.sub(r'[/\\:*?"<>|\x00-\x1f]', "_", replacement)
        template = template.replace("{" + key + "}", replacement)
    frozen = SimpleNamespace(photo_time=value or datetime(1970, 1, 1), upload_time=None)
    basename = format_export_filename(template, frozen, index, metadata, photo.filename)
    return os.path.join(os.path.dirname(photo.file_path), basename + os.path.splitext(photo.filename)[1])


def collision_free(path, source, reserved):
    if canonical(path) == canonical(source):
        return path
    stem, extension = os.path.splitext(path)
    counter = 1
    while canonical(path) in reserved or os.path.lexists(path):
        path = f"{stem}({counter}){extension}"
        counter += 1
    validate_target_path(path)
    reserved.add(canonical(path))
    return path


def prior_success(db, user, photo, config):
    signature = digest(config.model_dump(mode="json"))
    rows = db.query(ToolboxPlanItem).join(ToolboxPlan).filter(
        ToolboxPlan.owner_id == user.id, ToolboxPlanItem.photo_id == photo.id,
        ToolboxPlanItem.status == "success", ToolboxPlan.kind == config.kind,
    ).order_by(ToolboxPlanItem.id.desc()).limit(100)
    for row in rows:
        if row.detail.get("signature") != signature:
            continue
        if config.action == "copy":
            try:
                if row.detail.get("output_fingerprint") == file_fingerprint(row.target):
                    return True
            except OSError:
                continue
        elif canonical(row.target) == canonical(photo.file_path):
            try:
                if row.detail.get("output_fingerprint") == file_fingerprint(photo.file_path):
                    return True
            except OSError:
                continue
    return False


def file_fingerprint(path):
    stat = os.stat(path)
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def completed_copy_targets(db, user, photo, config):
    rows = db.query(ToolboxPlanItem).join(ToolboxPlan).filter(
        ToolboxPlan.owner_id == user.id, ToolboxPlanItem.photo_id == photo.id,
        ToolboxPlanItem.status == "success", ToolboxPlan.kind == "organize",
    ).order_by(ToolboxPlanItem.id.desc()).limit(100)
    signature, source_fingerprint = digest(config.model_dump(mode="json")), fingerprint(photo)
    completed = set()
    for row in rows:
        if row.detail.get("signature") != signature or row.fingerprint != source_fingerprint:
            continue
        try:
            if row.detail.get("output_fingerprint") == file_fingerprint(row.target):
                completed.add(canonical(row.detail.get("requested_target", row.target)))
        except OSError:
            continue
    return completed


def unsupported_reason(photo):
    if getattr(photo.file_type, "value", photo.file_type) != FileType.image.value:
        return "暂不处理视频或动态照片关联文件"
    stem, _ = os.path.splitext(photo.file_path)
    if any(os.path.exists(stem + extension) for extension in
           (".mov", ".MOV", ".mp4", ".MP4", ".dng", ".DNG", ".cr2", ".CR2", ".nef", ".NEF")):
        return "检测到关联文件，为防止拆散已跳过"
    return ""


def cleanup_candidates(db, user, photos, config):
    """Only in-scope IDs can become candidates; outside photos are references."""
    selected = {photo.id for photo in photos}
    compare = db.query(Photo).filter(Photo.owner_id == user.id, Photo.is_deleted.is_(False),
                                    Photo.file_type == FileType.image)
    if not config.compare_all:
        compare = compare.filter(Photo.id.in_(selected))
    candidates = {}
    if config.cleanup_mode == "quality":
        for photo in photos:
            description = photo.image_description
            if description is None:
                continue
            score = (description.memory_score or 0) + (description.quality_score or 0)
            if score <= config.quality_max:
                candidates[photo.id] = {"group": "quality", "label": f"评分 {score:g}"}
    elif config.cleanup_mode == "duplicate":
        grouped = {}
        for photo in compare.filter(Photo.md5.isnot(None), Photo.md5 != "").yield_per(250):
            grouped.setdefault(photo.md5, []).append(photo.id)
        for md5, ids in grouped.items():
            if len(ids) >= 2:
                for pid in selected.intersection(ids):
                    candidates[pid] = {"group": md5, "md5": md5, "label": f"重复组，共 {len(ids)} 项",
                                       "related_ids": list(map(str, ids[:100]))}
    else:
        import numpy as np
        rows = db.query(ImageVector.photo_id, ImageVector.embedding).join(Photo).filter(
            Photo.owner_id == user.id, Photo.is_deleted.is_(False), Photo.file_type == FileType.image)
        if not config.compare_all:
            rows = rows.filter(Photo.id.in_(selected))
        rows = rows.limit(3001).all()
        if len(rows) > 3000:
            raise ValueError("本版相似比较最多支持 3000 项，请缩小范围或关闭全库比较")
        if rows:
            vectors = np.asarray([r.embedding for r in rows], dtype=float)
            vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
            for index, row in enumerate(rows):
                if row.photo_id not in selected:
                    continue
                similarity = vectors @ vectors[index]
                matches = [str(rows[i].photo_id) for i in np.flatnonzero(similarity >= config.similarity) if i != index]
                if matches:
                    candidates[row.photo_id] = {"group": str(row.photo_id), "label": f"{len(matches)} 项相似参考", "related_ids": [str(row.photo_id), *matches]}
    return candidates


def item_for_photo(db, user, photo, config, index, reserved, candidates, anchor):
    path = photo.file_path
    item = ToolboxPlanItem(photo_id=photo.id, source=path, target="", status="ready",
                           fingerprint={}, detail={"signature": digest(config.model_dump(mode="json"))})
    try:
        reason = unsupported_reason(photo)
        if reason:
            raise ValueError(reason)
        item.fingerprint = fingerprint(photo)
        if config.kind == "cleanup":
            if photo.id not in candidates:
                raise ValueError("不属于清理候选，或缺少已计算的哈希/特征/评分")
            item.status = "candidate"
            item.detail = {**item.detail, **candidates[photo.id]}
            item.reason = "需手动勾选，未选项目保留"
        elif config.kind == "metadata":
            if os.path.splitext(path)[1].lower() not in {".jpg", ".jpeg", ".webp"}:
                raise ValueError("此格式不支持安全写入 EXIF")
            metadata = photo.metadata_info
            if config.only_missing_metadata and metadata and metadata.make and metadata.model:
                raise ValueError("拍摄设备信息完整，无需修改")
            desired_time = config.custom_time if config.time_mode == "custom" else None
            if config.time_mode == "auto":
                from app.utils.filename import extract_datetime_from_filename
                value = extract_datetime_from_filename(photo.filename) or photo.photo_time
                desired_time = value.isoformat() if value else None
            if not desired_time and not config.make and not config.model:
                raise ValueError("没有可写入的时间或设备信息")
            item.detail = {**item.detail, "time": desired_time, "make": config.make, "model": config.model}
            item.target = path
        elif config.kind == "rename":
            item.target = collision_free(rename_path(photo, config, index), path, reserved)
            if canonical(item.target) == canonical(path):
                raise ValueError("名称已符合规则")
        else:
            if config.kind == "organize" and config.action != "copy" and prior_success(db, user, photo, config):
                raise ValueError("相同规则已处理，无需再次归档")
            groups, reason = grouping_paths(photo, config)
            if not groups:
                raise ValueError(reason)
            if config.kind == "album":
                names = list(dict.fromkeys(config.album_prefix + " / ".join(parts) for parts in groups))
                if any(len(name) > 100 for name in names):
                    raise ValueError("相册名称超过 100 字")
                item.detail = {**item.detail, "albums": names}
                item.target = "；".join(names)
            else:
                relative = os.path.relpath(os.path.dirname(path), anchor) if config.layout == "preserve" else ""
                targets = []
                requested = []
                completed = completed_copy_targets(db, user, photo, config) if config.action == "copy" else set()
                for parts in groups:
                    target = os.path.join(config.target, relative, *parts, os.path.basename(path))
                    if not os.path.commonpath([canonical(target), canonical(config.target)]) == canonical(config.target):
                        raise ValueError("生成路径越界")
                    if canonical(target) in completed:
                        continue
                    requested.append(target)
                    targets.append(collision_free(target, path, reserved))
                if not targets:
                    raise ValueError("相同规则的副本已生成，无需再次复制")
                if all(canonical(target) == canonical(path) for target in targets):
                    raise ValueError("路径已符合规则")
                item.target = targets[0]
                item.detail = {**item.detail, "targets": targets, "requested_targets": requested,
                               "requested_target": requested[0]}
    except (ValueError, OSError) as error:
        item.status = "skipped"
        item.reason = str(error)
    return item


def create_plan(db, user, request: PlanRequest):
    config = request.config.model_copy(deep=True)
    if config.kind == "rename":
        validate_template(config.template)
    anchor = None
    if config.kind == "organize":
        config.target = allowed_directory(db, user, config.target)
        existing = config.target
        while not os.path.exists(existing):
            existing = os.path.dirname(existing)
        if not os.path.isdir(existing) or not os.access(existing, os.W_OK):
            raise ValueError("目标目录不可写")
        if config.layout == "preserve":
            if request.scope.source != "folders" or len(request.scope.folders) != 1:
                raise ValueError("保留目录层级需要选择一个共同源文件夹")
            anchor = allowed_directory(db, user, request.scope.folders[0])
    photos = list(itertools.islice(iter_scope(db, user, request.scope, relations=True), 50001))
    if len(photos) > 50000:
        raise ValueError("本版每次最多处理 50000 项，请缩小范围")
    photos.sort(key=lambda p: (p.photo_time is None, p.photo_time or datetime.max, str(p.id)), reverse=config.descending)
    candidates = cleanup_candidates(db, user, photos, config) if config.kind == "cleanup" else {}
    plan = ToolboxPlan(id=uuid4(), owner_id=user.id, kind=config.kind, status="preview", version=1,
                       request={"scope": request.scope.model_dump(mode="json"), "config": config.model_dump(mode="json")},
                       summary={}, expires_at=datetime.utcnow() + timedelta(minutes=30))
    db.add(plan)
    reserved = {canonical(photo.file_path) for photo in photos if photo.file_path}
    counters = Counter()
    counts = Counter()
    output_files, output_bytes = 0, 0
    for position, photo in enumerate(photos):
        directory = os.path.dirname(photo.file_path) if config.reset_index else ""
        index = counters[directory] + config.start_index
        counters[directory] += 1
        item = item_for_photo(db, user, photo, config, index, reserved, candidates, anchor)
        item.plan_id = plan.id
        targets = item.detail.get("targets", [])
        if item.status == "ready" and len(targets) > 1:
            item.target = targets[0]
            item.detail = {**item.detail, "targets": [targets[0]]}
            for number, target in enumerate(targets[1:], start=1):
                db.add(ToolboxPlanItem(plan_id=plan.id, photo_id=photo.id, source=item.source,
                       target=target, status="ready", reason="", fingerprint=item.fingerprint,
                       detail={**item.detail, "targets": [target],
                               "requested_target": item.detail["requested_targets"][number]}))
                counts["ready"] += 1
        db.add(item)
        counts[item.status] += 1
        if item.status == "ready":
            number = max(1, len(targets))
            output_files += number
            output_bytes += item.fingerprint.get("size", 0) * number
        if position % 250 == 0:
            db.flush()
    if config.kind == "organize" and config.action == "copy":
        import shutil
        if shutil.disk_usage(existing).free < output_bytes:
            db.rollback()
            raise ValueError("目标存储空间不足，无法容纳预计副本")
    plan.summary = {"total": len(photos), "ready": counts["ready"], "skipped": counts["skipped"],
                    "candidate": counts["candidate"], "output_files": output_files, "output_bytes": output_bytes}
    db.commit()
    return plan


def plan_view(plan):
    return {"id": str(plan.id), "kind": plan.kind, "status": plan.status, "version": plan.version,
            "request": plan.request, "summary": plan.summary, "task_id": str(plan.task_id) if plan.task_id else None,
            "created_at": plan.created_at, "expires_at": plan.expires_at, "finished_at": plan.finished_at,
            "stop_requested": plan.stop_requested}


def item_view(item):
    return {"id": item.id, "photo_id": str(item.photo_id), "source": item.source, "target": item.target,
            "status": item.status, "reason": item.reason, "detail": item.detail}
