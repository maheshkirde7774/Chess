"""
Pytest configuration and test database isolation for FOURX.
Ensures that all automated tests run against an isolated temporary SQLite database
and never modify or depend on the development database.
"""
import os
import sys
import tempfile
import pytest

# Ensure backend directory is on sys.path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(TESTS_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Configure an isolated temporary SQLite database before app modules load
_temp_dir = tempfile.mkdtemp(prefix="fourx_test_")
_test_db_path = os.path.join(_temp_dir, "test_fourx.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"

from app.db import init_db, engine

@pytest.fixture(scope="session", autouse=True)
def isolated_test_database():
    """Initializes schema once for the test session and cleans up temporary files on exit."""
    init_db()
    yield
    engine.dispose()
    try:
        if os.path.exists(_test_db_path):
            os.remove(_test_db_path)
        if os.path.exists(_temp_dir):
            os.rmdir(_temp_dir)
    except Exception:
        pass

