"""One-time reset code generation and hashing."""
import hashlib

import pytest

from app.service.reset_code_store import CODE_DIGITS, _generate_code, _hash_code

pytestmark = [pytest.mark.smoke, pytest.mark.module_user]


def test_generate_code_has_fixed_width_digits():
    code = _generate_code()
    assert len(code) == CODE_DIGITS
    assert code.isdigit()


def test_generate_code_is_random():
    assert _generate_code() != _generate_code()


def test_hash_code_is_a_stable_sha256_digest():
    assert _hash_code("123456") == hashlib.sha256(b"123456").hexdigest()


def test_hash_code_does_not_leak_the_plain_code():
    assert "123456" not in _hash_code("123456")
