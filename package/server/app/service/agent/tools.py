import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import logging
from sqlalchemy import or_, and_, cast, String
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy import or_, func, distinct
from langchain_core.tools import tool, StructuredTool

from app.utils.embedding import get_embedding
from app.core.config_manager import config_manager
from app.db.models import ImageVector
from app.db.session import SessionLocal
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.image_description import ImageDescription
from app.db.models.ocr import OCR
from app.db.models.trip import TrainTicket, FlightTicket
from app.db.models.scene import Scene
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.face import Face, FaceIdentity
from app.utils.path import get_user_roots, compute_browse_path
from app.service.agent.album_p0 import (
    album_health_report, artifact_context, contact_sheet_content, create_artifact, discover_travel_periods, photo_contexts, save_artifact_html, search_ocr_rows, select_representatives,
    travel_timeline, trip_tickets,
)
from app.service.agent.skills import get_skill_catalog, load_skill
from app.service.agent.actions import propose_album_plan

# 聚合摘要每类分布返回的 top-N 条目数
SUMMARY_TOP_N = 8


def _base_agent_photo_search_query(db: Session, user_id: str):
    """Build the PostgreSQL-safe projection used by search_photos_v2."""
    return db.query(Photo.id, Photo.photo_time).outerjoin(PhotoMetadata).outerjoin(ImageDescription).filter(
        Photo.owner_id == user_id, Photo.is_deleted.is_(False)
    )


def _build_search_summary(db: Session, filtered_query, distance) -> dict:
    """
    计算覆盖全部命中照片的聚合概览：时间跨度、城市分布 top-N、标签分布 top-N。
    从筛选 query 抽取 photo_id 子查询做独立聚合，与主查询解耦；任何异常都吞掉不影响主结果。
    """
    summary: dict = {}
    try:
        # 抽取命中的 photo_id 子查询，去除 distance 等附加列与排序
        id_subq = filtered_query.with_entities(Photo.id).order_by(None).subquery()

        # 时间跨度
        try:
            tmin, tmax = db.query(
                func.min(Photo.photo_time), func.max(Photo.photo_time)
            ).filter(Photo.id.in_(db.query(id_subq.c.id))).first()
            if tmin or tmax:
                summary["date_range"] = [
                    tmin.strftime("%Y-%m-%d") if tmin else None,
                    tmax.strftime("%Y-%m-%d") if tmax else None,
                ]
        except Exception as e:
            logging.warning(f"summary date_range 计算失败: {e}")

        # 城市分布 top-N
        try:
            rows = (
                db.query(PhotoMetadata.city, func.count().label("cnt"))
                .filter(
                    PhotoMetadata.photo_id.in_(db.query(id_subq.c.id)),
                    PhotoMetadata.city.isnot(None),
                    PhotoMetadata.city != "",
                )
                .group_by(PhotoMetadata.city)
                .order_by(func.count().desc())
                .limit(SUMMARY_TOP_N)
                .all()
            )
            if rows:
                summary["top_locations"] = {city: cnt for city, cnt in rows}
        except Exception as e:
            logging.warning(f"summary top_locations 计算失败: {e}")

        # 标签分布 top-N
        try:
            rows = (
                db.query(PhotoTag.tag_name, func.count().label("cnt"))
                .join(PhotoTagRelation, PhotoTag.id == PhotoTagRelation.tag_id)
                .filter(PhotoTagRelation.photo_id.in_(db.query(id_subq.c.id)))
                .group_by(PhotoTag.tag_name)
                .order_by(func.count().desc())
                .limit(SUMMARY_TOP_N)
                .all()
            )
            if rows:
                summary["top_tags"] = {name: cnt for name, cnt in rows}
        except Exception as e:
            logging.warning(f"summary top_tags 计算失败: {e}")
    except Exception as e:
        logging.warning(f"_build_search_summary 整体失败，返回空摘要: {e}")

    return summary


