"""
AI smoke 测试 —— 共享环境变量加载校验（无模型、无服务，秒级）。

证明 tests/.env.test 已被 AI 测试加载，与后端/前端/docker 读同一份文件。
真正的模型推理测试（带 @pytest.mark.model）后续单独添加，默认不跑。
"""
import os

import pytest

pytestmark = [pytest.mark.smoke]


def test_shared_env_loaded():
    assert os.environ.get("TS_TEST_ENV"), "TS_TEST_ENV 未设置——tests/.env.test 未加载"


def test_ai_api_url_loaded():
    assert os.environ.get("TS_AI_API_URL"), "TS_AI_API_URL 未设置——tests/.env.test 未加载"
