"""Shared test environment.

These variables must be set before any test module imports
``requirement_platform.config`` because Settings is a module-level singleton.
Keeping the setup in conftest.py makes collection order irrelevant.
"""
import atexit
import os
import sys
import tempfile
from pathlib import Path

TEST_DIR = tempfile.TemporaryDirectory()
os.environ["RP_DATABASE_URL"] = f"sqlite:///{Path(TEST_DIR.name) / 'requirements.db'}"
os.environ["RP_JWT_SECRET"] = "test-secret-that-is-long-enough-for-tests"
os.environ["RP_GITHUB_TOKEN"] = ""
os.environ["RP_UPLOAD_DIR"] = str(Path(TEST_DIR.name) / "uploads")
os.environ["RP_WEB_URL"] = "https://feedback.trailsnap.cn"
os.environ["RP_MCP_PUBLIC_URL"] = "https://feedback.trailsnap.cn/mcp/"

# An explicit prefix would leak into every URL assertion in the existing suite.
os.environ.pop("RP_BASE_PATH", None)


@atexit.register
def cleanup_test_environment():
    db_module = sys.modules.get("requirement_platform.db")
    if db_module is not None:
        db_module.engine.dispose()
    TEST_DIR.cleanup()
