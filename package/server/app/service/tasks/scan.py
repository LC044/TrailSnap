from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType, DEFAULT_PRIORITIES
from typing import Any, List, Dict, Set, Optional
import asyncio
import logging
import os
import re
import concurrent.futures
from sqlalchemy.orm import Session

from app.db.models.task import Task, TaskStatus
from app.db.models.photo import Photo, FileType
from app.db.models.index_log import IndexLog
from app.db.models.user import User
from app.core.config_manager import config_manager
from app.service.live_photo import live_photo_service
from app.utils.image_loading import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from app.service.disk_budget import disk_budget, media_io

def _compile_folder_patterns(patterns: Optional[List[str]]) -> List[re.Pattern]:
    """Compile valid folder-name exclusion patterns (regex)."""
    compiled = []
    for p in patterns or []:
        if not p:
            continue
        try:
            compiled.append(re.compile(p))
        except re.error:
            pass  # Ignore invalid regex
    return compiled

def _is_folder_excluded(name: str, compiled_patterns: List[re.Pattern]) -> bool:
    """Return True if a folder name matches any compiled exclusion pattern."""
    if not compiled_patterns:
        return False
    for cp in compiled_patterns:
        if cp.search(name):
            return True
    return False

@media_io('path')
def scan_directory_recursive(path: str, exts: Set[str], filter_settings: Optional[Dict] = None, exclude_folder_patterns: Optional[List[re.Pattern]] = None, *, recursive: bool = True, strict: bool = False) -> Set[str]:
    found = set()
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file(follow_symlinks=False):
                    if os.path.splitext(entry.name)[1].lower() in exts:
                        # Apply filters
                        if filter_settings and filter_settings.get('enable'):
                            # Filename patterns
                            patterns = filter_settings.get('filename_patterns', [])
                            should_skip = False
                            for pattern in patterns:
                                if not pattern:
                                    continue
                                try:
                                    if re.search(pattern, entry.name):
                                        should_skip = True
                                        break
                                except re.error:
                                    pass # Ignore invalid regex

                            if should_skip:
                                continue

                            # File size
                            min_size = filter_settings.get('min_size_kb', 0) * 1024
                            if min_size > 0 and entry.stat().st_size < min_size:
                                continue

                        found.add(entry.path)
                elif recursive and entry.is_dir(follow_symlinks=False):
                    # Skip excluded folders (e.g. NAS @eaDir / #recycle) regardless of filter enable
                    if _is_folder_excluded(entry.name, exclude_folder_patterns or []):
                        continue
                    found.update(scan_directory_recursive(entry.path, exts, filter_settings, exclude_folder_patterns, strict=strict))
    except OSError:
        from app.service.storage_paths import portable_enabled
        if strict or portable_enabled():
            raise
        pass
    return found

