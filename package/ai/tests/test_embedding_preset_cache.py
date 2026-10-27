import asyncio
from collections import OrderedDict
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_embedding]


def wrapper(model_id, direction):
    from app.services.embedding_service import ONNXCLIPTextWrapper
    model = ONNXCLIPTextWrapper.__new__(ONNXCLIPTextWrapper)
    model.model_id = model_id
    model._text_cache = OrderedDict()
    model._text_cache_lock = threading.Lock()
    model.encode_text = MagicMock(side_effect=lambda texts: np.tile(direction, (len(texts), 1)))
    return model


def test_cached_texts_deduplicate_bound_memory_and_protect_return_values():
    model = wrapper('one', [1., 0.])
    output = model.encode_text_cached(['春', '春', '冬'])
    assert model.encode_text.call_args.args[0] == ['春', '冬']
    output[0, 0] = 99
    assert model.encode_text_cached(['春'])[0, 0] == 1
    assert model.encode_text.call_count == 1
    model.encode_text_cached([str(i) for i in range(100)])
    assert len(model._text_cache) == 64


def test_preset_cache_follows_selected_model_instance(monkeypatch):
    from app.services import embedding_service as module
    old = wrapper('old', [1., 0.])
    new = wrapper('new', [0., 1.])
    state = {'id': 'old', 'wrapper': old}
    monkeypatch.setattr(module.ai_model_manager, 'is_ready', lambda *a: True)
    monkeypatch.setattr(module.ai_model_manager, 'get_selected_id', lambda *a: state['id'])
    monkeypatch.setattr(module.model_manager, 'get_model', lambda *a: state['wrapper'])
    service = module.EmbeddingService.__new__(module.EmbeddingService)
    for _ in range(2):
        assert asyncio.run(service.embed_texts(['质量照片'], use_cache=True)) == [[1., 0.]]
    assert old.encode_text.call_count == 1
    state.update(id='new', wrapper=new)
    assert asyncio.run(service.embed_texts(['质量照片'], use_cache=True)) == [[0., 1.]]
    assert new.encode_text.call_count == 1
    state['wrapper'] = old  # A stale instance must never serve its old cache.
    with pytest.raises(RuntimeError, match='not ready'):
        asyncio.run(service.embed_texts(['质量照片'], use_cache=True))


def test_text_api_accepts_cache_hint_without_changing_response_contract(monkeypatch):
    from app.routers import embedding
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock
    encode = AsyncMock(return_value=[[1., 0.]])
    monkeypatch.setattr(embedding.embedding_service, 'embed_texts', encode)
    app = FastAPI()
    app.include_router(embedding.router)
    with TestClient(app) as client:
        response = client.post('/text', json={'texts': ['春'], 'cache': True})
    assert response.json() == [[1., 0.]]
    encode.assert_awaited_once_with(['春'], use_cache=True)


@pytest.mark.model
def test_real_ranking_prompts_change_with_chinese_clip_and_legacy_model(monkeypatch):
    import ast
    from pathlib import Path
    from app.services import embedding_service as module
    repo = Path(__file__).resolve().parents[3]
    roots = [repo / 'package/ai/data/models' / name / 'text'
             for name in ['chinese-clip-vit-b16', 'clip-vit-b32']]
    if not all((root / 'textual.onnx').exists() for root in roots):
        pytest.skip('Both local ONNX model packages required')
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    monkeypatch.setattr(module, 'create_inference_session',
                        lambda path: ort.InferenceSession(path, options, providers=['CPUExecutionProvider']))
    tree = ast.parse((repo / 'package/server/app/crud/search_vector.py').read_text(encoding='utf-8'))
    prompts = next(ast.literal_eval(n.value) for n in tree.body
                   if isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id == 'SEARCH_PROMPTS' for x in n.targets))
    assert len(prompts) == 6
    results = []
    for index, root in enumerate(roots):
        current = module.ONNXCLIPTextWrapper(str(root))
        current.model_id = str(index)
        original = current.encode_text
        current.encode_text = MagicMock(wraps=original)
        monkeypatch.setattr(module.ai_model_manager, 'is_ready', lambda *a: True)
        monkeypatch.setattr(module.ai_model_manager, 'get_selected_id', lambda *a: str(index))
        monkeypatch.setattr(module.model_manager, 'get_model', lambda *a: current)
        service = module.EmbeddingService.__new__(module.EmbeddingService)
        result = np.asarray(asyncio.run(service.embed_texts(list(prompts.values()), use_cache=True)))
        repeated = np.asarray(asyncio.run(service.embed_texts(list(prompts.values()), use_cache=True)))
        assert result.shape == (6, 512) and np.isfinite(result).all()
        np.testing.assert_allclose(np.linalg.norm(result, axis=1), 1, atol=1e-6)
        np.testing.assert_array_equal(result, repeated)
        assert current.encode_text.call_count == 1
        results.append(result)
    assert not np.allclose(*results)
