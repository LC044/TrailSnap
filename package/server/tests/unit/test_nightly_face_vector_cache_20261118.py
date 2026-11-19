"""Nightly 2026-11-18: app/service/face_vector_cache.py 向量归一化盲区。"""
import numpy as np
import pytest

from app.service.face_vector_cache import _pack, normalise_matrix

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def test_normalise_matrix_normalises_rows():
    rows = np.array([[3.0, 4.0], [0.0, 5.0]], dtype=np.float32)
    result = normalise_matrix(rows)
    assert np.allclose(np.linalg.norm(result, axis=1), np.array([1.0, 1.0]), atol=1e-6)


def test_normalise_matrix_leaves_zero_rows_as_zero():
    rows = np.array([[0.0, 0.0], [3.0, 4.0]], dtype=np.float32)
    result = normalise_matrix(rows)
    assert np.allclose(result[0], np.array([0.0, 0.0]))
    assert not np.isnan(result).any()


def test_normalise_matrix_handles_empty_block():
    rows = np.zeros((0, 4), dtype=np.float32)
    result = normalise_matrix(rows)
    assert result.shape == (0, 4)


def test_pack_builds_zero_block_for_empty_input():
    block = _pack([], 4)
    assert block.shape == (0, 4)


def test_pack_keeps_valid_vectors():
    block = _pack([[3.0, 4.0]], 2)
    assert np.allclose(np.linalg.norm(block, axis=1), np.array([1.0]), atol=1e-6)


def test_pack_skips_none_and_mismatched_dimensions():
    block = _pack([None, [1.0, 2.0, 3.0], [1.0, 0.0]], 2)
    assert block.shape == (3, 2)
    # None 与维度不符的行保持全零（距离 1.0，永不成为近邻）
    assert np.allclose(block[0], np.array([0.0, 0.0]))
    assert np.allclose(block[1], np.array([0.0, 0.0]))
    assert np.allclose(np.linalg.norm(block[2]), 1.0, atol=1e-6)
