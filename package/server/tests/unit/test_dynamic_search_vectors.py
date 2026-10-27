from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
import requests

pytestmark = [pytest.mark.smoke, pytest.mark.module_embedding]


def test_presets_use_current_user_service_each_time_instead_of_stale_server_cache(monkeypatch):
    from app.crud import search_vector as module
    monkeypatch.setattr(module.config_manager, 'get_user_config',
                        lambda user, db: SimpleNamespace(ai=SimpleNamespace(ai_api_url=f'http://{user}/')))
    responses = [SimpleNamespace(raise_for_status=lambda: None, json=lambda: [[2., 0.] + [0.] * 510]),
                 SimpleNamespace(raise_for_status=lambda: None, json=lambda: [[0., 2.] + [0.] * 510])]
    post = MagicMock(side_effect=responses)
    monkeypatch.setattr(module.requests, 'post', post)
    first = module.get_search_vectors(None, 'one', keys=['春'])
    second = module.get_search_vectors(None, 'two', keys=['春'])
    assert first['春'][:2] == [1., 0.] and second['春'][:2] == [0., 1.]
    assert post.call_args_list[0].args[0] == 'http://one/embedding/text'
    assert post.call_args_list[1].args[0] == 'http://two/embedding/text'
    assert post.call_args.kwargs['json'] == {'texts': [module.SEARCH_PROMPTS['春']], 'cache': True}


@pytest.mark.parametrize('payload', [[], [[0.] * 512], [[1., 0.]], [[float('nan')] * 512]])
def test_invalid_vectors_never_fall_back_to_old_constants(monkeypatch, payload):
    from app.crud import search_vector as module
    monkeypatch.setattr(module.config_manager, 'get_user_config', lambda *a: SimpleNamespace(ai=SimpleNamespace(ai_api_url='http://ai')))
    monkeypatch.setattr(module.requests, 'post', lambda *a, **k: SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload))
    assert module.get_search_vectors(None, keys=['春']) == {}


def test_unavailable_model_keeps_report_usable_without_old_vector(monkeypatch, face_sqlite_session):
    from app.crud import search_vector as module
    from app.crud import annual_report as report
    monkeypatch.setattr(module.config_manager, 'get_user_config', lambda *a: SimpleNamespace(ai=SimpleNamespace(ai_api_url='http://ai')))
    monkeypatch.setattr(module.requests, 'post', MagicMock(side_effect=requests.ConnectionError('offline')))
    from datetime import datetime
    assert module.get_search_vectors(None) == {}
    result = report.get_report_easter_egg(datetime(2025, 1, 1), datetime(2025, 12, 31), face_sqlite_session)
    assert 'picsum.photos' in result.bestPhotoUrl


def test_image_search_uses_current_embedding_image_api(monkeypatch):
    import asyncio
    import io
    from fastapi import UploadFile
    from app.api import search as module
    class Response:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def json(self): return [[1., 0.]]
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        post = MagicMock(return_value=Response())
    monkeypatch.setattr(module.aiohttp, 'ClientSession', Client)
    monkeypatch.setattr(module.config_manager, 'get_user_config', lambda *a: SimpleNamespace(ai=SimpleNamespace(ai_api_url='http://ai/')))
    vectors = MagicMock(return_value=[])
    monkeypatch.setattr(module.crud_vector, 'search_similar_vectors', vectors)
    monkeypatch.setattr(module, '_build_vector_search_response', lambda *a: [])
    result = asyncio.run(module.search_by_image(UploadFile(file=io.BytesIO(b'image'), filename='photo.jpg'),
                                               limit=10, threshold=0., db=MagicMock(), user=SimpleNamespace(id='owner')))
    assert result.code == 200
    assert Client.post.call_args.args[0] == 'http://ai/embedding/image'
    assert Client.post.call_args.kwargs['json'] == {'images': ['aW1hZ2U=']}
    assert vectors.call_args.args[1] == [1., 0.]
