import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.model_phase import ModelPhaseCoordinator, ModelPhaseMiddleware
from app.services.model_manager import ModelManager

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
async def test_same_family_parallel_different_family_waits_for_all_requests():
    prepare = AsyncMock()
    coordinator = ModelPhaseCoordinator(prepare)
    first, second = asyncio.Event(), asyncio.Event()
    started = []
    async def request(family, done):
        async with coordinator.slot(family):
            started.append(family)
            await done.wait()
    a = asyncio.create_task(request('classification', first))
    b = asyncio.create_task(request('classification', second))
    for _ in range(10):
        if len(started) == 2:
            break
        await asyncio.sleep(0)
    assert started == ['classification', 'classification']
    face_done = asyncio.Event()
    face = asyncio.create_task(request('face', face_done))
    first.set(); await a
    await asyncio.sleep(0)
    assert started == ['classification', 'classification']
    second.set(); await b
    for _ in range(10):
        if len(started) == 3:
            break
        await asyncio.sleep(0)
    assert started[-1] == 'face'
    assert [call.args[0] for call in prepare.call_args_list] == ['classification', 'face']
    face_done.set(); await face


def test_release_previous_models_keeps_ticket_dependencies():
    manager = object.__new__(ModelManager)
    manager.models = {name: MagicMock() for name in ['face', 'ocr', 'tickets_yolo', 'clip_image', 'yolo_photo_cls_general']}
    manager.release_except('tickets')
    for name, wrapper in manager.models.items():
        assert wrapper.release.call_count == (0 if name in {'ocr', 'tickets_yolo'} else 1)


@pytest.mark.asyncio
async def test_stream_holds_model_until_final_response_body(monkeypatch):
    monkeypatch.setattr('app.core.model_phase.settings.AI_SINGLE_MODEL_FAMILY', True)
    stream_started, finish_stream = asyncio.Event(), asyncio.Event()
    order = []
    async def app(scope, receive, send):
        order.append(scope['path'])
        if scope['path'].startswith('/v1/'):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            stream_started.set()
            await finish_stream.wait()
        await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
    middleware = ModelPhaseMiddleware(app)
    middleware.coordinator.prepare = AsyncMock()
    receive, send = AsyncMock(), AsyncMock()
    stream = asyncio.create_task(middleware({'type': 'http', 'method': 'POST', 'path': '/v1/chat/completions'}, receive, send))
    await stream_started.wait()
    face = asyncio.create_task(middleware({'type': 'http', 'method': 'POST', 'path': '/face/face-recognition'}, receive, send))
    await asyncio.sleep(0)
    assert order == ['/v1/chat/completions']
    finish_stream.set()
    await asyncio.gather(stream, face)
    assert order == ['/v1/chat/completions', '/face/face-recognition']


@pytest.mark.asyncio
async def test_cancelled_request_drains_before_switching_models(monkeypatch):
    monkeypatch.setattr('app.core.model_phase.settings.AI_SINGLE_MODEL_FAMILY', True)
    started, finish = asyncio.Event(), asyncio.Event()
    order = []
    async def app(scope, receive, send):
        order.append(scope['path'])
        if scope['path'].startswith('/face/'):
            started.set()
            await finish.wait()
    middleware = ModelPhaseMiddleware(app)
    middleware.coordinator.prepare = AsyncMock()
    face = asyncio.create_task(middleware({'type': 'http', 'method': 'POST', 'path': '/face/face-recognition'}, AsyncMock(), AsyncMock()))
    await started.wait()
    face.cancel()
    ocr = asyncio.create_task(middleware({'type': 'http', 'method': 'POST', 'path': '/ocr/predict'}, AsyncMock(), AsyncMock()))
    await asyncio.sleep(0)
    assert order == ['/face/face-recognition']
    assert not face.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await face
    await ocr
    assert order == ['/face/face-recognition', '/ocr/predict']
