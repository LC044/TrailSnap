"""Nightly gap coverage (2026-10-23) — ONNX 分类模型的装载路径。

2026-10-23 的 AI 覆盖率扫描显示 ``app/services/image_classification_service.py``
仍有 36 行未覆盖（整体 83.2%）。已有基线
（``test_nightly_image_classification_service_gaps_20260812.py``）是用
``ONNXModelWrapper.__new__`` 绕过 ``__init__`` 来测 ``__call__`` /
``_preprocess``，因此下面这几段仍然是真盲区：

* ``ONNXModelWrapper.__init__`` —— names 元数据解析、输入尺寸、batch 能力探测
* ``_load_general_model``      —— 通用模型路径解析与缺失时的兜底/报错
* ``_load_category_model``     —— 分类子模型装载（未知分类 / 文件缺失 / 正常装载）
* ``classify_yolo`` 批量路径里走小模型复核的那一段
"""

import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app.services import image_classification_service as module
from app.services.image_classification_service import ImageClassificationService, ONNXModelWrapper

pytestmark = pytest.mark.smoke


class _FakeSession:
    """最小可用的 ONNX session 替身。"""

    def __init__(self, names="{0: 'animal', 1: 'person'}", shape=(None, 3, 224, 224)):
        self._names = names
        self._shape = shape
        self.run_calls = []

    def get_modelmeta(self):
        meta = MagicMock()
        meta.custom_metadata_map = {"names": self._names}
        return meta

    def get_inputs(self):
        node = MagicMock()
        node.name = "input"
        node.shape = list(self._shape)
        return [node]

    def get_outputs(self):
        node = MagicMock()
        node.name = "output"
        return [node]

    def run(self, names, feeds):
        self.run_calls.append((names, feeds))
        batch = np.asarray(next(iter(feeds.values()))).shape[0]
        return [np.zeros((batch, 2), dtype=np.float32)]


def _build_wrapper(shape=(None, 3, 224, 224), names="{0: 'animal', 1: 'person'}"):
    session = _FakeSession(names=names, shape=shape)
    with patch.object(module, "create_inference_session", return_value=session):
        wrapper = ONNXModelWrapper("photo-cls-general.onnx")
    return wrapper, session


def _bare_service(category_map=None):
    service = ImageClassificationService.__new__(ImageClassificationService)
    service._category_model_map = category_map or {}
    return service


# --------------------------------------------------------------------------
# ONNXModelWrapper.__init__
# --------------------------------------------------------------------------


def test_onnx_wrapper_parses_names_metadata_into_int_keys():
    wrapper, _ = _build_wrapper()

    assert wrapper.names == {0: "animal", 1: "person"}
    assert wrapper.input_name == "input"
    assert wrapper.output_name == "output"
    assert wrapper.model_name == "photo-cls-general.onnx"


def test_onnx_wrapper_invalid_names_metadata_falls_back_to_empty_dict():
    wrapper, _ = _build_wrapper(names="not-a-python-literal")

    assert wrapper.names == {}


def test_onnx_wrapper_uses_input_size_from_four_dim_shape():
    wrapper, _ = _build_wrapper(shape=(None, 3, 299, 299))

    assert wrapper.input_size == 299


def test_onnx_wrapper_defaults_input_size_when_shape_is_not_four_dim():
    wrapper, _ = _build_wrapper(shape=(3, 224, 224))

    assert wrapper.input_size == 224


def test_onnx_wrapper_fixed_batch_one_model_cannot_stack_batches():
    wrapper, _ = _build_wrapper(shape=(1, 3, 224, 224))

    assert wrapper._supports_batch is False
    assert wrapper._max_batch == 32


def test_onnx_wrapper_dynamic_batch_model_supports_batching():
    wrapper, _ = _build_wrapper(shape=("batch_size", 3, 224, 224))

    assert wrapper._supports_batch is True
    assert wrapper._max_batch == 32


def test_onnx_wrapper_fixed_batch_four_keeps_max_batch():
    wrapper, _ = _build_wrapper(shape=(4, 3, 224, 224))

    assert wrapper._supports_batch is True
    assert wrapper._max_batch == 4


def test_onnx_wrapper_call_with_empty_list_does_not_touch_session():
    wrapper, session = _build_wrapper()

    assert wrapper([]) == []
    assert session.run_calls == []


# --------------------------------------------------------------------------
# _load_general_model / _load_category_model
# --------------------------------------------------------------------------


def _patch_model_dir(tmp_path):
    manager = MagicMock()
    manager.require_ready.return_value = None
    manager.get_model_dir.return_value = str(tmp_path)
    return manager


