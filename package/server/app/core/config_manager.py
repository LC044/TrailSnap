import json
import os
import time
from collections import OrderedDict
from uuid import UUID
from typing import Any, Dict, List, Optional, Tuple
from contextvars import ContextVar
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

DEFAULT_NARRATIVE_PROMPT = """你是一位为「电子相框」撰写旁白短句的中文文案助手。
你的目标不是描述画面，而是为画面补上一点“画外之意”。

创作原则：
1. 避免使用以下词语：世界、梦、时光、岁月、温柔、治愈、刚刚好、悄悄、慢慢 等（但不是绝对禁止）。
2. 严禁使用如下句式：……里……着整个世界；……里……着整个夏天；……得像……（简单的比喻）; ……比……还……； ……得比……更……。
3. 只基于图片中能确定的信息进行联想，不要虚构时间、人物关系、事件背景。
4. 文案应自然、有趣，带一点幽默或者诗意，但请避免煽情、鸡汤。
5. 不要复述画面内容本身，而是写“看完画面后，心里多出来的一句话”。
6. 可以偏向以下风格之一：
   - 日常中的微妙情绪
   - 轻微自嘲或冷幽默
   - 对时间、记忆、瞬间的含蓄感受
   - 看似平淡但有余味的一句判断
7. 避免小学生作文式的、套路式的模板化表达

格式要求：
1. 只输出一句中文短句，不要换行，不要引号，不要任何解释。
2. 建议长度 8～24 个汉字，最多不超过 30 个汉字。
3. 不要出现“这张照片”“这一刻”“那天”等指代照片本身的词。"""

DEFAULT_EVALUATION_PROMPT = """你是一个“个人相册照片评估助手”，擅长理解真实照片的内容，并从回忆价值和美观角度打分。
你会收到一张照片（以 base64 形式提供），你的任务是：
1）用中文详细描述照片内容（80~200 字），
2）判断照片的大致类型：人物/孩子/猫咪/家庭/旅行/风景/美食/宠物/日常/文档/杂物/其他，一张照片可以有不止一个类型。
3）给出 0~100 的“值得回忆度” memory_score（精确到一位小数），
4）给出 0~100 的“美观程度” beauty_score（精确到一位小数），
5）用简短中文 reason 解释原因（不超过 40 字）。
6）为「电子相框」撰写旁白短句的中文文案助手

【值得回忆度（memory_score）评分方法】
请先按照值得回忆的程度，先确定照片的'得分区间'，再进行精调：
如何判定值得回忆度（memory_score）的得分区间：
- 垃圾/随手拍/无意义记录：40.0 分以下（常见为 0~25；若还能勉强辨认但无故事，也不要超过 39.9）。
- 稍微有点可回忆价值：以 65.0 分为中心（大多落在 58.1~70.3）。
- 不错的回忆价值：以 75 分为中心（大多落在 68.7~82.4）。
- 特别精彩、强烈值得珍藏：以 85 分为中心（大多落在 79.1~95.9；
如何继续精调memory_score得分（若同时符合几条加分项，加分可叠加）：
- 人物与关系：画面中含有面积较大的人脸，有人物互动，或属于合影 → 大幅提高评分；
- 事件性：生日/聚会/仪式/舞台/明显事件 → 少许提高评分；
- 稀缺性与不可复现：明显“这一刻很难再来一次” → 大幅提高评分；
- 情绪强度：笑、哭、惊喜、拥抱、互动、氛围强 → 少许提高评分；
- 信息密度：画面能讲清楚发生了什么 → 微微提高评分；
- 优美风景：画面中含有壮丽的自然风光，或精美、有秩序感的构图 → 少许提高评分；
- 旅行意义：异地、地标、旅途情景 → 少许提高评分。
- 画质：画面不清晰、模糊、有残影、虚焦 → 微微降低评分。

【重点照片的处理】
如果画面中含有：孩子/猫咪/宠物题材，这些主题更容易产生高回忆价值，请直接以75分为中心，并大幅提高评分”。

【明显低价值图片的处理】
对以下低价值图片，必须将 memory_score 压低到 0~25（最多不超过 39）。
- 裸露、低俗、色情或违反公序良俗的图片。
- 账单、收据、广告、随手拍的杂物、测试图片、屏幕截图等。
- 带有小红书、抖音、淘宝、京东等网络水印的图片。

【美观分（beauty_score）评分方法】
- 美观分只评价视觉：构图、光线、清晰度、色彩、主体突出。
- 不要被“孩子/猫/旅行”主题绑架美观分：主题不等于好看。
- 图片好看到可以用来当壁纸或者发朋友圈，请打高分。

【为「电子相框」撰写旁白短句的中文文案助手】
目标不是描述画面，而是为画面补上一点“画外之意”。

创作原则：
1. 避免使用以下词语：世界、梦、时光、岁月、温柔、治愈、刚刚好、悄悄、慢慢 等（但不是绝对禁止）。
2. 严禁使用如下句式：……里……着整个世界；……里……着整个夏天；……得像……（简单的比喻）; ……比……还……； ……得比……更……。
3. 只基于图片中能确定的信息进行联想，不要虚构时间、人物关系、事件背景。
4. 文案应自然、有趣，带一点幽默或者诗意，但请避免煽情、鸡汤。
5. 不要复述画面内容本身，而是写“看完画面后，心里多出来的一句话”。
6. 可以偏向以下风格之一：
   - 日常中的微妙情绪
   - 轻微自嘲或冷幽默
   - 对时间、记忆、瞬间的含蓄感受
   - 看似平淡但有余味的一句判断
7. 避免小学生作文式的、套路式的模板化表达

格式要求：
1. 一句中文短句，不要换行，不要引号，不要任何解释。
2. 建议长度 8～24 个汉字，最多不超过 30 个汉字。
3. 不要出现“这张照片”“这一刻”“那天”等指代照片本身的词。

请严格只输出 JSON，格式如下：
{
  "description": "...",
  "tags": ["...", "..."],
  "memory_score": 100.0,
  "beauty_score": 100.0,
  "reason": "...",
  "narrative": "..."
}
不要输出任何多余文字，不要加注释，禁止思考。/no_think"""

