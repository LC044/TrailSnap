#!/usr/bin/env python
"""Frozen entry point used by the TrailSnap desktop shell."""

from __future__ import annotations

import argparse
from contextlib import closing
import multiprocessing
import os
import signal
import secrets
import threading
import time
from pathlib import Path


DESKTOP_SCHEMA_REVISION = "portable_sqlite_0020"

# The desktop UI talks to the sidecar exactly like the production web UI talks
# to nginx: all API calls start with /api. The bundled server has no reverse
# proxy to strip that prefix, so expose the FastAPI app under its public path.
DESKTOP_API_ROOT_PATH = "/api"


def _apply_desktop_api_prefix(app) -> None:
    """Let the local sidecar accept the same /api paths as the public proxy."""

    app.root_path = DESKTOP_API_ROOT_PATH


def _database_is_current(database_path: Path) -> bool:
    """Check the tiny Alembic version table without importing Alembic."""
    if not database_path.is_file():
        return False
    import sqlite3

    try:
        with closing(sqlite3.connect(database_path)) as connection:
            row = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        return bool(row and row[0] == DESKTOP_SCHEMA_REVISION)
    except sqlite3.Error:
        return False


def _prepare_desktop_database() -> None:
    """Upgrade the local SQLite database before importing the API app."""

    data_dir = Path(os.environ["TS_DATA_DIR"]).resolve()
    if (data_dir.parent / 'library.json').exists() and not (data_dir / 'trailsnap.sqlite').is_file():
        raise RuntimeError('已有图库的数据库缺失，请连接原磁盘或从 backups 恢复；不会创建空库替代')
    # Earlier desktop builds used ./data under a cwd already named data.
    # Preserve their system preferences and JWT secret when fixing that layout.
    import shutil
    legacy_config = data_dir / "data/system_config.json"
    config_path = data_dir / "system_config.json"
    if legacy_config.is_file() and not config_path.exists():
        shutil.copy2(legacy_config, config_path)
    if os.getenv("TS_DESKTOP_PORTABLE") == "1" and not (data_dir.parent / "library.json").exists():
        import json
        from app.utils.portable_library import write_json
        settings = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        settings.setdefault("security", {})["secret_key"] = secrets.token_hex(32)
        write_json(config_path, settings)
    session_secret = secrets.token_urlsafe(32)
    os.environ["TS_DESKTOP_SESSION_SECRET"] = session_secret
    secret_file = data_dir / "desktop_session.secret"
    secret_file.write_text(session_secret, encoding="utf-8")
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass
    database_path = data_dir / "trailsnap.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    os.environ["TS_DB_URL"] = database_url
    os.environ['RAILWAY_DB_URL'] = f"sqlite:///{(data_dir / 'railway.sqlite').as_posix()}"

    # Most launches are already at the bundled schema head. Avoid importing
    # Alembic and scanning migration modules on that hot path.
    if not _database_is_current(database_path):
        from alembic import command
        from alembic.config import Config
        from app.core.paths import BUNDLE_ROOT

        config = Config()
        config.set_main_option("script_location", str(Path(BUNDLE_ROOT) / "alembic_sqlite"))
        config.set_main_option("sqlalchemy.url", database_url)
        from alembic.script import ScriptDirectory
        scripts = ScriptDirectory.from_config(config)
        if database_path.exists():
            import sqlite3
            with closing(sqlite3.connect(database_path)) as connection:
                try:
                    rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
                except sqlite3.OperationalError:
                    rows = []
            for (revision,) in rows:
                if scripts.get_revision(revision) is None:
                    raise RuntimeError("数据版本高于当前客户端，请使用兼容版本打开")
            from app.utils.portable_library import snapshot_library
            snapshot_library(data_dir.parent, data_dir.parent / "backups" / f"schema-{rows[0][0] if rows else 'unversioned'}")
        command.upgrade(config, "head")

    from app.db.bootstrap import ensure_desktop_admin
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        ensure_desktop_admin(db)
    if os.getenv("TS_DESKTOP_PORTABLE") == "1":
        from app.utils.portable_library import prepare_portable_library
        prepare_portable_library(data_dir.parent)
        from app.service.storage_paths import warm_roots
        with SessionLocal() as db:
            warm_roots(db)


def _watch_parent(parent_pid: int) -> None:
    """Stop an orphaned sidecar after an abnormal desktop-shell exit."""
    import psutil

    while True:
        time.sleep(2)
        if not psutil.pid_exists(parent_pid):
            os.kill(os.getpid(), signal.SIGTERM)
            return