def test_load_general_model_prefers_photo_cls_general_file(tmp_path):
    (tmp_path / "photo-cls-general.onnx").write_bytes(b"x")
    (tmp_path / "photo-cls-animal.onnx").write_bytes(b"x")
    service = _bare_service()

    captured = {}

    class _FakeWrapper:
        def __init__(self, path):
            captured["path"] = path

    with patch.object(module, "ai_model_manager", _patch_model_dir(tmp_path)), \
         patch.object(module, "ONNXModelWrapper", _FakeWrapper):
        service._load_general_model()

    assert os.path.basename(captured["path"]) == "photo-cls-general.onnx"


def test_load_general_model_falls_back_to_other_general_named_file(tmp_path):
    (tmp_path / "photo-cls-general-v2.onnx").write_bytes(b"x")
    service = _bare_service()

    captured = {}

    class _FakeWrapper:
        def __init__(self, path):
            captured["path"] = path

    with patch.object(module, "ai_model_manager", _patch_model_dir(tmp_path)), \
         patch.object(module, "ONNXModelWrapper", _FakeWrapper):
        service._load_general_model()

    assert os.path.basename(captured["path"]) == "photo-cls-general-v2.onnx"


def test_load_general_model_raises_when_no_general_model_exists(tmp_path):
    (tmp_path / "photo-cls-animal.onnx").write_bytes(b"x")
    service = _bare_service()

    with patch.object(module, "ai_model_manager", _patch_model_dir(tmp_path)):
        with pytest.raises(FileNotFoundError):
            service._load_general_model()


def test_load_category_model_returns_none_for_unknown_category(tmp_path):
    service = _bare_service({"animal": "photo-cls-animal.onnx"})

    with patch.object(module, "ai_model_manager", _patch_model_dir(tmp_path)):
        assert service._load_category_model("scenery") is None


def test_load_category_model_returns_none_when_file_missing(tmp_path):
    service = _bare_service({"animal": "photo-cls-animal.onnx"})

    with patch.object(module, "ai_model_manager", _patch_model_dir(tmp_path)):
        assert service._load_category_model("animal") is None


def test_load_category_model_loads_matching_file(tmp_path):
    (tmp_path / "photo-cls-animal.onnx").write_bytes(b"x")
    service = _bare_service({"animal": "photo-cls-animal.onnx"})

    captured = {}

    class _FakeWrapper:
        def __init__(self, path):
            captured["path"] = path

    with patch.object(module, "ai_model_manager", _patch_model_dir(tmp_path)), \
         patch.object(module, "ONNXModelWrapper", _FakeWrapper):
        service._load_category_model("animal")

    assert os.path.basename(captured["path"]) == "photo-cls-animal.onnx"


# --------------------------------------------------------------------------
# classify_yolo 的批量小模型复核路径
# --------------------------------------------------------------------------


def test_classify_yolo_batch_refines_label_with_small_model():
    """通用模型给出大类后，批量路径会用小模型复核并翻译标签。"""
    import base64
    import io

    service = _bare_service({"animal": "photo-cls-animal.onnx"})

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, format="PNG")
    payload = base64.b64encode(buffer.getvalue()).decode()

    general_model = MagicMock()
    general_model.names = {1: "animal"}
    general_model.return_value = [np.array([0.1, 0.9], dtype=np.float32)]

    small_model = MagicMock()
    small_model.names = {0: "dog"}
    small_model.return_value = [np.array([0.99, 0.01], dtype=np.float32)]

    manager = MagicMock()
    manager.is_ready.return_value = True
    manager.get_model.side_effect = lambda key: general_model if key.endswith("general") else small_model

    with patch.object(module, "ai_model_manager", manager), \
         patch.object(module, "model_manager", manager), \
         patch.object(ImageClassificationService, "_register_available_category_models", lambda self: None):
        results = service.classify_yolo([payload])

    # 小模型被调用，标签走 _translate_label 翻译成中文
    assert small_model.called
    assert results[0]["status"] == "success"
    assert results[0]["predictions"][0]["label"] == "狗"
    assert results[0]["predictions"][0]["confidence"] == pytest.approx(0.99, rel=1e-6)


def test_classify_yolo_batch_without_small_model_keeps_big_category():
    """大类没有对应的小模型时，直接用大类的中文名，置信度固定 0.9。"""
    import base64
    import io

    service = _bare_service({"animal": "photo-cls-animal.onnx"})

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, format="PNG")
    payload = base64.b64encode(buffer.getvalue()).decode()

    general_model = MagicMock()
    general_model.names = {1: "scenery"}
    general_model.return_value = [np.array([0.1, 0.9], dtype=np.float32)]

    manager = MagicMock()
    manager.is_ready.return_value = True
    manager.get_model.side_effect = lambda key: general_model

    with patch.object(module, "ai_model_manager", manager), \
         patch.object(module, "model_manager", manager), \
         patch.object(ImageClassificationService, "_register_available_category_models", lambda self: None):
        results = service.classify_yolo([payload])

    assert results == [{"status": "success", "predictions": [{"label": "风景", "confidence": 0.9}]}]