def get_agent_tools(user_id: str, session_id: str | None = None) -> List[StructuredTool]:
    """
    根据 user_id 动态生成绑定了用户的工具列表
    """

    @tool
    def search_photos_tool(
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None, 
        location: Optional[str] = None,
        provinces: Optional[List[str]] = None,
        cities: Optional[List[str]] = None,
        districts: Optional[List[str]] = None,
        scenes: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        persons: Optional[List[str]] = None,
        description: Optional[str] = None,
        folders: Optional[List[str]] = None,
        limit: int = 100,
        sort_by: str = "photo_time"
    ) -> str:
        """
        该接口用于搜索照片，不能用缩小搜索范围，也不能用来查看照片的详细数据。受limit限制，只能返回部分照片，在使用该接口之前，必须先根据用户的描述来初步缩小搜索范围，例如日期范围、地点、类型、标签、人物等，如果用户没有提供足够的信息，你可以要求用户进一步给出详细的描述。
        搜索用户的相册照片。支持多维度筛选，不同筛选条件之间进行与运算，相同筛选列表之间进行或运算。

        【渐进式披露】为节省上下文，当命中照片过多时，本接口不会返回全部明细，而是采用"少量样本 + 全局聚合摘要"的方式：
          - photos：仅返回排序后的前若干条完整明细（样本）；
          - truncated：为 true 时表示还有更多照片未在 photos 中列出，你应据此判断是否需要提示用户进一步缩小范围，而不要臆断只有这几张；
          - summary：对**全部**符合条件的照片（不止样本）做的聚合概览，包含时间跨度、地点分布(top)、标签分布(top)，可用它快速把握整体情况并回答"去了哪些地方/拍了些什么"类问题。

        【九宫格 / 挑图场景】当用户明确需要"凑九宫格""挑几张发朋友圈""给我 N 张照片"等需要拿到具体照片明细的场景时，
        请把 limit 显式设为所需数量（如 9 或 12）。当 limit <= 12 时，本接口会返回该数量的完整明细且不截断，确保你能直接用于展示。

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            location: 模糊的地点名称（如"北京", "西湖"）
            provinces: 匹配的省份列表
            cities: 匹配的城市列表
            districts: 匹配的区县列表
            scenes: 匹配的景区名称列表
            tags: 匹配的照片标签列表（如"风景", "猫"）
            persons: 匹配的人物/人脸名称列表
            description: clip模型以文搜图的文本描述提示词
            folders: 匹配的文件夹名称/相对路径关键字列表（如"旅游", "演唱会"），按文件路径模糊匹配
            limit: 期望返回的照片数量上限。凑图/挑图时请设为具体数量(如9、12)以获得完整明细。
            sort_by: 排序方式，可选 "photo_time"（按时间）, "quality_score"（按美观度）, "memory_score"（按回忆价值）
        Returns:
            JSON 字符串，结构为
            {
              "total": 符合条件的照片总数,
              "returned": 本次 photos 中返回的样本数量,
              "truncated": 是否还有更多照片未列出,
              "summary": {"date_range": [...], "top_locations": {...}, "top_tags": {...}},
              "photos": [...样本明细...]
            }。
            其中 total 可能远大于 returned；truncated=true 时请结合 summary 概览作答或提示用户缩小范围。
            每张照片包含 photo_id、拍摄时间、地点、所在文件夹、文件名和一句话描述；
            当使用 description 以文搜图时，还会附带 similarity（0~1，越大越相关）字段。
        """
        logging.info(f"search_photos_tool: {locals()}")
        with SessionLocal() as db:
            query = db.query(Photo, PhotoMetadata, ImageDescription).outerjoin(
                PhotoMetadata, Photo.id == PhotoMetadata.photo_id
            ).outerjoin(
                ImageDescription, Photo.id == ImageDescription.photo_id
            ).filter(Photo.owner_id == user_id, Photo.is_deleted.is_(False))

            if start_date:
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    query = query.filter(Photo.photo_time >= start_dt)
                except ValueError:
                    pass
            
            if end_date:
                try:
                    end_dt = datetime.strptime(f"{end_date} 23:59:59", "%Y-%m-%d %H:%M:%S")
                    query = query.filter(Photo.photo_time <= end_dt)
                except ValueError:
                    pass

            if location:
                query = query.filter(
                    (PhotoMetadata.city.ilike(f"%{location}%")) |
                    (PhotoMetadata.province.ilike(f"%{location}%")) |
                    (PhotoMetadata.address.ilike(f"%{location}%"))
                )

            if provinces:
                query = query.filter(PhotoMetadata.province.in_(provinces))
            if cities:
                query = query.filter(PhotoMetadata.city.in_(cities))
            if districts:
                query = query.filter(PhotoMetadata.district.in_(districts))

            if scenes:
                query = query.filter(PhotoMetadata.scene.has(Scene.name.in_(scenes)))

            if tags:
                tag_conditions = [Photo.tags.any(PhotoTag.tag_name.in_(tags))]
                for t in tags:
                    tag_conditions.append(cast(ImageDescription.tags, String).ilike(f'%"{t}"%'))
                query = query.filter(or_(*tag_conditions))

            if persons:
                query = query.filter(Photo.faces.any(Face.identity.has(FaceIdentity.identity_name.in_(persons))))

            if folders:
                folder_conditions = [Photo.file_path.ilike(f"%{f}%") for f in folders if f]
                if folder_conditions:
                    query = query.filter(or_(*folder_conditions))
            distance = None
            if description:
                # 1. Get Text Embedding from AI Service
                embedding = get_embedding(description, user_id, db)

                distance = ImageVector.embedding.cosine_distance(embedding)
                query = query.join(ImageVector, Photo.id == ImageVector.photo_id)
                # 放宽硬阈值，改为 top-k 策略：仅过滤明显不相关项（宽松阈值兜底），
                # 最终相关性由 distance 升序排序 + limit 控制，并向模型返回 similarity 分数。
                query = query.filter(distance < 0.85)
                query = query.add_columns(distance.label("distance"))

            # 统计符合筛选条件的总数（在排序/分页之前），供模型判断是否还有更多结果
            total = query.order_by(None).count()

            # 渐进式披露：limit<=12 视为凑图场景全量返回；否则最多返回 SAMPLE_LIMIT 条样本
            SAMPLE_LIMIT = 8
            GALLERY_THRESHOLD = 12
            if limit <= GALLERY_THRESHOLD:
                effective_limit = limit
            else:
                effective_limit = min(limit, SAMPLE_LIMIT)

            # 全局聚合摘要（覆盖全部命中照片）
            summary = _build_search_summary(db, query, distance)

            if sort_by == "quality_score":
                query = query.order_by(ImageDescription.quality_score.desc().nulls_last())
            elif sort_by == "memory_score":
                query = query.order_by(ImageDescription.memory_score.desc().nulls_last())
            elif sort_by == "photo_time" and distance is not None:
                query = query.order_by(distance.asc())
            else:
                query = query.order_by(Photo.photo_time.desc().nulls_last())

            results = query.limit(effective_limit).all()

            if not results:
                return json.dumps({
                    "total": total, "returned": 0, "truncated": False,
                    "summary": summary, "photos": []
                }, ensure_ascii=False)

            roots = get_user_roots(user_id, db)
            response_data = []
            for row in results:
                # 使用 description 以文搜图时，行末会多出一列 distance
                if distance is not None:
                    photo, meta, desc, dist = row
                else:
                    photo, meta, desc = row
                    dist = None
                folder, filename = compute_browse_path(photo.file_path, roots)
                item = {
                    "photo_id": str(photo.id),
                    "photo_time": photo.photo_time.strftime("%Y-%m-%d %H:%M:%S") if photo.photo_time else None,
                    "location": meta.address if meta else "未知地点",
                    "folder": folder or None,
                    "filename": filename or None,
                    "narrative": desc.narrative if desc else "无描述",
                    "quality_score": desc.quality_score if desc else None
                }
                if dist is not None:
                    # cosine_distance ∈ [0, 2]，转换为直观的相似度分数（越大越相关）
                    item["similarity"] = round(1 - float(dist), 4)
                response_data.append(item)

            return json.dumps({
                "total": total,
                "returned": len(response_data),
                "truncated": total > len(response_data),
                "summary": summary,
                "photos": response_data
            }, ensure_ascii=False)

    @tool
    def get_photo_locations_tool(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        level: Optional[str] = None,
    ) -> str:
        """
        获取照片足迹时间轴，用于查看某一段时间在哪些地方拍过照。当用户问去了哪些地方时可以调用此接口查询。
        Args:
            start_date: 开始日期 (YYYY-MM-DD)（可选）
            end_date: 结束日期（YYYY-MM-DD)（可选）
            level: 地点的层级（"provinces"、"cities"、"districts"、"scenes"，默认"city"）
        Returns:
            足迹时间轴的 JSON 字符串列表。每项字段说明：
            class TimelineNode(BaseModel):
                type: str = "default"
                startDate: str # 开始日期 (YYYY-MM-DD)
                endDate: str # 结束日期 (YYYY-MM-DD)
                locationName: str # 地点名称
                level: Optional[str] = None # 地点类型（可选）
                lat: Optional[float] = None
                lng: Optional[float] = None
                photoCount: int = 0 # 照片数量
                coverId: Optional[UUID] = None
        """
        logging.info(f"get_photo_locations_tool: {locals()}")
        with SessionLocal() as db:
            import app.crud.location
            response_data = app.crud.location.get_timeline_nodes(db, user_id, level, start_date=start_date, end_date=end_date)
            return response_data.model_dump_json()

    @tool
    def get_photo_tags_tool(
        photo_ids: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50
    ) -> str:
        """
        获取照片的分类标签信息，用于查看某一段时间的照片含有哪些标签，可以查找照片的分类标签信息。
        Args:
            photo_ids: 照片 ID 的字符串列表（可选）
            start_date: 开始日期 (YYYY-MM-DD)（可选）
            end_date: 结束日期 (YYYY-MM-DD)（可选）
            limit: 返回结果上限
        Returns:
            包含去重后的标签(tags)名称的 JSON 字符串列表。
        """
        with SessionLocal() as db:
            query = db.query(Photo, ImageDescription).outerjoin(
                ImageDescription, Photo.id == ImageDescription.photo_id
            ).options(joinedload(Photo.tags)).filter(Photo.owner_id == user_id, Photo.is_deleted.is_(False))

            if photo_ids:
                query = query.filter(Photo.id.in_(photo_ids))
            if start_date:
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    query = query.filter(Photo.photo_time >= start_dt)
                except ValueError:
                    pass
            if end_date:
                try:
                    end_dt = datetime.strptime(f"{end_date} 23:59:59", "%Y-%m-%d %H:%M:%S")
                    query = query.filter(Photo.photo_time <= end_dt)
                except ValueError:
                    pass

            results = query.order_by(Photo.photo_time.desc().nulls_last()).all()

            if not results:
                return "没有找到照片的标签信息。"

            all_tags = set()
            for photo, desc in results:
                if desc and desc.tags:
                    for t in desc.tags:
                        all_tags.add(t)
                for t in photo.tags:
                    all_tags.add(t.tag_name)
            
            return json.dumps(list(all_tags), ensure_ascii=False)

    @tool
    def get_photo_persons_tool(
        photo_ids: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50
    ) -> str:
        """
        获取照片包含的人物/人脸标签信息（去重后的列表），可以用来查找照片中的人物信息。
        Args:
            photo_ids: 照片 ID 的字符串列表（可选）
            start_date: 开始日期 (YYYY-MM-DD)（可选）
            end_date: 结束日期 (YYYY-MM-DD)（可选）
            limit: 返回结果上限
        Returns:
            包含去重后的人物名称的 JSON 字符串列表。
        """
        with SessionLocal() as db:
            query = db.query(Photo).options(
                joinedload(Photo.faces).joinedload(Face.identity)
            ).filter(Photo.owner_id == user_id, Photo.is_deleted.is_(False))

            if photo_ids:
                query = query.filter(Photo.id.in_(photo_ids))
            if start_date:
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    query = query.filter(Photo.photo_time >= start_dt)
                except ValueError:
                    pass
            if end_date:
                try:
                    end_dt = datetime.strptime(f"{end_date} 23:59:59", "%Y-%m-%d %H:%M:%S")
                    query = query.filter(Photo.photo_time <= end_dt)
                except ValueError:
                    pass

            results = query.order_by(Photo.photo_time.desc().nulls_last()).all()

            if not results:
                return "没有找到照片的人物信息。"

            all_persons = dict()
            for photo in results:
                for face in photo.faces:
                    if face.identity and face.identity.identity_name:
                        all_persons[face.identity.identity_name] = {
                            "name": face.identity.identity_name,
                            "description": face.identity.description,
                            "tags": face.identity.tags
                        }

            return json.dumps(list(all_persons.values()), ensure_ascii=False)

    @tool
    def get_travel_history_tool(start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        """
        查询用户的火车票和机票出行记录。
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        Returns:
            包含出行时间、出发地、目的地的 JSON 字符串。
        """
        with SessionLocal() as db:
            train_query = db.query(TrainTicket).filter(TrainTicket.owner_id == user_id)
            flight_query = db.query(FlightTicket).filter(FlightTicket.owner_id == user_id)

            if start_date:
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    train_query = train_query.filter(TrainTicket.date_time >= start_dt)
                    flight_query = flight_query.filter(FlightTicket.date_time >= start_dt)
                except ValueError:
                    pass
            
            if end_date:
                try:
                    end_dt = datetime.strptime(f"{end_date} 23:59:59", "%Y-%m-%d %H:%M:%S")
                    train_query = train_query.filter(TrainTicket.date_time <= end_dt)
                    flight_query = flight_query.filter(FlightTicket.date_time <= end_dt)
                except ValueError:
                    pass

            train_results = train_query.order_by(TrainTicket.date_time.asc()).all()
            flight_results = flight_query.order_by(FlightTicket.date_time.asc()).all()

            records = []
            for t in train_results:
                records.append({
                    "type": "火车",
                    "date": t.date_time.strftime("%Y-%m-%d %H:%M:%S") if t.date_time else None,
                    "train_code": t.train_code,
                    "departure": t.departure_station,
                    "arrival": t.arrival_station
                })
            
            # for f in flight_results:
            #     records.append({
            #         "type": "飞机",
            #         "date": f.date_time.strftime("%Y-%m-%d %H:%M:%S") if f.date_time else None,
            #         "flight_no": f.flight_code,
            #         "departure": f.departure_airport,
            #         "arrival": f.arrival_airport
            #     })
            
            if not records:
                return "这段时间内没有出行记录。"

            # 按时间排序
            records.sort(key=lambda x: x["date"] if x["date"] else "")
            return json.dumps(records, ensure_ascii=False)

    @tool
    def get_photo_details_tool(photo_ids: List[str]) -> str:
        """
        根据照片 ID 列表获取照片的详细描述和标签，用于撰写朋友圈文案。
        Args:
            photo_ids: 照片 ID 的字符串列表
        Returns:
            包含照片详细描述、标签和一句话旁白的 JSON 字符串。
        """
        with SessionLocal() as db:
            # 过滤 owner_id 确保安全
            results = db.query(ImageDescription).join(
                Photo, Photo.id == ImageDescription.photo_id
            ).filter(
                ImageDescription.photo_id.in_(photo_ids),
                Photo.owner_id == user_id,
                Photo.is_deleted.is_(False),
            ).all()
            
            if not results:
                return "没有找到这些照片的详细信息。"

            response_data = []
            for desc in results:
                response_data.append({
                    "photo_id": str(desc.photo_id),
                    "description": desc.description,
                    "tags": desc.tags,
                    "narrative": desc.narrative
                })
            return json.dumps(response_data, ensure_ascii=False)

    @tool
    def list_skills() -> str:
        """列出当前相册 Agent 可以按需加载的工作流 Skill。"""
        return json.dumps({"skills": get_skill_catalog()}, ensure_ascii=False)

    @tool("load_skill")
    def load_skill_tool(name: str) -> str:
        """按名称加载一个相册工作流 Skill 的完整指引；执行复杂任务前先加载对应 Skill。"""
        try:
            return json.dumps(load_skill(name), ensure_ascii=False)
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @tool
    def search_photos_v2(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        location: Optional[str] = None,
        ocr_text: Optional[str] = None,
        media_type: Optional[str] = None,
        orientation: Optional[str] = None,
        has_people: Optional[bool] = None,
        min_quality_score: Optional[float] = None,
        min_memory_score: Optional[float] = None,
        cursor: Optional[str] = None,
        limit: int = 30,
    ) -> str:
        """高级搜索照片，支持 OCR、媒体类型、方向、人物、质量/回忆分和游标分页；返回安全的上下文，不含原始文件路径。"""
        with SessionLocal() as db:
            # PostgreSQL requires every ORDER BY expression to be present in a
            # SELECT DISTINCT list. Keep photo_time in the projection while
            # still returning only the ID to callers.
            query = _base_agent_photo_search_query(db, user_id)
            if start_date: query = query.filter(Photo.photo_time >= datetime.strptime(start_date, "%Y-%m-%d"))
            if end_date: query = query.filter(Photo.photo_time < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
            if location:
                query = query.filter(or_(PhotoMetadata.city.ilike(f"%{location}%"), PhotoMetadata.province.ilike(f"%{location}%"), PhotoMetadata.address.ilike(f"%{location}%")))
            if ocr_text:
                query = query.join(OCR, OCR.photo_id == Photo.id).filter(OCR.text.ilike(f"%{ocr_text}%"))
            if media_type: query = query.filter(cast(Photo.file_type, String) == media_type)
            if orientation == "landscape": query = query.filter(Photo.width > Photo.height)
            elif orientation == "portrait": query = query.filter(Photo.height > Photo.width)
            elif orientation == "square": query = query.filter(Photo.height == Photo.width)
            if has_people is True: query = query.filter(Photo.faces.any())
            elif has_people is False: query = query.filter(~Photo.faces.any())
            if min_quality_score is not None: query = query.filter(ImageDescription.quality_score >= min_quality_score)
            if min_memory_score is not None: query = query.filter(ImageDescription.memory_score >= min_memory_score)
            total = query.order_by(None).distinct().count()
            offset = int(cursor or 0) if (cursor or "0").isdigit() else 0
            page_size = min(max(limit, 1), 30)
            ids = [str(row[0]) for row in query.distinct().order_by(Photo.photo_time.desc().nulls_last()).offset(offset).limit(page_size).all()]
            return json.dumps({"total": total, "next_cursor": str(offset + len(ids)) if offset + len(ids) < total else None, "photos": photo_contexts(db, user_id, ids)}, ensure_ascii=False)

    @tool
    def get_photo_context(photo_ids: List[str]) -> str:
        """一次获取最多 30 张照片的时间、地点、EXIF、描述、评分、标签、人物、OCR、色彩和安全缩略图 URL。"""
        with SessionLocal() as db:
            return json.dumps({"photos": photo_contexts(db, user_id, photo_ids)}, ensure_ascii=False)

    @tool
    def search_ocr(query: str, limit: int = 30) -> str:
        """在当前用户照片的 OCR 文字中搜索车次、店名、景点、菜单或其他可见文字。"""
        with SessionLocal() as db:
            return json.dumps({"results": search_ocr_rows(db, user_id, query, limit)}, ensure_ascii=False)

    @tool
    def get_trip_tickets(start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        """获取指定日期范围内当前用户的火车票和机票结构化记录。"""
        with SessionLocal() as db:
            return json.dumps({"tickets": trip_tickets(db, user_id, start_date, end_date)}, ensure_ascii=False)

    @tool
    def get_travel_timeline(start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        """按日期与地点聚合旅行照片，并联合票据返回可用于写旅行日志的时间线。"""
        with SessionLocal() as db:
            return json.dumps(travel_timeline(db, user_id, start_date, end_date), ensure_ascii=False)

    @tool
    def discover_trips(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_photos: int = 12,
        max_results: int = 8,
    ) -> str:
        """自动发现旅行候选。

        根据连续拍摄日期和地点聚合候选行程，并返回候选照片与票据 ID。
        结果只是建议，生成正式相册前仍需由用户在计划卡片中确认。
        """
        with SessionLocal() as db:
            try:
                result = discover_travel_periods(
                    db, user_id, start_date, end_date, min_photos, max_results
                )
            except ValueError:
                return json.dumps({"error": "日期格式必须为 YYYY-MM-DD"}, ensure_ascii=False)
            return json.dumps(result, ensure_ascii=False)

    @tool
    def inspect_album_health(album_id: Optional[str] = None, sample_limit: int = 8) -> str:
        """只读检查整个照片库或指定相册的健康度。

        统计缺少拍摄时间、地点、视觉描述、文件指纹、未归档照片、完全重复照片，
        以及空相册、照片计数不一致和缺少封面等问题。不会修改或删除任何数据。
        """
        with SessionLocal() as db:
            try:
                result = album_health_report(db, user_id, album_id, sample_limit)
            except ValueError as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)
            return json.dumps(result, ensure_ascii=False)

    @tool
    def view_photos(photo_ids: List[str], size: str = "small") -> str:
        """查看最多 16 张候选照片；返回可直接展示或供多模态模型逐张检查的缩略图清单。"""
        with SessionLocal() as db:
            photos = photo_contexts(db, user_id, photo_ids[:16])
            return json.dumps({"mode": "multimodal_gallery", "size": size if size in ("small", "medium") else "small", "photos": [{"photo_id": p["photo_id"], "thumbnail_url": p["thumbnail_url"], "description": p["description"], "quality_score": p["quality_score"]} for p in photos]}, ensure_ascii=False)

    @tool
    def create_contact_sheet(photo_ids: List[str]) -> List[dict]:
        """生成最多 16 张照片的编号联系表，并把真实图片作为多模态工具结果返回给模型观察。"""
        with SessionLocal() as db:
            return contact_sheet_content(db, user_id, photo_ids)

    @tool
    def select_representative_photos(photo_ids: List[str], count: int = 9) -> str:
        """从候选中选择最多 16 张代表照片，兼顾质量、回忆价值和时间/地点/人物多样性，返回可解释理由。"""
        with SessionLocal() as db:
            selected = select_representatives(db, user_id, photo_ids, count)
            return json.dumps({"selected": selected, "requested": count, "returned": len(selected)}, ensure_ascii=False)

    @tool
    def create_artifact_draft(
        artifact_type: str,
        title: str,
        content: Dict[str, Any],
        photo_ids: List[str],
        ticket_ids: Optional[List[str]] = None,
    ) -> str:
        """保存可编辑 AI 作品草稿。旅行日志使用 artifact_type=travel_story，content 包含 summary 和 sections。只创建草稿，不会修改照片。"""
        if artifact_type not in {"travel_story", "nine_grid", "album_note"}:
            return json.dumps({"error": "unsupported artifact_type"}, ensure_ascii=False)
        with SessionLocal() as db:
            try:
                row = create_artifact(db, user_id, session_id, artifact_type, title, content, photo_ids[:100], ticket_ids or [])
            except ValueError as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)
            return json.dumps({"artifact": {"id": str(row.id), "type": row.artifact_type, "title": row.title, "status": row.status, "url": f"/agent/artifacts/{row.id}", "photo_ids": row.source_photo_ids}}, ensure_ascii=False)

    @tool
    def save_artifact_html_page(
        artifact_id: str,
        html_content: str,
        style_name: str = "custom",
        custom_style: Optional[str] = None,
        server_api_access: bool = False,
    ) -> str:
        """为已有 AI 作品保存完整、个性化 HTML 页面。

        html_content 必须是完整 HTML 文档，可包含内联 CSS/JS，不能使用外部占位图片。
        照片使用 /api/medias/{user_id}/{photo_id}/thumbnail?size=medium 形式的真实地址。
        若 server_api_access=true，页面可通过 await TrailSnap.request('/api/...') 只读访问当前用户授权的数据。
        常用 GET 路径包括 /api/stats/timeline?years=2026、/api/stats/dashboard、/api/albums 和 /api/photos；
        不要猜测未由工具说明的接口，TrailSnap.request 目前只接收一个含查询参数的路径字符串。
        标题、正文、章节和真实照片必须直接预渲染在 HTML DOM 中，不得仅存放在 JavaScript 数据或 template 中；JavaScript 只用于渐进增强。
        不得在 HTML 中嵌入 token、密码或第三方追踪脚本。
        """
        with SessionLocal() as db:
            try:
                row = save_artifact_html(
                    db, user_id, artifact_id, html_content, style_name,
                    custom_style, server_api_access,
                )
            except ValueError as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)
            return json.dumps({"artifact": {
                "id": str(row.id), "type": row.artifact_type, "title": row.title,
                "status": row.status, "url": f"/agent/artifacts/{row.id}?view=html",
                "photo_ids": row.source_photo_ids, "has_html": True,
            }}, ensure_ascii=False)

    @tool
    def get_artifact_context(artifact_id: str) -> str:
        """读取当前用户已有 AI 作品的结构化内容、照片 ID 和 HTML 配置，用于生成或重新设计个性化页面。"""
        with SessionLocal() as db:
            try:
                return json.dumps(artifact_context(db, user_id, artifact_id), ensure_ascii=False)
            except ValueError as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @tool
    def propose_album_organization(
        name: str,
        photo_ids: List[str],
        description: Optional[str] = None,
        cover_photo_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        album_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> str:
        """生成一个需要用户在界面中确认的相册整理计划。

        可以创建普通相册，或向当前用户已有的普通相册添加照片，同时设置名称、简介、封面并添加标签。
        P2 旅行工作流应传入已经创建的旅行日志 artifact_id，使相册计划与旅行作品关联。
        这个工具只生成预览，不会直接修改相册或照片；不要声称计划已执行，也不要替用户确认。
        photo_ids 最多 500 个，cover_photo_id 必须包含在 photo_ids 中，tags 最多 10 个。
        P1 不会删除、移动、重命名照片，也不会修改原始文件。
        """
        with SessionLocal() as db:
            try:
                row = propose_album_plan(
                    db, user_id, session_id, name, description, photo_ids,
                    cover_photo_id, tags, album_id=album_id,
                    artifact_id=artifact_id, summary=summary,
                )
            except ValueError as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)
            return json.dumps({"action_plan": {
                "id": str(row.id), "plan_type": row.plan_type, "title": row.title,
                "summary": row.summary, "status": row.status, "preview": row.preview,
            }}, ensure_ascii=False)

    return [
        search_photos_tool, 
        # get_travel_history_tool, 
        get_photo_details_tool,
        get_photo_locations_tool,
        get_photo_tags_tool,
        get_photo_persons_tool,
        list_skills, load_skill_tool, search_photos_v2, get_photo_context,
        search_ocr, get_trip_tickets, get_travel_timeline, discover_trips, inspect_album_health, view_photos,
        create_contact_sheet, select_representative_photos, create_artifact_draft,
        get_artifact_context, save_artifact_html_page, propose_album_organization,
    ]
