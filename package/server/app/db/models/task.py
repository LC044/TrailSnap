from sqlalchemy import Column, String, Integer, JSON, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(str, enum.Enum):
    SCAN_FOLDER = "SCAN_FOLDER"
    PROCESS_BASIC = "PROCESS_BASIC"  # Basic info, thumbnail, preview
    # PROCESS_IMAGE = "PROCESS_IMAGE"  # Deprecated or Full Legacy
    GENERATE_THUMBNAIL = "GENERATE_THUMBNAIL"
    EXTRACT_METADATA = "EXTRACT_METADATA" # Heavy metadata, geolocation
    CLASSIFY_IMAGE = "CLASSIFY_IMAGE"
    RECOGNIZE_FACE = "RECOGNIZE_FACE"
    RECOGNIZE_TICKET = "RECOGNIZE_TICKET"
    REBUILD_METADATA = "REBUILD_METADATA"
    OCR = "OCR"
    VISUAL_DESCRIPTION = "VISUAL_DESCRIPTION"
    SIMILAR_PHOTO_CLUSTERING = "SIMILAR_PHOTO_CLUSTERING"
    FIND_DUPLICATE_PHOTOS = "FIND_DUPLICATE_PHOTOS"
    IMAGE_EMBEDDING = "IMAGE_EMBEDDING"
    SCAN_ALBUM = "SCAN_ALBUM"
    ORGANIZE_PHOTOS = "ORGANIZE_PHOTOS"
    BATCH_RENAME = "BATCH_RENAME"
    BATCH_TIME_FROM_FILENAME = "BATCH_TIME_FROM_FILENAME"

DEFAULT_PRIORITIES = {
    TaskType.SCAN_ALBUM: 100,
    TaskType.SCAN_FOLDER: 100,
    TaskType.PROCESS_BASIC: 99,
    TaskType.GENERATE_THUMBNAIL: 98,
    TaskType.EXTRACT_METADATA: 97,
    TaskType.REBUILD_METADATA: 96,
    TaskType.RECOGNIZE_FACE: 10,
    TaskType.CLASSIFY_IMAGE: 9,
    TaskType.IMAGE_EMBEDDING: 8,
    TaskType.OCR: 7,
    TaskType.RECOGNIZE_TICKET: 4,
    TaskType.VISUAL_DESCRIPTION: 1,
    TaskType.SIMILAR_PHOTO_CLUSTERING: 1000,
    TaskType.FIND_DUPLICATE_PHOTOS: 1000,
    TaskType.ORGANIZE_PHOTOS: 1000,
    TaskType.BATCH_RENAME: 1000,
    TaskType.BATCH_TIME_FROM_FILENAME: 1000,
}

CATEGORY_DESCRIPTION_MAP = {
    TaskType.SCAN_FOLDER: '用于扫描文件夹中的文件',
    TaskType.PROCESS_BASIC: '用于基本文件处理',
    TaskType.GENERATE_THUMBNAIL: '用于生成缩略图',
    TaskType.EXTRACT_METADATA: '用于提取文件元数据（GPS位置、拍摄参数等）',
    TaskType.REBUILD_METADATA: '用于重建文件元数据',
    TaskType.RECOGNIZE_FACE: '用于识别图片中的人脸',
    TaskType.RECOGNIZE_TICKET: '用于识别火车票、飞机票等',
    TaskType.CLASSIFY_IMAGE: '用于场景分类',
    TaskType.VISUAL_DESCRIPTION: '用于生成图片的视觉描述',
    TaskType.OCR: '用于识别图片中的文字',
    TaskType.SIMILAR_PHOTO_CLUSTERING: '用于相似照片聚类',
    TaskType.FIND_DUPLICATE_PHOTOS: '用于扫描重复照片',
    TaskType.IMAGE_EMBEDDING: '用于生成图片的特征向量',
    TaskType.ORGANIZE_PHOTOS: '用于图片文件整理',
    TaskType.BATCH_RENAME: '用于批量重命名文件',
    TaskType.BATCH_TIME_FROM_FILENAME: '用于根据文件名提取时间并批量修改照片的拍摄时间和设备信息',
}

CATEGORY_NAME_MAP = {
    TaskType.SCAN_ALBUM: '扫描文件夹',
    TaskType.GENERATE_THUMBNAIL: '生成缩略图',
    TaskType.PROCESS_BASIC: '基本处理',
    TaskType.EXTRACT_METADATA: '元数据提取',
    TaskType.RECOGNIZE_FACE: '人脸识别',
    TaskType.RECOGNIZE_TICKET: '车票识别',
    TaskType.CLASSIFY_IMAGE: '场景识别',
    TaskType.VISUAL_DESCRIPTION: '大模型智能分析',
    TaskType.OCR: '文字识别',
    TaskType.SIMILAR_PHOTO_CLUSTERING: '相似照片清理',
    TaskType.FIND_DUPLICATE_PHOTOS: '重复照片清理',
    TaskType.IMAGE_EMBEDDING: '图片特征提取',
    TaskType.ORGANIZE_PHOTOS: '图片文件整理',
    TaskType.BATCH_RENAME: '批量重命名',
    TaskType.BATCH_TIME_FROM_FILENAME: '修改拍摄信息',
}

class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(50), nullable=False)
    status = Column(String(20), default=TaskStatus.PENDING.value)
    priority = Column(Integer, default=0) # Higher number = Higher priority
    payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # Progress tracking
    total_items = Column(Integer, default=0)
    processed_items = Column(Integer, default=0)

    __table_args__ = (
        Index('ix_tasks_status_priority_created', 'status', 'priority', 'created_at'),
        Index('ix_tasks_type_status', 'type', 'status'),
    )

    def __str__(self):
        return f"Task(id: {self.id}, type: {self.type}, status: {self.status}, priority: {self.priority})"

