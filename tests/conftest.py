"""
Pytest configuration & shared fixtures for the PanelMind test suite.

Run all tests with:
    cd /c/Users/Abdullah/Documents/PTTP
    python -m pytest tests/ -v

Or just the persistence tests:
    python -m pytest tests/persistence/ -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import AsyncIterator

import pytest

# ─── sys.path setup ───────────────────────────────────────────────
# The legacy code in `backend/` imports sibling modules with bare names
# (e.g. `from orchestrator import ...`). To make that work without
# restructuring the legacy code, we add `backend/` itself to sys.path
# for the duration of the test session.
#
# The new code in `backend/persistence/` uses absolute imports
# (`from backend.persistence.repository import ...`) so it works
# without this. The legacy tests need both: backend/ on path so the
# legacy modules import, AND project root so `backend.*` resolves.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
for path in (PROJECT_ROOT, BACKEND_DIR):
    p = str(path)
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture
def temp_sqlite_url() -> str:
    """Yield a fresh SQLite file URL for each test, then clean it up."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="panelmind_test_")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{path}"
    try:
        yield url
    finally:
        # On Windows, SQLite connections may still hold the file open for a
        # moment after the session closes. Swallow PermissionError so the
        # test doesn't fail on cleanup — the OS will clean up the temp file.
        try:
            os.unlink(path)
        except (FileNotFoundError, PermissionError):
            pass


@pytest.fixture
def anyio_backend() -> str:
    """Use the asyncio backend for anyio-based tests (default for our code)."""
    return "asyncio"
