import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_embedding]


def test_text_wrapper_supplies_chinese_clip_three_int64_inputs():
    from app.services.embedding_service import ONNXCLIPTextWrapper
    wrapper = ONNXCLIPTextWrapper.__new__(ONNXCLIPTextWrapper)
    wrapper.max_length = 52
    wrapper.tokenizer = MagicMock(return_value={
        'input_ids': np.array([[101, 102]], dtype=np.int32),
        'attention_mask': np.array([[1, 1]], dtype=np.int32),
    })
    wrapper.text_session = MagicMock()
    wrapper.text_session.get_inputs.return_value = [SimpleNamespace(name=n) for n in ['input_ids', 'attention_mask', 'token_type_ids']]
    wrapper.text_session.run.return_value = [np.ones((1, 512), dtype=np.float32)]
    result = wrapper.encode_text(['中文'])
    feed = wrapper.text_session.run.call_args.args[1]
    assert all(value.dtype == np.int64 for value in feed.values())
    assert not feed['token_type_ids'].any()
    assert wrapper.tokenizer.call_args.kwargs['max_length'] == 52
    assert np.linalg.norm(result[0]) == pytest.approx(1)


def test_old_default_upgrades_once_and_explicit_old_choice_survives_restart(tmp_path, monkeypatch):
    from app.services.unified_model_manager import UnifiedModelManager
    from app.services import unified_model_manager as module
    catalog = Path(module.__file__).parents[1] / 'model_catalog.json'
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'version': 1, 'selections': {'embedding': 'embedding-clip-vit-b32'}}), encoding='utf-8')
    monkeypatch.setenv('AI_CONFIG_PATH', str(config))
    monkeypatch.setenv('AI_MODEL_CATALOG_PATH', str(catalog))
    monkeypatch.setattr(module.settings, 'MODEL_PATH', str(tmp_path / 'models'))
    manager = UnifiedModelManager()
    assert manager.get_selected_id('embedding') == 'embedding-chinese-clip-vit-b16'
    saved = json.loads(config.read_text(encoding='utf-8'))
    assert saved['version'] == 2
    saved['selections']['embedding'] = 'embedding-clip-vit-b32'
    config.write_text(json.dumps(saved), encoding='utf-8')
    assert UnifiedModelManager().get_selected_id('embedding') == 'embedding-clip-vit-b32'


@pytest.mark.model
def test_prepared_chinese_clip_package_matches_verified_embeddings(monkeypatch):
    repo = Path(__file__).resolve().parents[3]
    evaluation = repo / 'output/clip-evaluation-20261026'
    package = repo / 'output/models/modelscope/chinese-clip-vit-b16-onnx'
    if not (package / 'text/textual.onnx').exists() or not (evaluation / 'manifest.json').exists():
        pytest.skip('Local exported model and evaluation fixture required')
    import onnxruntime as ort
    from PIL import Image
    from app.services import embedding_service as module
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    monkeypatch.setattr(module, 'create_inference_session', lambda path: ort.InferenceSession(path, opts, providers=['CPUExecutionProvider']))
    manifest = json.loads((evaluation / 'manifest.json').read_text(encoding='utf-8'))
    text = module.ONNXCLIPTextWrapper(str(package / 'text'))
    result = text.encode_text([q['text'] for q in manifest['queries'][:3]])
    np.testing.assert_allclose(result, np.load(evaluation / 'candidate-onnx-text.npy')[:3], atol=2e-5, rtol=1e-4)
    image = module.ONNXCLIPImageWrapper(str(package / 'image'))
    images = []
    for image_id in manifest['image_ids'][:3]:
        with Image.open(evaluation / 'images' / f'{image_id}.jpg') as im:
            images.append(im.convert('RGB'))
    actual = image.encode_image(images)
    expected = np.load(evaluation / 'candidate-onnx-image.npy')[:3]
    # Pillow/Transformers versions can round bicubic pixels differently.
    # Verify the normalized retrieval direction across these runtime versions.
    assert actual.shape == (3, 512)
    np.testing.assert_allclose(np.linalg.norm(actual, axis=1), 1, atol=1e-6)
    assert np.all(np.sum(actual * expected, axis=1) > .9999)
