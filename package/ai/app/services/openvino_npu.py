"""Run complete desktop ONNX graphs on NPU with bounded static input shapes."""

import functools
import logging
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from onnxruntime import InferenceSession

from app.services.desktop_device import record_session

logger = logging.getLogger(__name__)
_compile_lock = threading.Lock()
_DET_CANVASES = ((2048, 2048), (2048, 1152), (1152, 2048), (1024, 1024),
                 (1536, 1536), (3072, 768), (768, 3840))
_REC_WIDTHS = (320, 480, 640, 896, 1152, 1536, 2048, 3072, 4096)


@functools.lru_cache(maxsize=1)
def _core():
    from openvino import Core

    return Core()


def _ports(ports):
    return [
        SimpleNamespace(
            name=port.get_any_name(),
            shape=[dim.get_length() if dim.is_static else None for dim in port.partial_shape],
        )
        for port in ports
    ]


def _resize_nchw(array, height, width):
    import cv2

    return np.stack([
        cv2.resize(image.transpose(1, 2, 0), (width, height), interpolation=cv2.INTER_AREA)
        .transpose(2, 0, 1)
        for image in array
    ])


class OpenVINONPUSession(InferenceSession):
    # RapidOCR checks the ORT session type. Override its session interface
    # without allocating an ORT execution graph.
    def __init__(self, model_path, device, *, ocr_stage=None, fixed_dimensions=None):
        self._path = str(model_path)
        self._device = device
        self._stage = ocr_stage
        self._lock = threading.Lock()
        self._requests = {}
        self._failures = {}
        try:
            self._graph = _core().read_model(self._path)
            self._inputs = _ports(self._graph.inputs)
            self._outputs = _ports(self._graph.outputs)
            self._shapes = self._static_shapes(fixed_dimensions or {})
        except Exception as exc:
            record_session(self._path, [], str(exc))
            raise

    def _static_shapes(self, fixed_dimensions):
        if self._stage:
            return None
        shapes = []
        for port in self._inputs:
            shape = list(port.shape)
            for axis, value in fixed_dimensions.items():
                if shape[axis] is None:
                    shape[axis] = value
            if shape and shape[0] is None:
                shape[0] = 1
            if None in shape:
                raise ValueError(f"{Path(self._path).name}: no fixed NPU shape for {port.name} {port.shape}")
            shapes.append(tuple(shape))
        return tuple(shapes)

    def get_inputs(self):
        return self._inputs

    def get_outputs(self):
        return self._outputs

    def get_providers(self):
        return ["OpenVINOExecutionProvider"]

    @functools.cached_property
    def _metadata(self):
        import onnx

        graph = onnx.load(self._path, load_external_data=False)
        return SimpleNamespace(custom_metadata_map={item.key: item.value for item in graph.metadata_props})

    def get_modelmeta(self):
        return self._metadata

    def _infer(self, shapes, inputs, indices):
        with self._lock:
            if shapes in self._failures:
                raise RuntimeError(self._failures[shapes])
            new_shape = shapes not in self._requests
            try:
                if new_shape:
                    with _compile_lock:
                        graph = self._graph.clone()
                        graph.reshape(dict(enumerate(shapes)))
                        model = _core().compile_model(graph, self._device, {"PERFORMANCE_HINT": "LATENCY"})
                        devices = model.get_property("EXECUTION_DEVICES")
                        if isinstance(devices, str):
                            devices = [devices]
                        if not devices or any(device.split(".", 1)[0] != "NPU" for device in devices):
                            raise RuntimeError(f"Expected NPU execution, got {devices}")
                        self._requests[shapes] = model.create_infer_request()
                    logger.info("Compiled %s on %s for %s", self._path, devices, shapes)
                request = self._requests[shapes]
                request.infer(dict(enumerate(inputs)))
                outputs = [request.get_output_tensor(index).data.copy() for index in indices]
                if new_shape:
                    self._record()
                return outputs
            except Exception as exc:
                self._requests.pop(shapes, None)
                self._failures[shapes] = f"{Path(self._path).name} {shapes}: {exc}"
                self._record()
                raise RuntimeError(self._failures[shapes]) from exc

    def _record(self):
        error = next(reversed(self._failures.values()), None)
        record_session(self._path, self.get_providers() if self._requests else [], error)

    def _run_ocr(self, array, indices):
        batch, channels, height, width = array.shape
        if self._stage == "Det" and batch == 1 and channels == 3 and height and width:
            canvas = min((shape for shape in _DET_CANVASES if shape[0] >= height and shape[1] >= width),
                         key=lambda shape: shape[0] * shape[1], default=None)
            infer_h, infer_w = height, width
            if canvas is None:
                # A panorama outside the fixed canvases is reduced for the
                # detector. Restore the probability map for RapidOCR's boxes.
                def scale_to(shape):
                    return min(shape[0] / height, shape[1] / width)

                canvas = max(_DET_CANVASES, key=scale_to)
                scale = scale_to(canvas)
                infer_h = max(1, int(height * scale))
                infer_w = max(1, int(width * scale))
                array = _resize_nchw(array, infer_h, infer_w)
            padded = np.zeros((1, 3, *canvas), dtype=array.dtype)
            padded[:, :, :infer_h, :infer_w] = array
            outputs = [output[:, :, :infer_h, :infer_w]
                       for output in self._infer((padded.shape,), [padded], indices)]
            if (infer_h, infer_w) != (height, width):
                import cv2

                return [cv2.resize(output[0, 0], (width, height), interpolation=cv2.INTER_LINEAR)[None, None]
                        for output in outputs]
            return outputs
        if self._stage in ("Cls", "Rec") and 0 < batch <= 6 and channels == 3 and height == 48 and width:
            if self._stage == "Rec" and width > _REC_WIDTHS[-1]:
                width = _REC_WIDTHS[-1]
                array = _resize_nchw(array, height, width)
            widths = (192,) if self._stage == "Cls" else _REC_WIDTHS
            bucket = next((value for value in widths if value >= width), None)
            if bucket:
                padded = np.zeros((6, 3, 48, bucket), dtype=array.dtype)
                padded[:batch, :, :, :width] = array
                outputs = self._infer((padded.shape,), [padded], indices)
                if self._stage == "Rec":
                    # PP-OCRv6 CTC time steps shrink independently of vocabulary size.
                    return [output[:batch, :(width + 3) // 8] for output in outputs]
                return [output[:batch] for output in outputs]
        error = f"{Path(self._path).name}: unsupported NPU OCR input shape {array.shape}"
        record_session(self._path, self.get_providers() if self._requests else [], error)
        raise ValueError(error)

    def run(self, output_names, input_feed, run_options=None):
        names = [port.name for port in self._outputs]
        indices = [names.index(name) for name in output_names] if output_names else range(len(names))
        inputs = [input_feed[port.name] for port in self._inputs]
        if self._stage:
            return self._run_ocr(inputs[0], indices)
        if tuple(array.shape for array in inputs) == self._shapes:
            return self._infer(self._shapes, inputs, indices)
        # Dynamic CLIP image batches share a single compiled batch-one graph.
        batch = len(inputs[0])
        if batch > 1 and all(
            port.shape[0] is None and shape == (1, *array.shape[1:]) and len(array) == batch
            for port, shape, array in zip(self._inputs, self._shapes, inputs)
        ):
            outputs = [self._infer(self._shapes, [array[i:i + 1] for array in inputs], indices)
                       for i in range(batch)]
            return [np.concatenate(parts, axis=0) for parts in zip(*outputs)]
        raise ValueError(f"{Path(self._path).name}: expected NPU inputs {self._shapes}, got "
                         f"{[array.shape for array in inputs]}")