def main() -> None:
    import sys
    # The frozen bootloader ignores PYTHONIOENCODING. Native commands decode
    # JSON and progress as UTF-8, including Chinese paths and error messages.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description="TrailSnap desktop API sidecar")
    parser.add_argument("--port", type=int)
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--migrate-data", nargs=2, metavar=("SOURCE", "TARGET"))
    parser.add_argument("--snapshot-data", nargs=2, metavar=("ROOT", "SNAPSHOT"))
    parser.add_argument("--restore-data", nargs=2, metavar=("ROOT", "SNAPSHOT"))
    parser.add_argument("--prepare-portable", metavar="ROOT")
    parser.add_argument("--convert-portable", nargs=4, metavar=("SOURCE", "TARGET", "PROGRAM", "LAUNCHER"))
    parser.add_argument("--preview-portable", metavar="ROOT")
    parser.add_argument("--copy-external", action="store_true")
    parser.add_argument('--install-layout', nargs=2, metavar=('DIRECTORY', 'VERSION'))
    parser.add_argument('--discover-old-data', nargs=2)
    parser.add_argument('--import-space', nargs=4)
    parser.add_argument('--cleanup-import', nargs=2)
    parser.add_argument('--automatic-upgrade', nargs=2, metavar=('ROOT', 'ACTION'))
    args = parser.parse_args()
    if args.automatic_upgrade:
        import json
        from app.utils.automatic_upgrade import automatic_upgrade
        try:
            result = automatic_upgrade(*args.automatic_upgrade)
        except Exception as error:
            print(f'自动迁移未完成：{error}。原数据保留，请检查日志后重试。', file=sys.stderr)
            raise SystemExit(1) from None
        print(json.dumps({'phase': result['phase']}, ensure_ascii=False))
        return
    if args.discover_old_data or args.import_space or args.cleanup_import:
        import json
        import sys
        from app.utils.desktop_import import discover_libraries, conversion_space, cleanup_staging
        try:
            if args.discover_old_data:
                local = os.getenv('LOCALAPPDATA')
                result = discover_libraries(*(Path(p) for p in args.discover_old_data), Path(local) if local else None)
            elif args.import_space:
                source, target, program, copy = args.import_space
                result = conversion_space(Path(source), Path(target), Path(program), copy == '1')
            else:
                cleanup_staging(Path(args.cleanup_import[0]), args.cleanup_import[1])
                result = {'cleaned': True}
        except (ValueError, OSError, __import__('sqlite3').Error) as error:
            print(f'检查或清理失败：{error}', file=sys.stderr)
            raise SystemExit(1) from None
        print(json.dumps(result, ensure_ascii=False))
        return

    if args.install_layout:
        from app.utils.desktop_layout import finalize_install
        print(finalize_install(Path(args.install_layout[0]), args.install_layout[1]))
        return

    if args.parent_pid:
        from app.utils.process_lifecycle import bind_desktop_process_tree

        bind_desktop_process_tree()
        threading.Thread(
            target=_watch_parent,
            args=(args.parent_pid,),
            name="DesktopParentWatch",
            daemon=True,
        ).start()

    if args.preview_portable or args.convert_portable:
        import json
        import sqlite3
        import sys
        from app.utils.portable_conversion import preview_conversion, convert_to_portable
        try:
            if args.preview_portable:
                result = preview_conversion(Path(args.preview_portable))
            else:
                result = convert_to_portable(*(Path(item) for item in args.convert_portable), copy_external=args.copy_external)
        except Exception as error:
            operation = '检查旧图库失败' if args.preview_portable else '复制图库失败'
            print(f'{operation}：{error}', file=sys.stderr)
            raise SystemExit(1) from None
        print(json.dumps(result,ensure_ascii=False))
        return

    if args.snapshot_data or args.restore_data:
        from app.utils.portable_library import snapshot_library, restore_library
        action = snapshot_library if args.snapshot_data else restore_library
        action(*(Path(path) for path in (args.snapshot_data or args.restore_data)))
        return
    if args.prepare_portable:
        root = Path(args.prepare_portable).resolve(strict=True)
        os.environ.update(TS_DESKTOP="1", TS_DESKTOP_PORTABLE="1", TS_DESKTOP_ROOT=str(root), TS_DATA_DIR=str(root / "data"))
        _prepare_desktop_database()
        return

    if args.migrate_data:
        from app.utils.desktop_data_migration import migrate_data_directory

        try:
            migrate_data_directory(*(Path(path) for path in args.migrate_data), skip_browser_state=True)
        except Exception as exc:
            import sys
            print(f"数据迁移失败：{exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return
    if args.port is None:
        parser.error("--port is required when starting the server")

    try:
        _prepare_desktop_database()
    except Exception as error:
        from app.utils.portable_library import write_json
        write_json(Path(os.environ['TS_DATA_DIR']).parent / 'startup-error.json', {
            'message': f'图库初始化失败：{error}。请检查磁盘和写入权限；升级前备份保存在数据目录的 backups 中。',
            'detail': repr(error),
        })
        raise

    from app.utils.desktop_network import lan_urls
    os.environ["TS_DESKTOP_PORT"] = str(args.port)
    urls = lan_urls(args.port)
    if urls:
        os.environ.setdefault("TRAILSNAP_PUBLIC_URL", urls[0])

    import uvicorn
    from main import app

    _apply_desktop_api_prefix(app)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=args.port,
            log_level=os.environ.get("TS_DESKTOP_LOG_LEVEL", "info"),
            access_log=False,
            timeout_keep_alive=60,
            timeout_graceful_shutdown=15,
        )
    )
    app.state.desktop_server = server
    server.run()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
