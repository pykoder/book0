from pathlib import Path

import pytest
from book0_core.models import BookDetails
from book0_core.testing import (
    build_calibre_metadata_db,
    build_many_books_db,
    expected_details_with_cover,
    reset_pg_schema,
    seed_pg_library,
    start_test_pg,
    stop_test_pg,
)


@pytest.fixture
def calibre_metadata_db(tmp_path: Path) -> Path:
    return build_calibre_metadata_db(tmp_path / "metadata.db")


@pytest.fixture
def many_books_db(tmp_path: Path) -> Path:
    return build_many_books_db(tmp_path / "metadata.db")


@pytest.fixture
def expected_book_details(
    calibre_metadata_db: Path,
) -> tuple[BookDetails, BookDetails, BookDetails]:
    """Expected BookDetails with absolute cover_path values for the fixture library."""
    return expected_details_with_cover(calibre_metadata_db.parent)


@pytest.fixture(scope="session")
def pg_dsn():
    """PostgreSQL docker jetable (postgres:16-alpine, port libre, 60 s max)."""
    dsn, name = start_test_pg()
    try:
        yield dsn
    finally:
        stop_test_pg(name)


@pytest.fixture
def pg_schema(pg_dsn):
    """Réinitialise le schéma public et applique la DDL calibre_pg_sync."""
    reset_pg_schema(pg_dsn)
    yield pg_dsn


@pytest.fixture
def pg_library_root(tmp_path: Path) -> Path:
    """Répertoire racine de la bibliothèque PG seedée (pour les cover_path)."""
    root = tmp_path / "grimoire-test"
    root.mkdir()
    return root


@pytest.fixture
def pg_library(pg_dsn, pg_schema, pg_library_root: Path) -> str:
    """Bibliothèque PG 'grimoire-test' seedée à l'identique de calibre_metadata_db."""
    return seed_pg_library(pg_dsn, pg_library_root)