@TaskStrategyFactory.register(TaskType.SCAN_FOLDER)
class ScanFolderStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'

    async def process(self, worker, task: Task, db: Session):
        worker.scan_status['message'] = "Scanning folders..."
        scan_roots = task.payload.get('scan_roots')
        user_id = task.payload.get('user_id')

        users_to_process = []
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                users_to_process.append((user, scan_roots))
        else:
            all_users = db.query(User).all()
            for user in all_users:
                users_to_process.append((user, scan_roots))

        total_new = 0
        total_deleted = 0
        skipped_roots = []

        for user, specific_roots in users_to_process:
            roots = specific_roots
            if not roots:
                config = config_manager.get_user_config(user.id, db)
                roots = config.storage.external_directories
            
            if task.payload.get('reconcile'):
                # Always use the current DB configuration for a full scan,
                # including an empty list (which still needs orphan cleanup).
                from app.service.gallery_sync import lock_user, external_roots, import_allowed, cancel_path_tasks, delete_index
                user = lock_user(db, user.id)
                roots = external_roots(user)
                cancel_path_tasks(db, user.id, lambda path: not import_allowed(user, path))
                orphaned = [p for p in db.query(Photo).filter(Photo.owner_id == user.id).all()
                            if not import_allowed(user, p.file_path)]
                total_deleted += delete_index(db, user.id, orphaned)
                db.commit()
            if not roots:
                continue
            
            res = await self._scan_for_user(worker, db, user, roots)
            total_new += res.get('new_files', 0)
            total_deleted += res.get('deleted_files', 0)
            skipped_roots.extend(res.get('skipped_roots', []))

        result = {'new_files': total_new, 'deleted_files': total_deleted}
        if skipped_roots:
            result['skipped_roots'] = skipped_roots
            worker.scan_status['message'] = f'扫描完成，{len(skipped_roots)} 个目录不可读取，已保留其照片记录'
        return result

    async def _scan_for_user(self, worker, db: Session, user: User, scan_roots: List[str]) -> Dict[str, Any]:
        from app.service.gallery_sync import contains, external_roots, lock_user, path_key, cancel_path_tasks
        EXTS = set(IMAGE_EXTENSIONS + VIDEO_EXTENSIONS)
        loop = asyncio.get_running_loop()
        logging.info(f"Scanning roots for user {user.id}: {scan_roots}")

        # Read filter from merged config so defaults (e.g. excluded NAS folders) always apply
        merged_config = config_manager.get_user_config(user.id, db)
        filter_config = merged_config.filter.model_dump()
        exclude_folder_patterns = _compile_folder_patterns(filter_config.get('exclude_folders'))

        def parallel_scan_wrapper():
            found_files = set()
            readable = []
            skipped = []
            roots = sorted(set(os.path.abspath(root) for root in scan_roots), key=len)
            unique_roots = []
            for root in roots:
                normalized = os.path.normcase(root)
                if not any(normalized == os.path.normcase(parent) or normalized.startswith(os.path.normcase(parent).rstrip(os.sep) + os.sep) for parent in unique_roots):
                    unique_roots.append(root)
            for root in unique_roots:
                try:
                    # Treat a failed subtree as a failed root. Never diff an
                    # incomplete listing against DB records as if it were empty.
                    root_files = scan_directory_recursive(root, EXTS, filter_config, exclude_folder_patterns, recursive=False, strict=True)
                    work_items = []
                    with os.scandir(root) as it:
                        for entry in it:
                            if entry.is_dir(follow_symlinks=False):
                                # Skip excluded folders at the top level too
                                if _is_folder_excluded(entry.name, exclude_folder_patterns):
                                    continue
                                work_items.append(entry.path)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=disk_budget.limit) as executor:
                        futures = [executor.submit(scan_directory_recursive, item, EXTS, filter_config, exclude_folder_patterns, strict=True) for item in set(work_items)]
                        for future in concurrent.futures.as_completed(futures):
                            root_files.update(future.result())
                    found_files.update(root_files)
                    readable.append(root)
                except OSError as error:
                    logging.warning('Gallery scan skipped %s: %s', root, error)
                    skipped.append({'path': root, 'reason': str(error)})
            return found_files, readable, skipped

        files_on_disk, readable, skipped = await loop.run_in_executor(None, parallel_scan_wrapper)

        # Removal may happen while filesystem work runs. Revalidate before any
        # enqueue or deletion, and release the lock before more filesystem work.
        user = lock_user(db, user.id)
        current_roots = external_roots(user)
        scan_roots = [root for root in readable if any(contains(allowed, root) for allowed in current_roots)]
        files_on_disk = {path for path in files_on_disk if any(contains(root, path) for root in scan_roots)}
        if not scan_roots:
            db.commit()
            return {'new_files': 0, 'deleted_files': 0, 'skipped_roots': skipped}

        existing_files, live_photo_to_add = self._get_existing_files(db, str(user.id), scan_roots)
        
        # Determine new and deleted
        disk_keys = {path_key(path) for path in files_on_disk}
        existing_keys = {path_key(path) for path in existing_files}
        new_files = {path for path in files_on_disk if path_key(path) not in existing_keys}
        deleted_files = {path for path in existing_files if path_key(path) not in disk_keys}

        for lp in live_photo_to_add:
            if lp.endswith('.jpg'):
                deleted_files.add(lp[:-3] + 'mp4')
                new_files.add(lp[:-3] + 'mp4')
            elif lp.endswith('.mp4'):
                deleted_files.add(lp[:-3] + 'jpg')
                new_files.add(lp[:-3] + 'jpg')
            if lp.endswith('.HEIC'):
                deleted_files.add(lp[:-4] + 'MOV')
                new_files.add(lp[:-4] + 'MOV')
            elif lp.endswith('.MOV'):
                deleted_files.add(lp[:-3] + 'HEIC')
                new_files.add(lp[:-3] + 'HEIC')
            new_files.add(lp)
            deleted_files.add(lp)

        logging.info(f"Scan result for user {user.id}: {len(new_files)} new, {len(deleted_files)} deleted")
        worker.scan_status['message'] = f"Found {len(new_files)} new, {len(deleted_files)} deleted"
        worker.scan_status['total_files'] += len(new_files)

        # Cancel pending imports for missing/filtered files before releasing the
        # DB lock; completion also rechecks the filesystem and configured roots.
        cancel_path_tasks(db, user.id, lambda path: any(contains(root, path) for root in scan_roots) and path_key(path) not in disk_keys)
        db.commit()
        self._handle_deleted_files(str(user.id), deleted_files, db, worker)
        await self._create_tasks_for_new_files(str(user.id), new_files, loop, db)

        result = {'new_files': len(new_files), 'deleted_files': len(deleted_files)}
        if skipped:
            result['skipped_roots'] = skipped
        return result

    def _get_existing_files(self, db: Session, user_id: str, scan_roots: List[str]) -> tuple[Set[str], Set[str]]:
        existing_files = set()
        live_photo_to_add = set()

        query = db.query(Photo.file_path, Photo.file_type).filter(Photo.owner_id == user_id)
        from app.service.gallery_sync import contains
        for p in query.all():
            is_exist = False
            for norm_path in scan_roots:
                if contains(norm_path, p[0]):
                    is_exist = True
            if not is_exist:
                continue
            file_path = os.path.normpath(p[0]).lower()
            if p[1] == FileType.live_photo:
                if file_path.endswith('.jpg'):
                    existing_files.add(p[0][:-3] + 'mp4')
                elif file_path.endswith('.heic'):
                    existing_files.add(p[0][:-4] + 'MOV')
            elif file_path.endswith('.jpg') and (p[0][:-3] + 'mp4' in existing_files):
                live_photo_to_add.add(p[0])
            elif file_path.endswith('.heic') and (p[0][:-4] + 'MOV' in existing_files):
                live_photo_to_add.add(p[0])
            elif file_path.endswith('.mp4') and (p[0][:-3] + 'jpg' in existing_files):
                live_photo_to_add.add(p[0])
            elif file_path.endswith('.mov') and (p[0][:-3] + 'HEIC' in existing_files):
                live_photo_to_add.add(p[0])
            existing_files.add(p[0])
            
        return existing_files, live_photo_to_add

    async def _create_tasks_for_new_files(self, user_id: str, new_files: Set[str], loop: asyncio.AbstractEventLoop, db: Session):
        new_tasks = []
        grouped_files = {}
        for fp in new_files:
            dirname, basename = os.path.split(fp)
            name, ext = os.path.splitext(basename)
            key = (dirname, name)
            if key not in grouped_files:
                grouped_files[key] = {}
            grouped_files[key][ext.lower()] = fp

        processed_paths = set()
        for key, files in grouped_files.items():
            image_path = None
            video_path = None

            if '.heic' in files:
                image_path = files['.heic']
            elif '.heif' in files:
                image_path = files['.heif']
            elif '.jpg' in files:
                image_path = files['.jpg']
            elif '.jpeg' in files:
                image_path = files['.jpeg']

            if '.mov' in files:
                video_path = files['.mov']
            elif '.mp4' in files:
                video_path = files['.mp4']

            is_live = False
            final_video_path = None

            try:
                if image_path and video_path:
                     @media_io('img')
                     def check_live_pair(img, vid):
                         cid1 = live_photo_service.get_content_identifier(img)
                         cid2 = live_photo_service.get_content_identifier(vid)
                         return cid1 and cid2 and cid1 == cid2

                     if await loop.run_in_executor(None, check_live_pair, image_path, video_path):
                         is_live = True
                         final_video_path = video_path

            except Exception as e:
                logging.error(f"Error checking live photo for {image_path}: {e}")

            if is_live:
                new_tasks.append(Task(
                    type=TaskType.PROCESS_BASIC,
                    payload={
                        'file_path': image_path,
                        'live_photo_video_path': final_video_path,
                        'is_live_photo': True,
                        'user_id': user_id
                    },
                    priority=DEFAULT_PRIORITIES[TaskType.PROCESS_BASIC],
                    status=TaskStatus.PENDING
                ))
                processed_paths.add(image_path)
                if final_video_path:
                    processed_paths.add(final_video_path)

            for ext, fp in files.items():
                if fp not in processed_paths:
                    new_tasks.append(Task(
                        type=TaskType.PROCESS_BASIC,
                        payload={'file_path': fp, 'user_id': user_id},
                        priority=DEFAULT_PRIORITIES[TaskType.PROCESS_BASIC],
                        status=TaskStatus.PENDING
                    ))
                    processed_paths.add(fp)

        if new_tasks:
            from app.service.gallery_sync import lock_user, import_allowed, path_key, owned_path_tasks
            chunk_size = 1000
            for i in range(0, len(new_tasks), chunk_size):
                user = lock_user(db, user_id)
                chunk = new_tasks[i:i+chunk_size]
                paths = [t.payload['file_path'] for t in chunk]
                known = {path_key(row[0]) for row in db.query(Photo.file_path).filter(
                    Photo.owner_id == user.id, Photo.file_path.in_(paths)).all()}
                known.update(path_key(t.payload['file_path']) for t in owned_path_tasks(db, user.id).filter(
                    Task.type == TaskType.PROCESS_BASIC,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
                ).all() if (t.payload or {}).get('file_path'))
                accepted = []
                for task in chunk:
                    path = task.payload['file_path']
                    if import_allowed(user, path) and path_key(path) not in known:
                        task.owner_id = user.id
                        task.payload = dict(task.payload, external_scan=True)
                        accepted.append(task)
                        known.add(path_key(path))
                db.bulk_save_objects(accepted)
                db.commit()

    def _handle_deleted_files(self, user_id: str, deleted_files: Set[str], db: Session, worker):
        if not deleted_files:
            return
            
        deleted_list = list(deleted_files)
        chunk_size = 500
        for i in range(0, len(deleted_list), chunk_size):
            chunk = deleted_list[i:i+chunk_size]
            photos_to_delete = db.query(Photo).filter(Photo.owner_id == user_id, Photo.file_path.in_(chunk)).all()
            photo_ids_to_delete = []
            for ph in photos_to_delete:
                photo_ids_to_delete.append(ph.id)
                db.add(IndexLog(action='deleted', file_path=ph.file_path, photo_id=ph.id, owner_id=user_id))
        
            if photo_ids_to_delete:
                from app.crud.photo import batch_delete_photos_db
                batch_delete_photos_db(db, photo_ids_to_delete, is_delete_file=False, user_id=user_id)
            
            db.commit()
            worker.scan_status['deleted'] += len(photos_to_delete)

def release_resources():
    pass