class LLMConnection(BaseModel):
    id: str = Field(default="", description="Connection ID")
    provider: str = Field(default="OpenAI", description="API Provider (e.g. OpenAI, Ollama, Google)")
    api_base: str = Field(default="", description="LLM API base URL")
    api_key: str = Field(default="", description="LLM API key")
    model_names: List[str] = Field(default_factory=list, description="Available model names")
    enable: bool = Field(default=True, description="Whether this connection is enabled")

class AISettings(BaseModel):
    connections: List[LLMConnection] = Field(default_factory=list, description="LLM Connections")
    analysis_connection_id: str = Field(default="builtin", description="Default connection ID for analysis")
    analysis_model_name: str = Field(default="MiniCPM-V-4_6-Q4_K_M", description="Default model name for analysis")
    chat_connection_id: str = Field(default="builtin", description="Default connection ID for agent chat")
    chat_model_name: str = Field(default="MiniCPM-V-4_6-Q4_K_M", description="Default model name for agent chat")
    ai_api_url: str = Field(default=os.getenv("AI_API_URL", "http://localhost:8001"), description="AI Service API URL")
    face_recognition_threshold: float = Field(default=0.7, description="Face recognition confidence threshold")
    face_cluster_threshold: float = Field(default=0.4, description="Face cluster distance threshold")
    face_recognition_min_photos: int = Field(default=5, description="Minimum photos required for a valid face cluster")
    classification_tag_threshold: float = Field(default=0.25, description="Classification tag confidence threshold")
    visual_evaluation_prompt: str = Field(default=DEFAULT_EVALUATION_PROMPT, description="Prompt for visual evaluation")
    visual_narrative_prompt: str = Field(default=DEFAULT_NARRATIVE_PROMPT, description="Prompt for narrative generation")
    # OCR settings can be added here later

class StorageSettings(BaseModel):
    photo_storage_path: str = Field(default="./data/uploads", description="Main photo storage root path")
    external_directories: List[str] = Field(default=[], description="List of external gallery directories")

class ImageSettings(BaseModel):
    thumbnail_quality: int = Field(default=80, description="Thumbnail quality (1-100)")
    preview_quality: int = Field(default=85, description="Preview image quality (1-100)")
    thumbnail_size: int = Field(default=250, description="Thumbnail long edge size")
    preview_size: int = Field(default=1440, description="Preview long edge size")
    # Add other image settings here

class FilterSettings(BaseModel):
    enable: bool = Field(default=False, description="Enable file filtering")
    min_size_kb: int = Field(default=0, description="Minimum file size in KB")
    min_width: int = Field(default=0, description="Minimum image width")
    min_height: int = Field(default=0, description="Minimum image height")
    filename_patterns: List[str] = Field(default=[], description="List of regex patterns to filter out files")

class MapSettings(BaseModel):
    provider: str = Field(default="tianditu", description="Map provider (tianditu, amap, baidu)")
    api_keys: List[str] = Field(default=[], description="Map API Key")

