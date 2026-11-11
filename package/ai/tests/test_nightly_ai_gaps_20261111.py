"""Nightly coverage for the AI service modules flagged by the 2026-11-11 gap scan.

Targets (NIGHTLY-TEST-WATCH.md 4.2, coverage-gaps-ai.txt):
  services/ticket_journey_parser.py   -> 61-62, 107, 111-112
  services/embedding_service.py        -> 33-35, 143-144
  services/unified_model_manager.py    -> 137-138, 210, 377

All ticket fixtures are synthetic cards; no real passenger data is used.
"""

import json
import sys
import types

import numpy as np
import pytest

from app.services import embedding_service as embedding_module
from app.services.embedding_service import EmbeddingService, ONNXCLIPTextWrapper
from app.services.ticket_journey_parser import extract_journey_time
from app.services.unified_model_manager import UnifiedModelManager


pytestmark = pytest.mark.smoke


def card(*blocks):
    """Build a synthetic OCR card: (text, x, y) blocks."""
    texts, polys = [], []
    for text, x, y in blocks:
        texts.append(text)
        polys.append([[x, y], [x + 60, y], [x + 60, y + 20], [x, y + 20]])
    return texts, polys


# --------------------------------------------------------------------------- #
# services/ticket_journey_parser.py
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize('label', ['历时200小时', '1小时75分', '历时0小时'])
def test_out_of_range_duration_is_ignored(label):
    """A duration outside 1..10080 minutes (or with >= 60 minutes) is skipped."""
    texts, polys = card(('G123', 180, 100), (label, 180, 60))
    assert extract_journey_time(texts, polys, {'train_code': 'G123'}) == {}


def test_two_stations_sharing_one_clock_produce_no_duration():
    """The same clock point cannot be both departure and arrival (line 107)."""
    texts, polys = card(
        ('北京南', 20, 300),
        ('上海虹桥', 60, 300),
        ('08:20', 40, 260),
    )
    assert extract_journey_time(
        texts, polys, {'departure_station': '北京南', 'arrival_station': '上海虹桥'}
    ) == {}


def test_clocks_far_apart_in_a_horizontal_route_are_not_a_pair():
    """Two clocks on clearly different rows are not a departure/arrival pair."""
    texts, polys = card(
        ('北京南', 20, 100),
        ('上海虹桥', 360, 100),
        ('08:20', 20, 60),
        ('12:00', 360, 140),
    )
    assert extract_journey_time(
        texts, polys, {'departure_station': '北京南', 'arrival_station': '上海虹桥'}
    ) == {}


# --------------------------------------------------------------------------- #
# services/embedding_service.py
# --------------------------------------------------------------------------- #

def test_text_wrapper_reads_max_length_from_config(tmp_path, monkeypatch):
    """embedding_config.json overrides the default tokenizer max length."""
    (tmp_path / 'embedding_config.json').write_text(
        json.dumps({'max_length': 64}), encoding='utf-8'
    )

    fake_modelscope = types.ModuleType('modelscope')
    fake_modelscope.AutoTokenizer = types.SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: object()
    )
    monkeypatch.setitem(sys.modules, 'modelscope', fake_modelscope)
    monkeypatch.setattr(embedding_module, 'create_inference_session', lambda *a, **k: object())

    wrapper = ONNXCLIPTextWrapper(str(tmp_path))
    assert wrapper.max_length == 64


def test_text_wrapper_falls_back_to_default_max_length(tmp_path, monkeypatch):
    """Without a config file the wrapper keeps the 128 token default."""
    fake_modelscope = types.ModuleType('modelscope')
    fake_modelscope.AutoTokenizer = types.SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: object()
    )
    monkeypatch.setitem(sys.modules, 'modelscope', fake_modelscope)
    monkeypatch.setattr(embedding_module, 'create_inference_session', lambda *a, **k: object())

    wrapper = ONNXCLIPTextWrapper(str(tmp_path))
    assert wrapper.max_length == 128


@pytest.mark.asyncio
async def test_model_switched_during_encoding_is_rejected(monkeypatch):
    """The selected embedding model changed while encoding -> ask the user to retry."""
    service = EmbeddingService()

    class SwappingWrapper:
        model_id = 'embedding-clip-vit-b32'

        def encode_text(self, texts):
            # The user switched the model while the encoding was running.
            monkeypatch.setattr(
                embedding_module.ai_model_manager, 'get_selected_id',
                lambda task: 'embedding-chinese-clip-vit-b16',
            )
            return np.zeros((len(texts), 2), dtype=np.float32)

    monkeypatch.setattr(embedding_module.ai_model_manager, 'is_ready', lambda *a, **k: True)
    monkeypatch.setattr(
        embedding_module.ai_model_manager, 'get_selected_id',
        lambda task: 'embedding-clip-vit-b32',
    )
    monkeypatch.setattr(
        embedding_module.model_manager, 'get_model', lambda name: SwappingWrapper()
    )

    with pytest.raises(RuntimeError, match='Embedding model changed during encoding'):
        await service.embed_texts(['hello'])


# --------------------------------------------------------------------------- #
# services/unified_model_manager.py
# --------------------------------------------------------------------------- #

@pytest.fixture()
def model_manager(tmp_path, monkeypatch):
    """A UnifiedModelManager bound to a temporary model root and config file."""
    from app.config import settings

    monkeypatch.setattr(settings, 'MODEL_PATH', str(tmp_path / 'models'))
    config_path = tmp_path / 'ai_config.json'
    monkeypatch.setenv('AI_CONFIG_PATH', str(config_path))
    manager = UnifiedModelManager()
    return manager, config_path


def test_legacy_model_id_is_migrated_to_the_new_catalog_id(model_manager):
    """Old config files stored pre-catalog ids; they must be mapped forward."""
    manager, config_path = model_manager
    config_path.write_text(
        json.dumps({'models': {'face': {'selected': 'buffalo_s'}}}), encoding='utf-8'
    )

    manager = UnifiedModelManager()
    assert manager.get_selected_id('face') == 'face-buffalo-s'


def test_model_file_outside_the_model_root_is_rejected(model_manager):
    """get_model_file must refuse paths that escape the model root."""
    manager, _ = model_manager
    with pytest.raises(ValueError, match='模型文件路径越界'):
        manager.get_model_file('face', '../../../etc/passwd')


def test_prepare_model_rejects_a_candidate_without_a_repository(model_manager):
    """Candidates whose ModelScope repo is not published cannot be prepared."""
    manager, config_path = model_manager
    config_path.write_text(
        json.dumps({'selections': {'embedding': 'embedding-clip-vit-b16'}}), encoding='utf-8'
    )

    manager = UnifiedModelManager()
    with pytest.raises(ValueError, match='ModelScope 仓库尚未发布'):
        manager.prepare_model('embedding')
