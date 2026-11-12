"""CLIP jobs never wait for another task phase while holding a worker slot."""

from uuid import UUID
import numpy as np
from sqlalchemy import tuple_, or_
from app.db.models.task import Task, TaskType, TaskStatus, DEFAULT_PRIORITIES
from app.db.models.photo import Photo, FileType
from app.db.models.image_vector import ImageVector
from app.db.models.clip_classification import (
    ClipCategory,
    ClipRuleRevision,
)
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.service import clip_classification as svc


@TaskStrategyFactory.register(TaskType.CLASSIFY_IMAGE_CLIP)
class ClipClassificationStrategy(BaseTaskStrategy):
    async def process_batch(self, worker, tasks, db):
        groups = {}
        results = []
        for task in tasks:
            if (task.payload or {}).get('photo_id') and task.owner_id:
                groups.setdefault(task.owner_id, []).append(task)
                continue
            task_id, task_type = task.id, task.type
            try:
                result = await self.process(worker, task, db)
                results.append(
                    {
                        "task_id": task_id,
                        "task_type": task_type,
                        "status": "completed",
                        "result": result,
                    }
                )
            except Exception as exc:
                db.rollback()
                results.append(
                    {
                        "task_id": task_id,
                        "task_type": task_type,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
        for owner_id, items in groups.items():
            identities = [(t.id, t.type) for t in items]
            try:
                results.extend(self.process_photos(db, owner_id, items))
            except Exception as exc:
                db.rollback()
                results.extend(dict(task_id=i, task_type=kind, status='failed', error=str(exc))
                               for i, kind in identities)
        return results

    def process_photos(self, db, owner_id, tasks):
        identities = {t.id: UUID(t.payload['photo_id']) for t in tasks}
        ids = [UUID(t.payload['photo_id']) for t in tasks]
        photos = {p.id: p for p in db.query(Photo).filter(Photo.id.in_(ids),
                  Photo.owner_id == owner_id, Photo.is_deleted.is_(False), Photo.file_type != FileType.video)}
        embeddings = {v.photo_id: v for v in db.query(ImageVector).filter(ImageVector.photo_id.in_(photos))}
        cats = db.query(ClipCategory).filter_by(owner_id=owner_id, enabled=True, is_deleted=False).all()
        rules = {(r.category_id, r.revision): r for r in db.query(ClipRuleRevision).filter(
            tuple_(ClipRuleRevision.category_id, ClipRuleRevision.revision).in_([(c.id, c.revision) for c in cats]))}
        results, grouped, prepared = [], {}, {}
        deferred = []
        for task in tasks:
            pid = UUID(task.payload['photo_id'])
            result = dict(task_id=task.id, task_type=task.type, status='completed')
            results.append(result)
            revisions = task.payload.get('revisions', {})
            selected = [c for c in cats if revisions.get(str(c.id)) == c.revision]
            if pid not in photos or not selected:
                result['result'] = {'status': 'skipped'}
                continue
            emb = embeddings.get(pid)
            model = task.payload.get('model') or (emb.model_name if emb else None)
            if emb is None or emb.model_name != model:
                deferred.append((pid, model))
                result['result'] = {'status': 'deferred', 'reason': 'waiting for image embedding'}
                continue
            grouped.setdefault(model, []).append((pid, emb.embedding, selected, result))
        url = svc.ai_url(owner_id, db) if grouped else None
        for model, rows in grouped.items():
            selected_ids = {c.id for _, _, selected, _ in rows for c in selected}
            active = [c for c in cats if c.id in selected_ids]
            thresholds = [svc.threshold_for(rules[(c.id, c.revision)], model) for c in active]
            vectors = svc.category_vectors(url, model, [rules[(c.id, c.revision)].descriptions for c in active])
            scores = svc.normalize([embedding for _, embedding, _, _ in rows]) @ np.asarray(vectors).T
            for (pid, _, selected, result), values in zip(rows, scores):
                chosen = {c.id for c in selected}
                previous = {c.id: (c, revision, score, threshold)
                            for c, revision, score, threshold in prepared.get(pid, [])}
                previous.update({c.id: (c, c.revision, float(score), threshold)
                                 for c, score, threshold in zip(active, values, thresholds) if c.id in chosen})
                prepared[pid] = list(previous.values())
                result['result'] = dict(status='success', rules_checked=len(selected), model=model)
        # End the read transaction before reserving SQLite's writer.
        db.commit()
        if hasattr(db, 'begin_write'):
            db.begin_write()
        found = svc.apply_batch_results(db, prepared)
        for result in results:
            if result['result']['status'] == 'success':
                result['result']['tags_found'] = found.get(identities[result['task_id']], 0)
        if deferred:
            pending = {t.photo_id: t for t in db.query(Task).filter(Task.owner_id == owner_id,
                Task.type == TaskType.IMAGE_EMBEDDING, Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
                Task.photo_id.in_([pid for pid, _ in deferred]))}
            for pid, model in deferred:
                if pid not in pending:
                    item = Task(type=TaskType.IMAGE_EMBEDDING, owner_id=owner_id, status=TaskStatus.PENDING,
                                priority=DEFAULT_PRIORITIES[TaskType.IMAGE_EMBEDDING],
                                payload=dict(photo_id=str(pid), model=model, force=True))
                    db.add(item)
                    pending[pid] = item
                elif pending[pid].status == TaskStatus.PENDING:
                    pending[pid].payload = dict(pending[pid].payload or {}, model=model, force=True)
        db.commit()
        return results

    @property
    def task_category(self):
        return "AI"

    @property
    def resource_key(self):
        return "clip_classification"

    async def process(self, worker, task, db):
        payload = task.payload or {}
        if not task.owner_id:
            raise ValueError("CLIP 分类任务必须指定所属用户")
        if "photo_id" not in payload:
            if payload.get("wait_for_embeddings") and db.query(Task.id).filter(
                Task.type == TaskType.IMAGE_EMBEDDING,
                Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
                or_(Task.owner_id == task.owner_id, Task.owner_id.is_(None)),
            ).first():
                raise RuntimeError("等待 AI 模型：图片特征重建完成后自动继续分类")
            svc.ensure_presets(db, task.owner_id)
            # Initialization must release its writer before any AI request.
            db.commit()
            cats = db.query(ClipCategory).filter_by(
                owner_id=task.owner_id, enabled=True, is_deleted=False
            )
            if payload.get("category_ids"):
                cats = cats.filter(
                    ClipCategory.id.in_([UUID(c) for c in payload["category_ids"]])
                )
            revisions = {str(c.id): c.revision for c in cats}
            if not revisions:
                return {"generated_tasks": 0}
            model = payload.get("model") or svc.selected_embedding_model(svc.ai_url(task.owner_id, db))
            query = db.query(Photo.id).filter(
                Photo.owner_id == task.owner_id,
                Photo.is_deleted.is_(False),
                Photo.file_type != FileType.video,
            )
            if payload.get("after_photo_id"):
                query = query.filter(Photo.id > UUID(payload["after_photo_id"]))
            photo_ids = [row.id for row in query.order_by(Photo.id).limit(1024)]
            pending = {
                item.photo_id: item
                for item in db.query(Task).filter(
                    Task.owner_id == task.owner_id,
                    Task.type == TaskType.CLASSIFY_IMAGE_CLIP,
                    Task.status == TaskStatus.PENDING,
                    Task.photo_id.in_(photo_ids),
                )
            }
            count = 0
            for photo_id in photo_ids:
                existing = pending.get(photo_id)
                if existing is not None:
                    existing.payload = dict(
                        existing.payload,
                        revisions={**existing.payload.get("revisions", {}), **revisions},
                        model=model,
                    )
                else:
                    db.add(Task(
                        type=TaskType.CLASSIFY_IMAGE_CLIP,
                        owner_id=task.owner_id,
                        status=TaskStatus.PENDING,
                        priority=DEFAULT_PRIORITIES[TaskType.CLASSIFY_IMAGE_CLIP],
                        payload={"photo_id": str(photo_id), "revisions": revisions, "model": model},
                    ))
                    count += 1
            if len(photo_ids) == 1024:
                # Release the classification slot so this page can be scored.
                db.add(Task(
                    type=TaskType.CLASSIFY_IMAGE_CLIP,
                    owner_id=task.owner_id,
                    status=TaskStatus.PENDING,
                    priority=DEFAULT_PRIORITIES[TaskType.CLASSIFY_IMAGE_CLIP] - 1,
                    payload={**payload, "model": model, "after_photo_id": str(photo_ids[-1])},
                ))
            db.commit()
            return {"generated_tasks": count, "photos_checked": len(photo_ids)}
        photo = (
            db.query(Photo)
            .filter_by(
                id=UUID(payload["photo_id"]), owner_id=task.owner_id, is_deleted=False
            )
            .first()
        )
        if not photo or photo.file_type == FileType.video:
            return {"status": "skipped"}
        revisions = payload.get("revisions", {})
        cats = (
            db.query(ClipCategory)
            .filter_by(owner_id=task.owner_id, enabled=True, is_deleted=False)
            .all()
        )
        cats = [
            c
            for c in cats
            if str(c.id) in revisions and c.revision == revisions[str(c.id)]
        ]
        if not cats:
            return {"status": "skipped", "reason": "rules changed or disabled"}
        url = svc.ai_url(task.owner_id, db)
        embedding = db.get(ImageVector, photo.id)
        model = payload.get("model") or (embedding.model_name if embedding is not None else None)
        if embedding is None or (model and embedding.model_name != model):
            # Persist a continuation on the producer, return immediately.
            # IMAGE_EMBEDDING completion schedules CLIP with current revisions.
            pending = (
                db.query(Task)
                .filter(
                    Task.owner_id == task.owner_id,
                    Task.type == TaskType.IMAGE_EMBEDDING,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
                    Task.payload["photo_id"].as_string() == str(photo.id),
                )
                .first()
            )
            if pending is None:
                db.add(
                    Task(
                        type=TaskType.IMAGE_EMBEDDING,
                        owner_id=task.owner_id,
                        status=TaskStatus.PENDING,
                        priority=DEFAULT_PRIORITIES[TaskType.IMAGE_EMBEDDING],
                        payload={
                            "photo_id": str(photo.id),
                            "model": model,
                            "force": True,
                        },
                    )
                )
            elif pending.status == TaskStatus.PENDING:
                pending.payload = dict(pending.payload or {}, model=model, force=True)
            db.commit()
            return {"status": "deferred", "reason": "waiting for image embedding"}
        image = svc.normalize([embedding.embedding])[0]
        rules = {
            (r.category_id, r.revision): r
            for r in db.query(ClipRuleRevision).filter(
                tuple_(ClipRuleRevision.category_id, ClipRuleRevision.revision).in_(
                    [(c.id, c.revision) for c in cats]
                )
            )
        }
        prepared = []
        rules_to_score = []
        for cat in cats:
            revision = cat.revision
            rule = rules[(cat.id, revision)]
            threshold = svc.threshold_for(rule, model)
            rules_to_score.append((cat, revision, threshold, rule))
        vectors = svc.category_vectors(
            url, model, [rule.descriptions for *_, rule in rules_to_score]
        )
        for (cat, revision, threshold, rule), vector in zip(rules_to_score, vectors):
            prepared.append((cat, revision, float(image @ vector), threshold))
        found = svc.apply_results(db, photo, prepared)
        db.commit()
        return {
            "status": "success",
            "tags_found": found,
            "rules_checked": len(prepared),
            "model": model,
        }
