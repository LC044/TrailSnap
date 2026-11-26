"""Nightly watch 2026-11-26 · app/services/openvino_npu.py 的盲区。

AI 服务的定向覆盖显示 ``app/services/openvino_npu.py`` 只有 59% 覆盖：
既有测试只覆盖了「分片填充 / 全景缩放 / 非 NPU 设备拒绝 / 动态 batch」这几条主路径，
下面这些分支从未被触达：

- ``_ports``：静态 / 动态维度的端口描述
- ``_static_shapes``：动态 batch 归一、fixed_dimensions 补齐、无法确定时报错
- ``__init__``：模型读取失败时登记会话失败并向上抛
- ``_infer``：已缓存的失败、单字符串设备名、成功路径与失败登记
- ``_run_ocr``：不支持的输入形状、Rec 阶段超宽输入的缩放
- ``run``：按 stage 分流、形状完全匹配、形状不匹配报错
- ``get_modelmeta``：读取 onnx metadata props

全部用假的 graph / core / onnx 模块驱动，不需要真的 OpenVINO 运行时。
"""

import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from app.services import openvino_npu
from app.services.openvino_npu import OpenVINONPUSession


def fake_port(name, shape):
    """构造一个只有 ``partial_shape`` 语义的假端口。"""
    dims = []
    for value in shape:
        if value is None:
            dims.append(SimpleNamespace(is_static=False, get_length=lambda: None))
        else:
            dims.append(SimpleNamespace(is_static=True, get_length=lambda v=value: v))
    return SimpleNamespace(
        get_any_name=lambda: name,
        partial_shape=dims,
        shape=list(shape),
        name=name,
    )


def make_session(**attrs):
    session = OpenVINONPUSession.__new__(OpenVINONPUSession)
    session._path = "model.onnx"
    session._device = "NPU"
    session._stage = None
    session._lock = threading.Lock()
    session._requests = {}
    session._failures = {}
    for key, value in attrs.items():
        setattr(session, key, value)
    return session


# --- _ports / _static_shapes -----------------------------------------


def test_ports_map_static_and_dynamic_dimensions():
    ports = openvino_npu._ports([fake_port("input", [None, 3, 224, 224])])

    assert len(ports) == 1
    assert ports[0].name == "input"
    assert ports[0].shape == [None, 3, 224, 224]


def test_static_shapes_default_the_dynamic_batch_dimension():
    session = make_session(_inputs=[fake_port("input", [None, 3, 8, 8])])

    shapes = session._static_shapes({})

    assert shapes == ((1, 3, 8, 8),)


def test_static_shapes_apply_the_requested_fixed_dimensions():
    session = make_session(_inputs=[fake_port("input", [None, 3, None, 8])])

    shapes = session._static_shapes({2: 16})

    assert shapes == ((1, 3, 16, 8),)


def test_static_shapes_reject_a_shape_that_cannot_be_pinned():
    session = make_session(_inputs=[fake_port("input", [None, None, 3])])

    with pytest.raises(ValueError, match="no fixed NPU shape"):
        session._static_shapes({})


def test_static_shapes_are_skipped_for_a_staged_ocr_session():
    session = make_session(_stage="Det", _inputs=[fake_port("input", [None, None, 3])])

    assert session._static_shapes({}) is None


# --- __init__ --------------------------------------------------------


def test_init_records_a_failed_model_read_and_reraises(monkeypatch):
    recorded = []
    monkeypatch.setattr(openvino_npu, "_core", lambda: (_ for _ in ()).throw(RuntimeError("no core")))
    monkeypatch.setattr(openvino_npu, "record_session", lambda *args: recorded.append(args))

    with pytest.raises(RuntimeError, match="no core"):
        OpenVINONPUSession("broken.onnx", "NPU")

    assert recorded == [("broken.onnx", [], "no core")]


# --- _infer ----------------------------------------------------------


def test_infer_replays_a_cached_failure_without_recompiling(monkeypatch):
    compiled = []
    monkeypatch.setattr(
        openvino_npu, "_core",
        lambda: SimpleNamespace(compile_model=lambda *a: compiled.append(a)),
    )
    monkeypatch.setattr(openvino_npu, "record_session", lambda *args: None)
    session = make_session(_graph=SimpleNamespace(clone=lambda: SimpleNamespace(reshape=lambda _: None)))
    session._failures[((1, 3),)] = "model.onnx boom"

    with pytest.raises(RuntimeError, match="boom"):
        session._infer(((1, 3),), [], [0])

    assert compiled == []