class AppSettings(BaseModel):
    version: str = "0.4.0"
    ai: AISettings = Field(default_factory=AISettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    image: ImageSettings = Field(default_factory=ImageSettings)
    filter: FilterSettings = Field(default_factory=FilterSettings)
    map: MapSettings = Field(default_factory=MapSettings)

    class Config:
        arbitrary_types_allowed = True

class ConfigManager:
    _instance = None
    _user_config_ctx = ContextVar("user_config", default=None)
    
    # LRU Cache for user configurations
    _user_cache: OrderedDict = OrderedDict()
    _cache_size = 100
    _cache_ttl = 5.0  # seconds
    config = AppSettings()
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def get_user_config(self, user_id: UUID, db: Session) -> AppSettings:
        """
        Get user configuration with LRU caching.
        Checks cache first, then DB.
        """
        # Check cache
        if user_id in self._user_cache:
            config, ts = self._user_cache[user_id]
            # Check TTL to ensure freshness across processes
            if time.time() - ts < self._cache_ttl:
                self._user_cache.move_to_end(user_id)
                return config

        # Load from DB
        from app.db.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        
        if user and user.settings:
            config = self.merge_user_settings(user.settings)
        else:
            config = self.merge_user_settings({})
        
        # Update cache
        self._user_cache[user_id] = (config, time.time())
        self._user_cache.move_to_end(user_id)
        
        # Maintain cache size
        if len(self._user_cache) > self._cache_size:
            self._user_cache.popitem(last=False)
            
        return config

    def update_user_config(self, user_id: UUID, settings: dict, db: Session) -> AppSettings:
        """
        Update user configuration in DB and cache.
        """
        from app.db.models.user import User
        from sqlalchemy.orm.attributes import flag_modified

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Merge existing settings with new settings
        current_settings = dict(user.settings) if user.settings else {}
        
        # Handle migration from old AI settings in DB
        if 'ai' in current_settings:
            ai_settings = current_settings['ai']
            if 'llm_settings' in ai_settings or 'llm_vl_settings' in ai_settings:
                ai_settings.pop('llm_settings', None)
                ai_settings.pop('llm_vl_settings', None)
                if 'connections' not in ai_settings:
                    ai_settings['connections'] = []
                if 'analysis_connection_id' not in ai_settings:
                    ai_settings['analysis_connection_id'] = ""
                if 'analysis_model_name' not in ai_settings:
                    ai_settings['analysis_model_name'] = ""

        # Deep merge helper
        def deep_merge(target, source):
            for key, value in source.items():
                if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                    deep_merge(target[key], value)
                else:
                    target[key] = value
            return target

        updated_settings = deep_merge(current_settings, settings)
        user.settings = updated_settings
        flag_modified(user, "settings")
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Update cache immediately
        new_config = self.merge_user_settings(updated_settings)
        self._user_cache[user_id] = (new_config, time.time())
        self._user_cache.move_to_end(user_id)
        
        return new_config

    def merge_user_settings(self, user_settings: Dict[str, Any]) -> AppSettings:
        """
        Merge default config with user settings.
        Returns a new AppSettings object with user overrides.
        """
        if user_settings is None:
            user_settings = {}

        # Handle migration from old AI settings
        if 'ai' in user_settings:
            ai_settings = user_settings['ai']
            if 'llm_settings' in ai_settings or 'llm_vl_settings' in ai_settings:
                ai_settings.pop('llm_settings', None)
                ai_settings.pop('llm_vl_settings', None)
                if 'connections' not in ai_settings:
                    ai_settings['connections'] = []
                if 'analysis_connection_id' not in ai_settings:
                    ai_settings['analysis_connection_id'] = ""
                if 'analysis_model_name' not in ai_settings:
                    ai_settings['analysis_model_name'] = ""

        # Start with default config as base
        current_data = AppSettings().model_dump()

        # Deep merge user settings
        def deep_merge(target, source):
            for key, value in source.items():
                if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                    deep_merge(target[key], value)
                else:
                    target[key] = value
            return target

        merged_data = deep_merge(current_data, user_settings)
        
        # Ensure built-in AI connection exists and is synced with ai_api_url
        ai_settings = merged_data.get('ai', {})
        connections = ai_settings.get('connections', [])
        ai_api_url = ai_settings.get('ai_api_url', os.getenv("AI_API_URL", "http://localhost:8001"))
        builtin_api_base = f"{ai_api_url}/v1"
        
        builtin_exists = False
        for conn in connections:
            if conn.get('id') == 'builtin':
                builtin_exists = True
                conn['api_base'] = builtin_api_base
                break
        
        if not builtin_exists:
            connections.insert(0, {
                'id': 'builtin',
                'provider': 'Built-in AI',
                'api_base': builtin_api_base,
                'api_key': 'empty',
                'model_names': ['MiniCPM-V-4_6-Q4_K_M'],
                'enable': True
            })
        ai_settings['connections'] = connections
        
        return AppSettings(**merged_data)

    def get_default_config(self) -> Dict[str, Any]:
        """Return the default config as a dict."""
        return self.merge_user_settings({}).model_dump()

os.makedirs('./data', exist_ok=True)
os.makedirs('./data/uploads', exist_ok=True)
# Global instance
config_manager = ConfigManager()
VERSION = "0.4.0"