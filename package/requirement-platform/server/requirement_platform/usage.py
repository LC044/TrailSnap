"""cc-switch SQL 备份解析与导入，以及用量统计查询。

导入流程：
1. 上传的 .sql 文件读入内存，SHA-256 去重（重复文件直接拒绝）。
2. 在内存 SQLite（:memory:）中 executescript 执行，通过 set_authorizer
   白名单只放行建表/插入语句，阻止 ATTACH / PRAGMA 等危险操作。
3. 从内存库提取 proxy_request_logs / usage_daily_rollups / providers 三张表，
   按设备写入平台库。
4. 同设备二次导入时，删除日期已被新 rollup 覆盖的旧明细，避免双计数。

统计查询：明细与日聚合 UNION ALL 合并（cc-switch 导出文件内两层日期不重叠）。
"""
import hashlib
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import manager
from .usage_models import (
    UsageDailyRollup,
    UsageDevice,
    UsageImport,
    UsageProvider,
    UsageRequestLog,
)

logger = logging.getLogger(__name__)

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_IMPORT_BYTES = 64 * 1024 * 1024  # 64MB


# ---------------------------------------------------------------------------
# 解析层：内存 SQLite
# ---------------------------------------------------------------------------

def _authorizer(action_code: int, arg1: str | None, _arg2: str | None, _db: str, _trigger: str) -> int:
    """内存库内的最小防线：拒绝 ATTACH/DETACH、任意 UPDATE/DELETE。

    内存库自身无法落盘，唯一的越界通道是 ATTACH（可指向宿主文件系统上的文件）。
    CREATE TABLE 内部会以 UPDATE 写 sqlite_master 元数据，属正常 DDL，放行。
    sqlite_sequence 是 AUTOINCREMENT 计数器元数据，导出脚本会 DELETE 它，放行。
    注：sqlite3 常量表里 SQLITE_INSERT 与 SQLITE_TOOBIG 同值（18），
    因此对 INSERT 不做表级拦截，靠 ATTACH/UPDATE/DELETE 三条防线兜住。
    """
    if action_code in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    if action_code == sqlite3.SQLITE_UPDATE and arg1 not in ("sqlite_master",):
        return sqlite3.SQLITE_DENY
    if action_code == sqlite3.SQLITE_DELETE and arg1 not in ("sqlite_sequence",):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _parse_export(raw: bytes) -> tuple[sqlite3.Connection, int]:
    """把导出 SQL 执行进内存库，返回 (connection, user_version)。"""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="文件不是 UTF-8 编码的 cc-switch 导出") from exc
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("PRAGMA user_version=0")
        # executescript 前设置 authorizer，拦截语句内部的 ATTACH 等
        conn.set_authorizer(_authorizer)
        conn.executescript(text)
        conn.set_authorizer(None)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        return conn, version
    except sqlite3.Error as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=f"SQL 解析失败：{exc}") from exc


def _fetch_dict_rows(conn: sqlite3.Connection, table: str, columns: list[str]) -> list[dict]:
    names = ",".join(f'"{col}"' for col in columns)
    try:
        cursor = conn.execute(f"SELECT {names} FROM {table}")
    except sqlite3.OperationalError:
        return []
    keys = [desc[0] for desc in cursor.description]
    return [dict(zip(keys, row)) for row in cursor.fetchall()]


