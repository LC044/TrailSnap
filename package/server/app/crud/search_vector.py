"""Semantic ranking prompts encoded by the currently selected AI model.

Never persist model-specific preset vectors here: the AI service owns their
bounded, per-model-instance cache and releases it when the model changes.
"""
import logging

import requests

from app.core.config_manager import config_manager

logger = logging.getLogger(__name__)
SEARCH_PROMPTS = {
    "春": "清晰、曝光适当、色彩自然、构图优美的春天照片，盛开的花朵、嫩芽、新绿和明媚春光。",
    "夏": "清晰、曝光适当、色彩自然、构图优美的夏天照片，明亮的自然光、茂盛的绿叶、荷花和夏日生活。",
    "秋": "清晰、曝光适当、色彩自然、构图优美的秋天照片，柔和的暖光、金黄银杏、红色枫叶、落叶和晴朗秋空。",
    "冬": "清晰、曝光适当、色彩自然、构图优美的冬天照片，洁白雪景、雾凇、冬日暖阳和温暖生活。",
    "easter_egg": "一张值得珍藏的年度最佳照片，画面清晰、曝光准确、构图优美、色彩自然，记录旅行、风景、人像或温暖美好的生活瞬间。",
    "positive_sentiment": "那年今日 值得纪念的瞬间 生活美好瞬间 温馨日常 风景 人像 笑脸 旅行 节日 聚会 家庭 治愈 温暖 高光时刻",
}


def get_search_vectors(db, user_id=None, *, keys=None):
    """Batch encode presets; on failure use non-vector ranking, never old vectors.

    No server-side model cache: every call reaches this user's configured AI
    service so switches in other server processes/clients also take effect.
    Older AI services ignore the cache hint and still return fresh vectors.
    """
    keys = tuple(SEARCH_PROMPTS) if keys is None else tuple(keys)
    if not keys:
        return {}
    texts = [SEARCH_PROMPTS[key] for key in keys]
    try:
        api_url = config_manager.get_user_config(user_id, db).ai.ai_api_url.rstrip('/')
        response = requests.post(api_url + '/embedding/text',
                                 json={'texts': texts, 'cache': True}, timeout=(5, 30))
        response.raise_for_status()
        values = response.json()
        if not isinstance(values, list) or len(values) != len(keys):
            raise ValueError('Unexpected preset embedding count')
        import numpy as np
        vectors = np.asarray(values, dtype=np.float32)
        if vectors.shape != (len(keys), 512) or not np.isfinite(vectors).all():
            raise ValueError('Invalid preset embedding shape or values')
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if (norms <= 1e-12).any():
            raise ValueError('Empty preset embedding')
        vectors /= norms
        return dict(zip(keys, vectors.tolist()))
    except Exception:
        logger.warning('Current-model ranking presets unavailable; using score/time fallback', exc_info=True)
        return {}
