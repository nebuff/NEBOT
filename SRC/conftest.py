"""
conftest.py — shared pytest fixtures for all NeBot test modules.

Ensures that every test runs against the same isolated SQLite database and
starts with a clean configuration state, regardless of which test files are
collected together in the same pytest process.
"""
import pytest
import test_db_helper
import db_service


@pytest.fixture(autouse=True)
def _reset_shared_state():
    """
    Re-initialise the shared test database and in-memory config dict before
    every test so cross-module contamination is impossible.
    """
    # Re-point db_service to the unified test DB and rebuild its schema
    test_db_helper.init_test_db()

    # Clear the in-memory guild / plurality caches that are shared globals
    try:
        import configuration_module
        configuration_module.guild_configs.clear()
    except Exception:
        pass

    try:
        import plurality_module
        plurality_module.plurality_data.clear()
    except Exception:
        pass

    yield

    # Teardown: close any open connection so the next test gets a fresh one
    db_service.close_db_connection()