def _num(value, default=0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_local_date(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc).astimezone(TZ_SHANGHAI).date().isoformat()


# ---------------------------------------------------------------------------
# 导入层
# ---------------------------------------------------------------------------

@dataclass
class ImportStats:
    detail_rows: int = 0
    detail_new: int = 0
    detail_dup: int = 0
    detail_aged_out: int = 0
    rollup_rows: int = 0
    rollup_upserted: int = 0
    date_min: str | None = None
    date_max: str | None = None


def _get_or_create_device(db: Session, label: str) -> UsageDevice:
    device = db.query(UsageDevice).filter(UsageDevice.label == label).first()
    if device:
        return device
    device = UsageDevice(id=str(uuid.uuid4()), label=label)
    db.add(device)
    db.flush()
    return device


def import_ccswitch_export(db: Session, *, label: str, file_name: str, raw: bytes, imported_by: str | None) -> dict:
    """解析并导入一份 cc-switch 导出 SQL。返回导入统计。"""
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 64MB 限制")
    label = label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="设备名称不能为空")
    sha256 = hashlib.sha256(raw).hexdigest()

    existing = db.query(UsageImport).filter(UsageImport.file_sha256 == sha256).first()
    if existing:
        raise HTTPException(status_code=409, detail="该文件已导入过（内容相同），已跳过")

    conn, user_version = _parse_export(raw)
    try:
        device = _get_or_create_device(db, label)
        stats = ImportStats()

        # --- providers：仅取 id/name/app_type/category，绝不碰 settings_config ---
        provider_rows = _fetch_dict_rows(conn, "providers", ["id", "app_type", "name", "category"])
        existing_provider_keys = {
            (row.device_id, row.provider_id) for row in
            db.query(UsageProvider.device_id, UsageProvider.provider_id).filter(UsageProvider.device_id == device.id)
        }
        for row in provider_rows:
            key = (device.id, row["id"])
            if key in existing_provider_keys:
                continue
            db.add(UsageProvider(
                id=str(uuid.uuid4()), device_id=device.id, provider_id=row["id"],
                app_type=row["app_type"] or "", name=row["name"] or row["id"], category=row.get("category"),
            ))
            existing_provider_keys.add(key)

        # --- 日聚合：同键 upsert，request_count 更大者胜 ---
        rollup_rows = _fetch_dict_rows(
            conn, "usage_daily_rollups",
            ["date", "app_type", "provider_id", "model", "request_model", "pricing_model",
             "request_count", "success_count", "input_tokens", "output_tokens",
             "cache_read_tokens", "cache_creation_tokens", "total_cost_usd"],
        )
        rollup_index: dict[tuple, UsageDailyRollup] = {
            (row.device_id, row.date, row.app_type, row.provider_id, row.model, row.request_model, row.pricing_model): row
            for row in db.query(UsageDailyRollup).filter(UsageDailyRollup.device_id == device.id)
        }
        for row in rollup_rows:
            key = (device.id, row["date"], row["app_type"], row["provider_id"], row["model"],
                   row["request_model"] or "", row["pricing_model"] or "")
            current = rollup_index.get(key)
            if current is not None:
                stats.rollup_rows += 1
                if int(row["request_count"] or 0) > current.request_count:
                    current.request_count = int(row["request_count"] or 0)
                    current.success_count = int(row["success_count"] or 0)
                    current.input_tokens = int(row["input_tokens"] or 0)
                    current.output_tokens = int(row["output_tokens"] or 0)
                    current.cache_read_tokens = int(row["cache_read_tokens"] or 0)
                    current.cache_creation_tokens = int(row["cache_creation_tokens"] or 0)
                    current.total_cost_usd = _num(row["total_cost_usd"])
                continue
            entry = UsageDailyRollup(
                id=str(uuid.uuid4()), device_id=device.id, date=row["date"], app_type=row["app_type"],
                provider_id=row["provider_id"], model=row["model"], request_model=row["request_model"] or "",
                pricing_model=row["pricing_model"] or "", request_count=int(row["request_count"] or 0),
                success_count=int(row["success_count"] or 0), input_tokens=int(row["input_tokens"] or 0),
                output_tokens=int(row["output_tokens"] or 0), cache_read_tokens=int(row["cache_read_tokens"] or 0),
                cache_creation_tokens=int(row["cache_creation_tokens"] or 0),
                total_cost_usd=_num(row["total_cost_usd"]),
            )
            db.add(entry)
            rollup_index[key] = entry
            stats.rollup_rows += 1
            stats.rollup_upserted += 1

        # --- 明细：request_id 全局去重 ---
        log_rows = _fetch_dict_rows(
            conn, "proxy_request_logs",
            ["request_id", "provider_id", "app_type", "model", "request_model",
             "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens",
             "input_cost_usd", "output_cost_usd", "cache_read_cost_usd", "cache_creation_cost_usd",
             "total_cost_usd", "latency_ms", "status_code", "session_id", "data_source", "created_at"],
        )
        file_dates: list[str] = [row["date"] for row in rollup_rows if row.get("date")]
        new_rollup_max = max(file_dates) if file_dates else None
        aged_out = 0
        if new_rollup_max:
            # 该日期及之前的旧明细已被本次 rollup 覆盖，删除防止双计数
            aged_out = db.query(UsageRequestLog).filter(
                UsageRequestLog.device_id == device.id,
                UsageRequestLog.created_date <= new_rollup_max,
            ).delete(synchronize_session=False)
            db.flush()

        existing_ids = {
            rid for (rid,) in db.query(UsageRequestLog.request_id).filter(
                UsageRequestLog.request_id.in_([row["request_id"] for row in log_rows])
            )
        } if log_rows else set()
        import_record = UsageImport(
            id=str(uuid.uuid4()), device_id=device.id, file_name=file_name[:255], file_sha256=sha256,
            file_size=len(raw), user_version=user_version, imported_by=imported_by,
        )
        db.add(import_record)
        db.flush()
        for row in log_rows:
            stats.detail_rows += 1
            if row["request_id"] in existing_ids:
                stats.detail_dup += 1
                continue
            epoch = int(row["created_at"] or 0)
            db.add(UsageRequestLog(
                request_id=row["request_id"], device_id=device.id, import_id=import_record.id,
                provider_id=row["provider_id"] or "", app_type=row["app_type"] or "",
                model=row["model"] or "", request_model=row.get("request_model"),
                input_tokens=int(row["input_tokens"] or 0), output_tokens=int(row["output_tokens"] or 0),
                cache_read_tokens=int(row["cache_read_tokens"] or 0),
                cache_creation_tokens=int(row["cache_creation_tokens"] or 0),
                input_cost_usd=_num(row["input_cost_usd"]), output_cost_usd=_num(row["output_cost_usd"]),
                cache_read_cost_usd=_num(row["cache_read_cost_usd"]),
                cache_creation_cost_usd=_num(row["cache_creation_cost_usd"]),
                total_cost_usd=_num(row["total_cost_usd"]),
                latency_ms=int(row["latency_ms"] or 0), status_code=int(row["status_code"] or 0),
                session_id=row.get("session_id"), data_source=row["data_source"] or "proxy",
                created_at=epoch, created_date=_to_local_date(epoch),
            ))
            existing_ids.add(row["request_id"])
            stats.detail_new += 1
        stats.detail_aged_out = int(aged_out)

        # 汇总日期范围（rollup + 明细）
        all_dates = [row["date"] for row in rollup_rows if row.get("date")]
        all_dates.extend(
            _to_local_date(int(row["created_at"] or 0)) for row in log_rows if row.get("created_at")
        )
        if all_dates:
            stats.date_min = min(all_dates)
            stats.date_max = max(all_dates)

        import_record.detail_rows = stats.detail_rows
        import_record.detail_new = stats.detail_new
        import_record.detail_dup = stats.detail_dup
        import_record.detail_aged_out = stats.detail_aged_out
        import_record.rollup_rows = stats.rollup_rows
        import_record.rollup_upserted = stats.rollup_upserted
        import_record.date_min = stats.date_min
        import_record.date_max = stats.date_max
        device.last_import_at = datetime.now(timezone.utc)
        db.commit()
        return {
            "import_id": import_record.id, "device_id": device.id, "device_label": device.label,
            "file_name": file_name, "file_sha256": sha256, "user_version": user_version,
            "detail_rows": stats.detail_rows, "detail_new": stats.detail_new,
            "detail_dup": stats.detail_dup, "detail_aged_out": stats.detail_aged_out,
            "rollup_rows": stats.rollup_rows, "rollup_upserted": stats.rollup_upserted,
            "date_min": stats.date_min, "date_max": stats.date_max,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("cc-switch import failed")
        raise HTTPException(status_code=500, detail="导入失败，请检查文件格式")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 查询层：明细 + 日聚合 UNION ALL
# ---------------------------------------------------------------------------

def _date_range(db: Session, date_from: str | None, date_to: str | None) -> tuple[str | None, str | None]:
    if date_from and date_to:
        return date_from, date_to
    row = db.query(func.min(UsageDailyRollup.date), func.max(UsageDailyRollup.date)).first()
    log_row = db.query(func.min(UsageRequestLog.created_date), func.max(UsageRequestLog.created_date)).first()
    candidates = [value for value in (row[0], log_row[0]) if value]
    max_values = [value for value in (row[1], log_row[1]) if value]
    overall_min = min(candidates) if candidates else None
    overall_max = max(max_values) if max_values else None
    return date_from or overall_min, date_to or overall_max


def usage_overview(
    db: Session, date_from: str | None, date_to: str | None,
    model: str | None = None, app_type: str | None = None,
) -> dict:
    date_from, date_to = _date_range(db, date_from, date_to)
    log_filter = [UsageRequestLog.created_date >= date_from] if date_from else []
    log_filter += [UsageRequestLog.created_date <= date_to] if date_to else []
    rollup_filter = [UsageDailyRollup.date >= date_from] if date_from else []
    rollup_filter += [UsageDailyRollup.date <= date_to] if date_to else []
    dim_log_filter, dim_rollup_filter = _dim_filters(model, app_type)
    log_filter += dim_log_filter
    rollup_filter += dim_rollup_filter

    def _sum_pair(column_log, column_rollup) -> float:
        a = db.query(func.coalesce(func.sum(column_log), 0.0)).filter(*log_filter).scalar()
        b = db.query(func.coalesce(func.sum(column_rollup), 0.0)).filter(*rollup_filter).scalar()
        return float(a or 0) + float(b or 0)

    log_count = db.query(func.count(UsageRequestLog.request_id)).filter(*log_filter).scalar() or 0
    rollup_count = db.query(func.coalesce(func.sum(UsageDailyRollup.request_count), 0)).filter(*rollup_filter).scalar() or 0
    total = {
        "requests": int(log_count) + int(rollup_count),
        "input_tokens": int(_sum_pair(UsageRequestLog.input_tokens, UsageDailyRollup.input_tokens)),
        "output_tokens": int(_sum_pair(UsageRequestLog.output_tokens, UsageDailyRollup.output_tokens)),
        "cache_read_tokens": int(_sum_pair(UsageRequestLog.cache_read_tokens, UsageDailyRollup.cache_read_tokens)),
        "cache_creation_tokens": int(_sum_pair(UsageRequestLog.cache_creation_tokens, UsageDailyRollup.cache_creation_tokens)),
        "total_cost_usd": round(_sum_pair(UsageRequestLog.total_cost_usd, UsageDailyRollup.total_cost_usd), 6),
        "date_from": date_from,
        "date_to": date_to,
    }

    def _breakdown(dimension: str) -> list[dict]:
        """按维度聚合（明细按行数计请求，rollup 按 request_count 计）。"""
        log_dim = getattr(UsageRequestLog, dimension)
        rollup_dim = getattr(UsageDailyRollup, dimension)
        log_rows = db.query(
            log_dim.label("key"),
            func.count(UsageRequestLog.request_id).label("requests"),
            func.sum(UsageRequestLog.input_tokens).label("input_tokens"),
            func.sum(UsageRequestLog.output_tokens).label("output_tokens"),
            func.sum(UsageRequestLog.cache_read_tokens).label("cache_read_tokens"),
            func.sum(UsageRequestLog.cache_creation_tokens).label("cache_creation_tokens"),
            func.sum(UsageRequestLog.total_cost_usd).label("total_cost"),
        ).filter(*log_filter).group_by(log_dim).all()
        rollup_rows = db.query(
            rollup_dim.label("key"),
            func.sum(UsageDailyRollup.request_count).label("requests"),
            func.sum(UsageDailyRollup.input_tokens).label("input_tokens"),
            func.sum(UsageDailyRollup.output_tokens).label("output_tokens"),
            func.sum(UsageDailyRollup.cache_read_tokens).label("cache_read_tokens"),
            func.sum(UsageDailyRollup.cache_creation_tokens).label("cache_creation_tokens"),
            func.sum(UsageDailyRollup.total_cost_usd).label("total_cost"),
        ).filter(*rollup_filter).group_by(rollup_dim).all()

        provider_names = {
            row.provider_id: row.name for row in db.query(UsageProvider.provider_id, UsageProvider.name)
        }
        # cc-switch 内部数据源 ID 的友好名称（providers 表里没有它们的记录）
        provider_names.update({
            "_session": "Claude 会话日志",
            "_codex_session": "Codex 会话日志",
        })
        merged: dict[str, dict] = {}
        for key, requests, input_t, output_t, cache_r, cache_c, cost in list(log_rows) + list(rollup_rows):
            entry = merged.setdefault(key, {
                "key": key, "requests": 0, "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_creation_tokens": 0, "total_cost_usd": 0.0,
            })
            entry["requests"] += int(requests or 0)
            entry["input_tokens"] += int(input_t or 0)
            entry["output_tokens"] += int(output_t or 0)
            entry["cache_read_tokens"] += int(cache_r or 0)
            entry["cache_creation_tokens"] += int(cache_c or 0)
            entry["total_cost_usd"] += float(cost or 0)
        items = sorted(merged.values(), key=lambda item: -item["total_cost_usd"])
        for item in items:
            item["total_cost_usd"] = round(item["total_cost_usd"], 6)
            if dimension == "provider_id":
                item["label"] = provider_names.get(item["key"], item["key"] or "未知")
        return items

    # 按设备聚合（明细 + rollup 各自 group by device_id 后合并）
    log_device_rows = db.query(
        UsageRequestLog.device_id.label("key"),
        func.count(UsageRequestLog.request_id).label("requests"),
        func.sum(UsageRequestLog.input_tokens).label("input_tokens"),
        func.sum(UsageRequestLog.output_tokens).label("output_tokens"),
        func.sum(UsageRequestLog.cache_read_tokens).label("cache_read_tokens"),
        func.sum(UsageRequestLog.cache_creation_tokens).label("cache_creation_tokens"),
        func.sum(UsageRequestLog.total_cost_usd).label("total_cost"),
    ).filter(*log_filter).group_by(UsageRequestLog.device_id).all()
    rollup_device_rows = db.query(
        UsageDailyRollup.device_id.label("key"),
        func.sum(UsageDailyRollup.request_count).label("requests"),
        func.sum(UsageDailyRollup.input_tokens).label("input_tokens"),
        func.sum(UsageDailyRollup.output_tokens).label("output_tokens"),
        func.sum(UsageDailyRollup.cache_read_tokens).label("cache_read_tokens"),
        func.sum(UsageDailyRollup.cache_creation_tokens).label("cache_creation_tokens"),
        func.sum(UsageDailyRollup.total_cost_usd).label("total_cost"),
    ).filter(*rollup_filter).group_by(UsageDailyRollup.device_id).all()

    devices = db.query(UsageDevice).order_by(UsageDevice.created_at).all()
    device_map = {device.id: {
        "key": device.id, "label": device.label,
        "requests": 0, "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_creation_tokens": 0, "total_cost_usd": 0.0,
    } for device in devices}
    for key, requests, input_t, output_t, cache_r, cache_c, cost in list(log_device_rows) + list(rollup_device_rows):
        entry = device_map.get(key)
        if entry is None:
            continue
        entry["requests"] += int(requests or 0)
        entry["input_tokens"] += int(input_t or 0)
        entry["output_tokens"] += int(output_t or 0)
        entry["cache_read_tokens"] += int(cache_r or 0)
        entry["cache_creation_tokens"] += int(cache_c or 0)
        entry["total_cost_usd"] += float(cost or 0)
    by_device = sorted(device_map.values(), key=lambda item: -item["total_cost_usd"])
    for item in by_device:
        item["total_cost_usd"] = round(item["total_cost_usd"], 6)

    return {
        "total": total,
        "by_model": _breakdown("model"),
        "by_provider": _breakdown("provider_id"),
        "by_app_type": _breakdown("app_type"),
        "by_device": by_device,
        "device_count": len(devices),
    }


def _dim_filters(model: str | None, app_type: str | None) -> tuple[list, list]:
    """返回 (log_filter, rollup_filter)：按模型与应用类型过滤。"""
    log_filter: list = []
    rollup_filter: list = []
    if model:
        log_filter.append(UsageRequestLog.model == model)
        rollup_filter.append(UsageDailyRollup.model == model)
    if app_type:
        log_filter.append(UsageRequestLog.app_type == app_type)
        rollup_filter.append(UsageDailyRollup.app_type == app_type)
    return log_filter, rollup_filter


def usage_filters(db: Session) -> dict:
    """筛选下拉的可选值：全部模型与应用类型。"""
    models = {row[0] for row in db.query(UsageRequestLog.model).distinct()} | {
        row[0] for row in db.query(UsageDailyRollup.model).distinct()
    }
    app_types = {row[0] for row in db.query(UsageRequestLog.app_type).distinct()} | {
        row[0] for row in db.query(UsageDailyRollup.app_type).distinct()
    }
    return {
        "models": sorted(value for value in models if value),
        "app_types": sorted(value for value in app_types if value),
    }


def usage_daily(
    db: Session, date_from: str | None, date_to: str | None,
    model: str | None = None, app_type: str | None = None,
) -> list[dict]:
    """合并的日序列（明细按上海时区日期归并 + rollup 直接求和），缺日期补零。"""
    date_from, date_to = _date_range(db, date_from, date_to)
    if not date_from or not date_to:
        return []
    dim_log_filter, dim_rollup_filter = _dim_filters(model, app_type)
    log_rows = db.query(
        UsageRequestLog.created_date.label("day"),
        func.count(UsageRequestLog.request_id).label("requests"),
        func.sum(UsageRequestLog.input_tokens).label("input_tokens"),
        func.sum(UsageRequestLog.output_tokens).label("output_tokens"),
        func.sum(UsageRequestLog.cache_read_tokens).label("cache_read_tokens"),
        func.sum(UsageRequestLog.cache_creation_tokens).label("cache_creation_tokens"),
        func.sum(UsageRequestLog.total_cost_usd).label("total_cost"),
    ).filter(
        UsageRequestLog.created_date >= date_from, UsageRequestLog.created_date <= date_to,
        *dim_log_filter,
    ).group_by(UsageRequestLog.created_date).all()
    rollup_rows = db.query(
        UsageDailyRollup.date.label("day"),
        func.sum(UsageDailyRollup.request_count).label("requests"),
        func.sum(UsageDailyRollup.input_tokens).label("input_tokens"),
        func.sum(UsageDailyRollup.output_tokens).label("output_tokens"),
        func.sum(UsageDailyRollup.cache_read_tokens).label("cache_read_tokens"),
        func.sum(UsageDailyRollup.cache_creation_tokens).label("cache_creation_tokens"),
        func.sum(UsageDailyRollup.total_cost_usd).label("total_cost"),
    ).filter(
        UsageDailyRollup.date >= date_from, UsageDailyRollup.date <= date_to,
        *dim_rollup_filter,
    ).group_by(UsageDailyRollup.date).all()

    merged: dict[str, dict] = {}
    for day, requests, input_t, output_t, cache_r, cache_c, cost in list(log_rows) + list(rollup_rows):
        entry = merged.setdefault(day, {
            "date": day, "requests": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_creation_tokens": 0, "total_cost_usd": 0.0,
        })
        entry["requests"] += int(requests or 0)
        entry["input_tokens"] += int(input_t or 0)
        entry["output_tokens"] += int(output_t or 0)
        entry["cache_read_tokens"] += int(cache_r or 0)
        entry["cache_creation_tokens"] += int(cache_c or 0)
        entry["total_cost_usd"] += float(cost or 0)

    days: list[dict] = []
    start = datetime.strptime(date_from, "%Y-%m-%d").date()
    end = datetime.strptime(date_to, "%Y-%m-%d").date()
    span = (end - start).days
    if span > 400:  # 防御：超大范围不逐日补零
        return sorted(merged.values(), key=lambda item: item["date"])
    offset = start
    while offset <= end:
        key = offset.isoformat()
        entry = merged.get(key)
        if entry:
            entry["total_cost_usd"] = round(entry["total_cost_usd"], 6)
            days.append(entry)
        else:
            days.append({
                "date": key, "requests": 0, "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_creation_tokens": 0, "total_cost_usd": 0.0,
            })
        offset += timedelta(days=1)
    return days


# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------

async def upload_usage_import(
    file: UploadFile = File(...),
    device_label: str = Form(...),
    actor: User = Depends(manager),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    result = import_ccswitch_export(
        db, label=device_label, file_name=file.filename or "export.sql", raw=raw, imported_by=actor.id,
    )
    return {"code": 0, "msg": "success", "data": result}


def list_usage_imports(actor: User = Depends(manager), db: Session = Depends(get_db)):
    imports = db.query(UsageImport).order_by(UsageImport.imported_at.desc()).all()
    devices = {device.id: device.label for device in db.query(UsageDevice).all()}
    return {"code": 0, "msg": "success", "data": [{
        "id": row.id, "device_id": row.device_id, "device_label": devices.get(row.device_id, "?"),
        "file_name": row.file_name, "file_sha256": row.file_sha256, "file_size": row.file_size,
        "user_version": row.user_version, "detail_rows": row.detail_rows, "detail_new": row.detail_new,
        "detail_dup": row.detail_dup, "detail_aged_out": row.detail_aged_out,
        "rollup_rows": row.rollup_rows, "rollup_upserted": row.rollup_upserted,
        "date_min": row.date_min, "date_max": row.date_max, "imported_by": row.imported_by,
        "imported_at": row.imported_at.isoformat() if row.imported_at else None,
    } for row in imports]}


def delete_usage_import(import_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    """按导入批次删除其明细（rollup 保留——它是设备累计值，不与批次绑定）。"""
    row = db.query(UsageImport).filter(UsageImport.id == import_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="导入记录不存在")
    deleted = db.query(UsageRequestLog).filter(UsageRequestLog.import_id == import_id).delete(
        synchronize_session=False
    )
    db.delete(row)
    db.commit()
    return {"code": 0, "msg": "success", "data": {"deleted": True, "detail_removed": deleted}}


def delete_usage_device(device_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    """删除整个设备及其全部用量数据（级联：明细/rollup/providers/imports）。"""
    device = db.query(UsageDevice).filter(UsageDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    db.query(UsageRequestLog).filter(UsageRequestLog.device_id == device_id).delete(synchronize_session=False)
    db.query(UsageDailyRollup).filter(UsageDailyRollup.device_id == device_id).delete(synchronize_session=False)
    db.query(UsageProvider).filter(UsageProvider.device_id == device_id).delete(synchronize_session=False)
    db.query(UsageImport).filter(UsageImport.device_id == device_id).delete(synchronize_session=False)
    db.delete(device)
    db.commit()
    return {"code": 0, "msg": "success", "data": {"deleted": True, "device_label": device.label}}


def get_usage_overview(
    date_from: str | None = None, date_to: str | None = None,
    model: str | None = None, app_type: str | None = None,
    db: Session = Depends(get_db),
):
    """公开接口：总览与分布，无需登录。"""
    return {"code": 0, "msg": "success", "data": usage_overview(db, date_from, date_to, model, app_type)}


def get_usage_daily(
    date_from: str | None = None, date_to: str | None = None,
    model: str | None = None, app_type: str | None = None,
    db: Session = Depends(get_db),
):
    """公开接口：日序列，无需登录。"""
    return {"code": 0, "msg": "success", "data": usage_daily(db, date_from, date_to, model, app_type)}


def get_usage_filters(db: Session = Depends(get_db)):
    """公开接口：筛选下拉的可选值，无需登录。"""
    return {"code": 0, "msg": "success", "data": usage_filters(db)}
