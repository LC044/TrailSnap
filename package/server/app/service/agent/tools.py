import json
from typing import List, Optional
from datetime import datetime

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
from app.db.models.trip import TrainTicket, FlightTicket
from app.db.models.scene import Scene
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.face import Face, FaceIdentity
from app.utils.path import get_user_roots, compute_browse_path

def get_agent_tools(user_id: str) -> List[StructuredTool]:
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
            limit: 返回的照片数量上限
            sort_by: 排序方式，可选 "photo_time"（按时间）, "quality_score"（按美观度）, "memory_score"（按回忆价值）
        Returns:
            包含照片ID、拍摄时间、地点、所在文件夹、文件名和一句话描述的 JSON 字符串。
        """
        logging.info(f"search_photos_tool: {locals()}")
        with SessionLocal() as db:
            query = db.query(Photo, PhotoMetadata, ImageDescription).outerjoin(
                PhotoMetadata, Photo.id == PhotoMetadata.photo_id
            ).outerjoin(
                ImageDescription, Photo.id == ImageDescription.photo_id
            ).filter(Photo.owner_id == user_id)

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
                query = query.filter(distance < 0.78)

            if sort_by == "quality_score":
                query = query.order_by(ImageDescription.quality_score.desc().nulls_last())
            elif sort_by == "memory_score":
                query = query.order_by(ImageDescription.memory_score.desc().nulls_last())
            elif sort_by == "photo_time" and distance is not None:
                query = query.order_by(distance.asc())
            else:
                query = query.order_by(Photo.photo_time.desc().nulls_last())

            results = query.limit(limit).all()

            if not results:
                return "没有找到符合条件的照片。"

            roots = get_user_roots(user_id, db)
            response_data = []
            for photo, meta, desc in results:
                folder, filename = compute_browse_path(photo.file_path, roots)
                response_data.append({
                    "photo_id": str(photo.id),
                    "photo_time": photo.photo_time.strftime("%Y-%m-%d %H:%M:%S") if photo.photo_time else None,
                    "location": meta.address if meta else "未知地点",
                    "folder": folder or None,
                    "filename": filename or None,
                    "narrative": desc.narrative if desc else "无描述",
                    "quality_score": desc.quality_score if desc else None
                })

            return json.dumps(response_data, ensure_ascii=False)

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
            ).options(joinedload(Photo.tags)).filter(Photo.owner_id == user_id)

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
            ).filter(Photo.owner_id == user_id)

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
                Photo.owner_id == user_id
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

    return [
        search_photos_tool, 
        # get_travel_history_tool, 
        get_photo_details_tool,
        get_photo_locations_tool,
        get_photo_tags_tool,
        get_photo_persons_tool
    ]