def test_infer_accepts_a_single_string_device_name(monkeypatch):
    recorded = []

    class Request:
        def infer(self, _feed):
            return None

        def get_output_tensor(self, index):
            return SimpleNamespace(data=np.array([index], dtype=np.float32))

    model = SimpleNamespace(
        get_property=lambda name: "NPU.0",
        create_infer_request=Request,
    )
    monkeypatch.setattr(
        openvino_npu, "_core",
        lambda: SimpleNamespace(compile_model=lambda *a: model),
    )
    monkeypatch.setattr(openvino_npu, "record_session", lambda *args: recorded.append(args))
    session = make_session(_graph=SimpleNamespace(clone=lambda: SimpleNamespace(reshape=lambda _: None)))

    outputs = session._infer(((1, 3),), [np.zeros((1, 3))], [0])

    assert outputs[0].tolist() == [0]
    assert recorded and recorded[0][0] == "model.onnx"


def test_infer_registers_the_failure_and_raises_runtime_error(monkeypatch):
    recorded = []

    def compile_model(*_args):
        raise RuntimeError("compile failed")

    monkeypatch.setattr(openvino_npu, "_core", lambda: SimpleNamespace(compile_model=compile_model))
    monkeypatch.setattr(openvino_npu, "record_session", lambda *args: recorded.append(args))
    session = make_session(_graph=SimpleNamespace(clone=lambda: SimpleNamespace(reshape=lambda _: None)))

    with pytest.raises(RuntimeError, match="compile failed"):
        session._infer(((1, 3),), [], [0])

    assert session._failures[((1, 3),)].startswith("model.onnx")
    assert recorded


# --- _run_ocr --------------------------------------------------------


def test_run_ocr_rejects_an_unsupported_input_shape(monkeypatch):
    recorded = []
    monkeypatch.setattr(openvino_npu, "record_session", lambda *args: recorded.append(args))
    session = make_session(_stage="Det")

    with pytest.raises(ValueError, match="unsupported NPU OCR input shape"):
        session._run_ocr(np.zeros((2, 3, 64, 64), dtype=np.float32), [0])

    assert recorded


def test_run_ocr_shrinks_a_recogniser_input_wider_than_the_buckets(monkeypatch):
    seen = {}

    def infer(shapes, feeds, indices):
        seen["shapes"] = shapes
        seen["feed"] = feeds[0]
        return [np.ones((6, 8, 4), dtype=np.float32)]

    session = make_session(_stage="Rec")
    session._infer = infer

    outputs = session._run_ocr(np.ones((1, 3, 48, 5000), dtype=np.float32), [0])

    assert seen["shapes"][0][-1] == openvino_npu._REC_WIDTHS[-1]
    assert outputs[0].shape[0] == 1


# --- run -------------------------------------------------------------


def test_run_delegates_to_the_ocr_stage():
    session = make_session(_stage="Cls")
    seen = {}
    session._inputs = [SimpleNamespace(name="x")]
    session._outputs = [SimpleNamespace(name="y")]

    def run_ocr(array, indices):
        seen["array"] = array
        seen["indices"] = indices
        return ["ocr"]

    session._run_ocr = run_ocr
    array = np.ones((1, 3, 48, 192), dtype=np.float32)

    assert session.run(None, {"x": array}) == ["ocr"]
    assert seen["indices"] == range(1)


def test_run_uses_the_infer_path_for_matching_shapes():
    session = make_session()
    session._inputs = [SimpleNamespace(name="x", shape=[1, 2])]
    session._outputs = [SimpleNamespace(name="y")]
    session._shapes = ((1, 2),)
    seen = {}

    def infer(shapes, inputs, indices):
        seen["shapes"] = shapes
        seen["indices"] = indices
        return ["ok"]

    session._infer = infer
    array = np.zeros((1, 2), dtype=np.float32)

    assert session.run(["y"], {"x": array}) == ["ok"]
    assert seen["shapes"] == ((1, 2),)
    assert list(seen["indices"]) == [0]


def test_run_rejects_an_input_that_does_not_match_the_compiled_shape():
    session = make_session()
    session._inputs = [SimpleNamespace(name="x", shape=[1, 2])]
    session._outputs = [SimpleNamespace(name="y")]
    session._shapes = ((1, 2),)

    with pytest.raises(ValueError, match="expected NPU inputs"):
        session.run(["y"], {"x": np.zeros((3, 2), dtype=np.float32)})


# --- get_modelmeta ---------------------------------------------------


def test_model_metadata_is_read_from_the_onnx_graph(monkeypatch):
    fake_onnx = SimpleNamespace(
        load=lambda path, load_external_data=False: SimpleNamespace(
            metadata_props=[SimpleNamespace(key="author", value="TrailSnap")],
        )
    )
    monkeypatch.setitem(sys.modules, "onnx", fake_onnx)
    session = make_session(_path="model.onnx")

    meta = session.get_modelmeta()

    assert meta.custom_metadata_map == {"author": "TrailSnap"}

