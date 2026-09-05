import hashlib
import os
import uuid
from datetime import datetime
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Json

from book0_core.errors import (
    AuthorNameMismatchError,
    AuthorNotFoundError,
    BookNotFoundError,
    InvalidAliasError,
    InvalidApplyNameError,
    InvalidExtractError,
    InvalidPatchError,
    LibraryNotFoundError,
    NoEpubError,
)
from book0_core.gateway import ReadLibraryGateway
from book0_core.models import (
    ApplyNameRequest,
    ApplyNameResult,
    Author,
    BookContent,
    BookPatch,
    BookQuery,
    BookSort,
    EditBooksResult,
    JobAction,
    JobFailure,
    JobOutcome,
    JobRequest,
    JobStatus,
    NameTargetById,
    NameTargetByName,
    Publisher,
    Series,
    SortOrder,
)
from book0_core.pg_gateway import PgLibraryGateway
from tests.conftest import (
    CALIBRE_LIBRARY_AUTHORS,
    CALIBRE_LIBRARY_BOOKS,
    CALIBRE_LIBRARY_PUBLISHERS,
    CALIBRE_LIBRARY_SERIES,
    GRIMOIRE_TEST_LIBRARY_UUID,
    PG_DUNE_EPUB_RELATIVE,
    _expected_details_with_cover,
    _write_minimal_epub,
)


def test_pg_gateway_satisfies_the_read_protocol(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    assert isinstance(gw, ReadLibraryGateway)

    gw.close()


def test_pg_list_books_matches_the_sqlite_fixture_seed(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    assert gw.list_books() == CALIBRE_LIBRARY_BOOKS


def test_pg_list_books_enrichi(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    books = {b.title: b for b in gw.list_books()}

    dune = books["Dune"]
    assert dune.publisher == Publisher(id="1", name="Ace Books")
    assert dune.series == Series(id="1", name="Dune Chronicles")
    assert dune.rating == 4  # Calibre raw rating 8 / 2 (0-10 -> 1-5 stars)
    assert dune.series_index == "1.0"
    assert dune.has_cover is True
    hobbit = books["The Hobbit"]
    assert hobbit.publisher is None
    assert hobbit.series is None
    assert hobbit.rating is None
    assert hobbit.has_cover is False


def test_pg_tag_inconnu_leve_library_not_found(pg_library):
    with pytest.raises(LibraryNotFoundError):
        PgLibraryGateway(pg_library, "inconnu")


def test_pg_list_authors_returns_authors_sorted_by_name(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    assert gw.list_authors() == CALIBRE_LIBRARY_AUTHORS


def test_pg_list_publishers_returns_publishers_sorted_by_name(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    assert gw.list_publishers() == CALIBRE_LIBRARY_PUBLISHERS


def test_pg_list_series_returns_series_sorted_by_name(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    assert gw.list_series() == CALIBRE_LIBRARY_SERIES


def test_pg_get_book_details_returns_details_with_cover_paths(
    pg_library, pg_library_root
):
    expected = _expected_details_with_cover(pg_library_root)
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.get_book_details(["1", "2", "3"])

    assert set(result.books) == set(expected)
    assert result.missing_ids == ()


def test_pg_get_book_details_reports_unknown_ids_as_missing(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.get_book_details(["1", "999", "abc"])

    assert len(result.books) == 1
    assert result.books[0].title == "Dune"
    assert set(result.missing_ids) == {"999", "abc"}


def test_pg_list_books_page_et_handle(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    page1 = gw.list_books_page(1, 2)

    assert len(page1.items) == 2
    assert page1.handle is not None
    assert page1.total_pages == 2

    page2 = gw.list_books_page(2, 2, page1.handle)

    assert len(page2.items) == 1
    assert page2.handle is None  # last page: no handle
    gw.close_pagination(page2.handle or "")
    gw.close()


def test_pg_list_books_page_cold_jump_to_a_later_page(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.list_books_page(2, 2)

    assert [book.title for book in result.items] == ["The Hobbit"]


def test_pg_list_authors_page_returns_the_requested_page(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.list_authors_page(1, 3)

    assert [author.name for author in result.items] == [
        "Frank Herbert",
        "J.R.R. Tolkien",
        "Neil Gaiman",
    ]
    assert result.total_pages == 2

    # A short (non-full) last page has no handle.
    second = gw.list_authors_page(2, 3, handle=result.handle)

    assert [author.name for author in second.items] == ["Terry Pratchett"]
    assert second.handle is None


def test_pg_list_publishers_page_returns_the_requested_page(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.list_publishers_page(1, 1)

    assert result.items == (Publisher(id="1", name="Ace Books"),)
    assert result.handle is not None


def test_pg_list_series_page_last_page_has_no_handle(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.list_series_page(1, 2)

    assert result.items == (Series(id="1", name="Dune Chronicles"),)
    assert result.handle is None


def test_pg_close_pagination_replays_from_a_fresh_fetch(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    first = gw.list_books_page(1, 2)
    assert first.handle is not None

    gw.close_pagination(first.handle)
    second = gw.list_books_page(2, 2, handle=first.handle)

    assert second.handle != first.handle
    assert [book.title for book in second.items] == ["The Hobbit"]


def test_pg_close_pagination_is_silent_and_idempotent(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.close_pagination("never-issued")
    gw.close_pagination("never-issued")

    gw.close()


def test_pg_query_books_filtre_tags(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.query_books_page(BookQuery(tags=("fantasy",)), 1, 100)

    assert {b.title for b in result.items} == {"Good Omens"}


def test_pg_query_books_filters_by_rating(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.query_books_page(BookQuery(ratings=(4,)), 1, 100)

    assert {b.title for b in result.items} == {"Dune"}


def test_pg_query_books_filters_by_pubdate_year_excluding_null_pubdate(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    by_1965 = gw.query_books_page(BookQuery(pubdate_years=(1965,)), 1, 100)
    by_1990 = gw.query_books_page(BookQuery(pubdate_years=(1990,)), 1, 100)

    assert {b.title for b in by_1965.items} == {"Dune"}
    # The Hobbit's NULL pubdate must not match any year filter.
    assert {b.title for b in by_1990.items} == {"Good Omens"}


def test_pg_query_books_filters_by_author_publisher_and_series_ids(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    by_author = gw.query_books_page(BookQuery(author_ids=("1",)), 1, 100)
    by_publisher = gw.query_books_page(BookQuery(publisher_ids=("2",)), 1, 100)
    by_series = gw.query_books_page(BookQuery(series_ids=("1",)), 1, 100)

    assert {b.title for b in by_author.items} == {"Dune"}
    assert {b.title for b in by_publisher.items} == {"Good Omens"}
    assert {b.title for b in by_series.items} == {"Dune"}


def test_pg_query_books_filters_by_language_and_format(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    by_language = gw.query_books_page(BookQuery(languages=("fra",)), 1, 100)
    by_format = gw.query_books_page(BookQuery(formats=("epub",)), 1, 100)

    assert {b.title for b in by_language.items} == {
        "Dune",
        "Good Omens",
        "The Hobbit",
    }
    assert {b.title for b in by_format.items} == {"Dune"}


def test_pg_query_books_combines_keys_with_and_and_values_with_or(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    either_tag = gw.query_books_page(BookQuery(tags=("sci-fi", "fantasy")), 1, 100)
    both_keys = gw.query_books_page(BookQuery(tags=("sci-fi",), ratings=(2,)), 1, 100)

    assert {b.title for b in either_tag.items} == {"Dune", "Good Omens"}
    assert both_keys.items == ()
    assert both_keys.handle is None
    assert both_keys.total_pages == 0


def test_pg_query_books_sorts_by_pubdate_desc_with_nulls_last(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.query_books_page(
        BookQuery(sort=BookSort.PUBDATE, order=SortOrder.DESC), 1, 100
    )

    assert [b.title for b in result.items] == [
        "Good Omens",  # 1990
        "Dune",  # 1965
        "The Hobbit",  # NULL pubdate
    ]


def test_pg_pubdate_sentinelle_calibre_est_neutralisee_en_null(
    pg_library_with_sentinel_pubdate,
):
    # La CASE de _PUBDATE_SQL (an 101 -> NULL) : la sentinelle Calibre
    # (calibre.utils.date.UNDEFINED_DATE) doit sortir comme un vrai NULL.
    gw = PgLibraryGateway(pg_library_with_sentinel_pubdate, "grimoire-test")

    books = {b.title: b for b in gw.list_books()}

    assert books["Sentinel Book"].pubdate is None


def test_pg_query_books_sorts_by_pubdate_asc_with_nulls_first(pg_library):
    # SQLite place les NULL en PREMIER en ASC ; PG les met en DERNIER par
    # défaut. Le ORDER BY de la passerelle doit forcer NULLS FIRST pour
    # rester aligné sur la sémantique SQLite (desc garde NULLS LAST).
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.query_books_page(BookQuery(sort=BookSort.PUBDATE), 1, 100)

    assert [b.title for b in result.items] == [
        "The Hobbit",  # NULL pubdate -> premier, sémantique SQLite ASC
        "Dune",  # 1965
        "Good Omens",  # 1990
    ]


def test_pg_query_books_sorts_by_author_sort_desc(pg_library):
    # The PG schema's books table HAS an author_sort column, so the AUTHOR sort
    # key is real here (unlike the SQLite fixture, which lacks the column).
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.query_books_page(
        BookQuery(sort=BookSort.AUTHOR, order=SortOrder.DESC), 1, 100
    )

    assert [b.title for b in result.items] == [
        "The Hobbit",  # "Tolkien, J.R.R."
        "Dune",  # "Herbert, Frank"
        "Good Omens",  # "Gaiman, Neil, Pratchett, Terry"
    ]


def test_pg_query_authors_page_returns_authors_of_the_filtered_books(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.query_authors_page(BookQuery(tags=("fantasy",)), 1, 100)

    assert set(result.items) == {
        Author(id="3", name="Neil Gaiman"),
        Author(id="4", name="Terry Pratchett"),
    }


def test_pg_query_publishers_page_returns_publishers_of_the_filtered_books(
    pg_library,
):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.query_publishers_page(BookQuery(tags=("sci-fi",)), 1, 100)

    assert set(result.items) == {Publisher(id="1", name="Ace Books")}


def test_pg_query_series_page_returns_series_of_the_filtered_books(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    sci_fi = gw.query_series_page(BookQuery(tags=("sci-fi",)), 1, 100)
    fantasy = gw.query_series_page(BookQuery(tags=("fantasy",)), 1, 100)

    assert set(sci_fi.items) == {Series(id="1", name="Dune Chronicles")}
    assert fantasy.items == ()
    assert fantasy.handle is None


def test_pg_list_field_values(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    values = {v.value: v.count for v in gw.list_field_values("ratings")}

    assert values == {"4": 1}


def test_pg_list_field_values_tags_languages_and_formats(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    tags = {v.value: v.count for v in gw.list_field_values("tags")}
    languages = {v.value: v.count for v in gw.list_field_values("languages")}
    formats = {v.value: v.count for v in gw.list_field_values("formats")}

    assert tags == {"classic": 1, "fantasy": 1, "humor": 1, "sci-fi": 1}
    assert languages == {"fra": 3}
    assert formats == {"EPUB": 1}


# --- edit_books : PATCH transactionnel avec dry_run (spec §7.1) ---
# Seed pg_library (identique à la fixture SQLite) : publisher local_id 1 =
# Ace Books, 2 = Gollancz ; series local_id 1 = Dune Chronicles ; language
# 'fra' (local_id 1) liée aux 3 livres ; Dune a la note 4 étoiles (raw 8).


def _pg_fetchone(dsn, sql, params=()):
    """SELECT brut pour les champs non exposés par la façade de lecture
    (comments, books_languages_link, books_series_link.ord)."""
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        conn.close()


def test_pg_edit_books_change_publisher(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.edit_books(["1"], BookPatch(publisher_id="2"))

    assert result == EditBooksResult(updated=("1",), missing_ids=())
    books = {b.title: b for b in gw.list_books()}
    assert books["Dune"].publisher == Publisher(id="2", name="Gollancz")
    gw.close()


def test_pg_edit_books_tags_remplace_la_liste(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.edit_books(["1"], BookPatch(tags=("nouveau",)))

    details = gw.get_book_details(["1"])
    assert details.books[0].tags == ("nouveau",)
    gw.close()


def test_pg_edit_books_tags_vide_efface_la_liste(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.edit_books(["3"], BookPatch(tags=()))

    details = gw.get_book_details(["3"])
    assert details.books[0].tags == ()
    gw.close()


def test_pg_edit_books_rating_1_5(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.edit_books(["2"], BookPatch(rating=3))

    assert {b.title: b for b in gw.list_books()}["The Hobbit"].rating == 3
    gw.close()


def test_pg_edit_books_rating_remplace_la_ligne_existante(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.edit_books(["1"], BookPatch(rating=2))

    assert {b.title: b for b in gw.list_books()}["Dune"].rating == 2
    gw.close()


def test_pg_edit_books_series_et_series_index(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.edit_books(["2"], BookPatch(series_id="1", series_index="3.5"))

    hobbit = {b.title: b for b in gw.list_books()}["The Hobbit"]
    assert hobbit.series == Series(id="1", name="Dune Chronicles")
    assert hobbit.series_index == "3.5"
    row = _pg_fetchone(
        pg_library,
        "SELECT ord FROM books_series_link WHERE book_pk = 2",
    )
    assert row == (3.5,)
    gw.close()


def test_pg_edit_books_serie_sans_index_conserve_l_index_courant(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.edit_books(["1"], BookPatch(series_index="7.0"))
    gw.edit_books(["1"], BookPatch(series_id="1"))

    dune = {b.title: b for b in gw.list_books()}["Dune"]
    assert dune.series_index == "7.0"
    row = _pg_fetchone(
        pg_library,
        "SELECT ord FROM books_series_link WHERE book_pk = 1",
    )
    assert row == (7.0,)
    gw.close()


def test_pg_edit_books_pubdate(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.edit_books(["2"], BookPatch(pubdate="1937-09-21"))

    assert {b.title: b for b in gw.list_books()}["The Hobbit"].pubdate == ("1937-09-21")
    gw.close()


def test_pg_edit_books_language_remplace_le_lien(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.edit_books(["1"], BookPatch(language="eng"))

    languages = {v.value: v.count for v in gw.list_field_values("languages")}
    assert languages == {"eng": 1, "fra": 2}
    gw.close()


def test_pg_edit_books_comments_upsert(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.edit_books(["1"], BookPatch(comments="Sonate des clairs de terre."))
    assert _pg_fetchone(pg_library, "SELECT text FROM comments WHERE book_pk = 1") == (
        "Sonate des clairs de terre.",
    )

    # Deuxième passe : la PK comments(book_pk) impose un upsert, pas un insert.
    gw.edit_books(["1"], BookPatch(comments="Mise à jour."))
    assert _pg_fetchone(pg_library, "SELECT text FROM comments WHERE book_pk = 1") == (
        "Mise à jour.",
    )
    gw.close()


def test_pg_edit_books_plusieurs_livres_dans_l_ordre_demande(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.edit_books(["3", "1"], BookPatch(rating=5))

    assert result == EditBooksResult(updated=("3", "1"), missing_ids=())
    books = {b.title: b for b in gw.list_books()}
    assert books["Good Omens"].rating == 5
    assert books["Dune"].rating == 5
    gw.close()


def test_pg_edit_books_dry_run_n_ecrit_rien(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    avant = gw.list_books()
    tags_avant = gw.list_field_values("tags")

    result = gw.edit_books(
        ["1"],
        BookPatch(
            publisher_id="2",
            series_index="9.9",
            tags=("nouveau",),
            rating=1,
            pubdate="2001-01-01",
            language="eng",
            comments="brouillon",
        ),
        dry_run=True,
    )

    # Même réponse qu'une exécution réelle...
    assert result == EditBooksResult(updated=("1",), missing_ids=())
    # ...mais aucune écriture, y compris pas de ligne tags orpheline.
    assert gw.list_books() == avant
    assert gw.list_field_values("tags") == tags_avant
    assert (
        _pg_fetchone(pg_library, "SELECT text FROM comments WHERE book_pk = 1") is None
    )
    gw.close()


def test_pg_edit_books_ids_inconnus_dans_missing(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.edit_books(["1", "9999"], BookPatch(rating=2))

    assert result.updated == ("1",)
    assert result.missing_ids == ("9999",)
    assert {b.title: b for b in gw.list_books()}["Dune"].rating == 2
    gw.close()


def test_pg_edit_books_patch_vide_leve_invalid_patch(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidPatchError):
        gw.edit_books(["1"], BookPatch())
    gw.close()


def test_pg_edit_books_ids_vides_leve_invalid_patch(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidPatchError):
        gw.edit_books([], BookPatch(rating=3))
    gw.close()


def test_pg_edit_books_publisher_inconnu_leve_invalid_patch(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidPatchError):
        gw.edit_books(["1"], BookPatch(publisher_id="9999"))
    gw.close()


def test_pg_edit_books_series_inconnue_leve_invalid_patch(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidPatchError):
        gw.edit_books(["1"], BookPatch(series_id="9999"))
    gw.close()


def test_pg_edit_books_rating_hors_echelle_leve_invalid_patch(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidPatchError):
        gw.edit_books(["1"], BookPatch(rating=7))
    gw.close()


def test_pg_edit_books_pubdate_invalide_leve_invalid_patch(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidPatchError):
        gw.edit_books(["1"], BookPatch(pubdate="pas-une-date"))
    gw.close()


def test_pg_edit_books_series_index_invalide_leve_invalid_patch(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidPatchError):
        gw.edit_books(["1"], BookPatch(series_index="abc"))
    gw.close()


# --- get_book_content : EPUB -> markdown via epub2md, cache disque mtime ---
# L'EPUB minimal de Dune (fixture pg_library) porte le titre « Livre Test ».


def _dune_epub_path(pg_library_root):
    return pg_library_root / PG_DUNE_EPUB_RELATIVE


def _cache_filename(book_id, level, epub_mtime, extract, library_uuid):
    library_hex = uuid.UUID(library_uuid).hex[:12]
    digest = hashlib.sha256((extract or "").encode()).hexdigest()[:12]
    return f"{library_hex}-{book_id}-{level}-{int(epub_mtime)}-{digest}.md"


def test_pg_get_book_content_convertit(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    content = gw.get_book_content("1", 7, None)

    assert content == BookContent(
        book_id="1", level=7, extract=None, markdown=content.markdown
    )
    assert "Livre Test" in content.markdown
    assert "Chapitre 1" in content.markdown and "Chapitre 2" in content.markdown
    gw.close()


def test_pg_get_book_content_passe_l_extract_a_epub2md(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    content = gw.get_book_content("1", 7, "1...1")

    assert content.extract == "1...1"
    assert "Chapitre 1" in content.markdown
    assert "Chapitre 2" not in content.markdown
    gw.close()


def test_pg_get_book_content_extract_invalide(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidExtractError):
        gw.get_book_content("1", 7, "pas-de-points")
    gw.close()


def test_pg_get_book_content_level_hors_bornes(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidExtractError):
        gw.get_book_content("1", 0, None)
    with pytest.raises(InvalidExtractError):
        gw.get_book_content("1", 8, None)
    gw.close()


def test_pg_get_book_content_livre_inconnu(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(BookNotFoundError):
        gw.get_book_content("9999", 7, None)
    gw.close()


def test_pg_get_book_content_sans_epub(pg_library):
    # The Hobbit (local_id 2) : aucune ligne data format='EPUB'.
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(NoEpubError):
        gw.get_book_content("2", 7, None)
    gw.close()


def test_pg_get_book_content_fichier_epub_manquant(pg_library, pg_library_root):
    _dune_epub_path(pg_library_root).unlink()
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(NoEpubError):
        gw.get_book_content("1", 7, None)
    gw.close()


def test_pg_get_book_content_cache_reutilise(pg_library, pg_library_root, tmp_path):
    cache_dir = tmp_path / "mdcache"
    gw = PgLibraryGateway(pg_library, "grimoire-test", markdown_cache_dir=cache_dir)
    epub_mtime = int(_dune_epub_path(pg_library_root).stat().st_mtime)

    first = gw.get_book_content("1", 7, None)

    cached = cache_dir / _cache_filename(
        "1", 7, epub_mtime, None, GRIMOIRE_TEST_LIBRARY_UUID
    )
    assert cached.is_file()
    assert cached.read_text(encoding="utf-8") == first.markdown

    # Un contenu sentinelle dans le cache est servi tel quel : pas de reconversion.
    cached.write_text("SENTINELLE", encoding="utf-8")
    second = gw.get_book_content("1", 7, None)
    assert second.markdown == "SENTINELLE"
    gw.close()


def test_pg_get_book_content_sans_cache_dir_ne_cree_rien(pg_library, tmp_path):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    content = gw.get_book_content("1", 7, None)

    assert "Livre Test" in content.markdown
    assert not (tmp_path / "mdcache").exists()
    gw.close()


def test_pg_get_book_content_cache_invalide_si_epub_change(
    pg_library, pg_library_root, tmp_path
):
    cache_dir = tmp_path / "mdcache"
    gw = PgLibraryGateway(pg_library, "grimoire-test", markdown_cache_dir=cache_dir)
    first = gw.get_book_content("1", 7, None)
    epub_path = _dune_epub_path(pg_library_root)
    old_mtime = int(epub_path.stat().st_mtime)

    # toucher l'EPUB avec un mtime nettement postérieur : nouvelle clé de cache.
    new_mtime = old_mtime + 10
    os.utime(epub_path, (new_mtime, new_mtime))

    second = gw.get_book_content("1", 7, None)

    assert second.markdown == first.markdown  # reconverti, pas l'ancien cache
    assert (
        cache_dir / _cache_filename("1", 7, new_mtime, None, GRIMOIRE_TEST_LIBRARY_UUID)
    ).is_file()
    gw.close()


def test_pg_get_book_content_cache_keys_distinctes_par_extract(
    pg_library, pg_library_root, tmp_path
):
    # Deux extracts distincts, même livre/level/mtime : deux fichiers de cache
    # distincts, chacun servant le markdown de son extract demandé.
    cache_dir = tmp_path / "mdcache"
    gw = PgLibraryGateway(pg_library, "grimoire-test", markdown_cache_dir=cache_dir)
    epub_mtime = int(_dune_epub_path(pg_library_root).stat().st_mtime)

    first = gw.get_book_content("1", 7, "1...1")
    second = gw.get_book_content("1", 7, "1...2")

    cache_first = cache_dir / _cache_filename(
        "1", 7, epub_mtime, "1...1", GRIMOIRE_TEST_LIBRARY_UUID
    )
    cache_second = cache_dir / _cache_filename(
        "1", 7, epub_mtime, "1...2", GRIMOIRE_TEST_LIBRARY_UUID
    )
    assert cache_first.is_file() and cache_second.is_file()
    assert cache_first != cache_second
    assert cache_first.read_text(encoding="utf-8") == first.markdown
    assert cache_second.read_text(encoding="utf-8") == second.markdown
    assert "Chapitre 1" in first.markdown and "Chapitre 2" not in first.markdown
    assert "Chapitre 2" in second.markdown
    gw.close()


def test_pg_get_book_content_cache_distinct_par_bibliotheque(
    pg_library, pg_library_root, tmp_path
):
    # Deux bibliothèques partageant le même répertoire de cache markdown, avec
    # un livre de même local_id et un EPUB de même mtime : deux fichiers de
    # cache distincts, chacune servant son propre markdown (jamais celui de
    # l'autre bibliothèque).
    cache_dir = tmp_path / "mdcache"
    gw1 = PgLibraryGateway(pg_library, "grimoire-test", markdown_cache_dir=cache_dir)
    epub1_mtime = int(_dune_epub_path(pg_library_root).stat().st_mtime)

    # Seconde bibliothèque seedée en SQL direct : local_id 1 identique, EPUB
    # avec exactement le même mtime, racine disque à elle.
    other_uuid = "9c4e7f21-0000-4000-8000-00000000ffff"
    other_root = tmp_path / "autre-lib"
    other_rel = Path("A. Auteur") / "Autre (1)"
    _write_minimal_epub(other_root / other_rel / "Autre.epub")
    other_epub = other_root / other_rel / "Autre.epub"
    os.utime(other_epub, (epub1_mtime, epub1_mtime))
    with psycopg.connect(pg_library) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO libraries (library_uuid, name, base_path)"
                " VALUES (%s, %s, %s)",
                (other_uuid, "autre-lib", str(other_root)),
            )
            cur.execute(
                "INSERT INTO books (library_uuid, local_id, uuid, title, title_sort,"
                " author_sort, pubdate, timestamp, last_modified, series_index, path,"
                " flags, has_cover)"
                " VALUES (%s, 1, 'uuid-autre-1', 'Autre', 'Autre', 'Auteur, A.',"
                " NULL, now(), now(), NULL, %s, 1, false) RETURNING book_pk",
                (other_uuid, "A. Auteur/Autre (1)/"),
            )
            other_book_pk = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO data (book_pk, format, name, uncompressed_size)"
                " VALUES (%s, %s, %s, %s)",
                (other_book_pk, "EPUB", "Autre", 671088),
            )
        conn.commit()

    gw2 = PgLibraryGateway(pg_library, "autre-lib", markdown_cache_dir=cache_dir)

    gw1.get_book_content("1", 7, None)
    cache1 = cache_dir / _cache_filename(
        "1", 7, epub1_mtime, None, GRIMOIRE_TEST_LIBRARY_UUID
    )
    assert cache1.is_file()
    cache1.write_text("SENTINELLE-LIB1", encoding="utf-8")

    second = gw2.get_book_content("1", 7, None)

    cache2 = cache_dir / _cache_filename("1", 7, epub1_mtime, None, other_uuid)
    assert cache1 != cache2
    assert cache2.is_file()
    assert second.markdown != "SENTINELLE-LIB1"  # jamais le cache de l'autre lib
    assert "Livre Test" in second.markdown
    # Re-lecture : chaque gateway reste servie par son propre fichier.
    assert gw1.get_book_content("1", 7, None).markdown == "SENTINELLE-LIB1"
    assert gw2.get_book_content("1", 7, None).markdown == second.markdown
    gw1.close()
    gw2.close()


def test_pg_get_book_content_extract_absent_du_document(pg_library):
    # Numéro d'élément inexistant dans l'EPUB : ValueError sémantique d'epub2md
    # (apply_extract), mappée en InvalidExtractError comme tout extract invalide.
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidExtractError):
        gw.get_book_content("1", 7, "9...9")
    gw.close()


# --- Jobs : persistance PG (spec §7.2) ---
# create_job insère en 'pending' ; get_job est scopé par library_uuid ;
# list_jobs_page trie created_at DESC avec filtres status/action optionnels ;
# mark_interrupted_jobs bascule les 'running' en 'interrupted' (crash/restart).


def test_pg_create_job_persiste_en_pending(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    job = gw.create_job(
        JobRequest(
            action=JobAction.CONVERT_MARKDOWN, book_ids=("1",), params={"level": 5}
        )
    )

    assert job.status is JobStatus.PENDING
    assert job.id
    assert job.outcome is None
    assert job.started_at is None and job.finished_at is None
    fetched = gw.get_job(job.id)
    assert fetched is not None
    assert fetched.action is JobAction.CONVERT_MARKDOWN
    assert fetched.status is JobStatus.PENDING
    # created_at : ISO 8601 UTC, suffixe 'Z' (format wire de la spec §7.2).
    assert fetched.created_at.endswith("Z")
    datetime.fromisoformat(fetched.created_at)
    # params sérialisés en jsonb tels quels.
    row = _pg_fetchone(
        pg_library, "SELECT params FROM jobs WHERE id = %s", (uuid.UUID(job.id),)
    )
    assert row == ({"level": 5},)
    gw.close()


def test_pg_create_job_params_absents_deviennent_un_objet_vide(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    job = gw.create_job(JobRequest(action=JobAction.SYNC_LIBRARY))

    row = _pg_fetchone(
        pg_library, "SELECT params FROM jobs WHERE id = %s", (uuid.UUID(job.id),)
    )
    assert row == ({},)
    gw.close()


def test_pg_get_job_inconnu_renvoie_none(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    assert gw.get_job("8f3a9c00-0000-0000-0000-000000000000") is None
    gw.close()


def test_pg_get_job_deserialise_l_outcome(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    job = gw.create_job(JobRequest(action=JobAction.CONVERT_MARKDOWN))

    with gw._connection.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status='done', started_at=now(), finished_at=now(),"
            " outcome=%s WHERE id=%s",
            (
                Json(
                    {
                        "succeeded": ["1"],
                        "failed": [{"id": "2", "reason": "NoEpubError"}],
                    }
                ),
                uuid.UUID(job.id),
            ),
        )
    fetched = gw.get_job(job.id)

    assert fetched is not None
    assert fetched.status is JobStatus.DONE
    assert fetched.outcome == JobOutcome(
        succeeded=("1",),
        failed=(JobFailure(id="2", reason="NoEpubError"),),
    )
    assert fetched.started_at is not None and fetched.finished_at is not None
    assert fetched.started_at.endswith("Z") and fetched.finished_at.endswith("Z")
    gw.close()


def test_pg_list_jobs_filtre_statut_et_action(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.create_job(JobRequest(action=JobAction.CONVERT_MARKDOWN))
    gw.create_job(JobRequest(action=JobAction.SYNC_LIBRARY))

    page = gw.list_jobs_page(
        status=None, action=JobAction.SYNC_LIBRARY, page=1, page_size=10
    )

    assert len(page.items) == 1
    assert page.items[0].action is JobAction.SYNC_LIBRARY
    gw.close()


def test_pg_list_jobs_filtre_statut(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    done_job = gw.create_job(JobRequest(action=JobAction.CONVERT_MARKDOWN))
    gw.create_job(JobRequest(action=JobAction.CONVERT_MARKDOWN))
    with gw._connection.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status='done', outcome=%s WHERE id=%s",
            (Json({"succeeded": [], "failed": []}), uuid.UUID(done_job.id)),
        )

    page = gw.list_jobs_page(status=JobStatus.DONE, action=None, page=1, page_size=10)

    assert len(page.items) == 1
    assert page.items[0].id == done_job.id
    assert page.items[0].status is JobStatus.DONE
    gw.close()


def test_pg_list_jobs_tri_created_at_desc_et_pagination(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    created = [
        gw.create_job(JobRequest(action=JobAction.CONVERT_MARKDOWN)) for _ in range(3)
    ]

    page = gw.list_jobs_page(status=None, action=None, page=1, page_size=2)

    # Les plus récents d'abord (chaque create_job est sa propre transaction,
    # donc created_at est strictement croissant).
    assert [j.id for j in page.items] == [created[2].id, created[1].id]
    assert page.handle is None  # jobs : pagination offset simple, pas de handle
    assert page.total_pages == 2
    assert page.has_more_than_shown is False

    page2 = gw.list_jobs_page(status=None, action=None, page=2, page_size=2)

    assert [j.id for j in page2.items] == [created[0].id]
    gw.close()


def test_pg_list_jobs_page_vide(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    page = gw.list_jobs_page(status=None, action=None, page=1, page_size=10)

    assert page.items == ()
    assert page.total_pages == 0
    gw.close()


def test_pg_mark_interrupted_jobs(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    job = gw.create_job(JobRequest(action=JobAction.CONVERT_MARKDOWN))
    pending = gw.create_job(JobRequest(action=JobAction.SYNC_LIBRARY))

    with gw._connection.cursor() as cur:  # simule un crash en pleine exécution
        cur.execute(
            "UPDATE jobs SET status='running', started_at=now() WHERE id=%s",
            (uuid.UUID(job.id),),
        )

    assert gw.mark_interrupted_jobs() == 1
    fetched = gw.get_job(job.id)
    assert fetched is not None
    assert fetched.status is JobStatus.INTERRUPTED
    assert fetched.finished_at is not None
    # Un job non running n'est pas touché.
    untouched = gw.get_job(pending.id)
    assert untouched is not None and untouched.status is JobStatus.PENDING
    # Rappel au démarrage sans running restant : plus rien à marquer.
    assert gw.mark_interrupted_jobs() == 0
    gw.close()


def test_pg_mark_interrupted_jobs_sans_tag_couvre_toutes_les_bibliotheques(
    pg_library,
):
    # Passerelle non scopée (tag=None, celle du hook lifespan du serveur) :
    # mark_interrupted_jobs couvre TOUTES les bibliothèques PG, pas seulement
    # une configurée dans le dict de config (vide en déploiement PG réel).
    gw = PgLibraryGateway(pg_library)
    other_uuid = "5b1a2c3d-0000-4000-8000-00000000ffff"
    job_a = "8f3a9c00-0000-4000-8000-0000000000aa"
    job_b = "8f3a9c00-0000-4000-8000-0000000000bb"
    with gw._connection.cursor() as cur:
        cur.execute(
            "INSERT INTO libraries (library_uuid, name, base_path)"
            " VALUES (%s, 'autre-lib', '/tmp/autre-lib')",
            (other_uuid,),
        )
        cur.executemany(
            "INSERT INTO jobs (id, library_uuid, action, status)"
            " VALUES (%s, %s, 'convert-markdown', 'running')",
            [
                (job_a, uuid.UUID(GRIMOIRE_TEST_LIBRARY_UUID)),
                (job_b, other_uuid),
            ],
        )

    assert gw.mark_interrupted_jobs() == 2

    with gw._connection.cursor() as cur:
        cur.execute(
            "SELECT id, status FROM jobs WHERE status = 'interrupted' ORDER BY id"
        )
        rows = cur.fetchall()
    assert [str(row[0]) for row in rows] == sorted([job_a, job_b])
    gw.close()


def test_pg_update_job_status_transitions_excecuteur(pg_library):
    """Le cycle de l'exécuteur de jobs : running (started_at posé), puis
    done/failed avec outcome (finished_at posé)."""
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    job = gw.create_job(JobRequest(action=JobAction.CONVERT_MARKDOWN))

    gw.update_job_status(job.id, JobStatus.RUNNING)
    running = gw.get_job(job.id)
    assert running is not None
    assert running.status is JobStatus.RUNNING
    assert running.started_at is not None
    assert running.outcome is None
    assert running.finished_at is None

    outcome = JobOutcome(
        succeeded=("1",),
        failed=(JobFailure(id="2", reason="NoEpubError"),),
    )
    gw.update_job_status(job.id, JobStatus.DONE, outcome)
    done = gw.get_job(job.id)
    assert done is not None
    assert done.status is JobStatus.DONE
    assert done.outcome == outcome
    assert done.finished_at is not None

    failed = gw.create_job(JobRequest(action=JobAction.SYNC_LIBRARY))
    gw.update_job_status(failed.id, JobStatus.RUNNING)
    gw.update_job_status(
        failed.id,
        JobStatus.FAILED,
        JobOutcome((), (JobFailure(id=failed.id, reason="boom"),)),
    )
    fetched = gw.get_job(failed.id)
    assert fetched is not None
    assert fetched.status is JobStatus.FAILED
    assert fetched.outcome is not None
    assert fetched.outcome.succeeded == ()
    assert fetched.outcome.failed[0].reason == "boom"
    gw.close()


def test_pg_lectures_de_jobs_globales_sans_tag(pg_library):
    """Une passerelle construite sans tag lit les jobs de TOUTES les
    bibliothèques (console de jobs du serveur) ; une passerelle taguée reste
    scopée à la sienne."""
    scoped = PgLibraryGateway(pg_library, "grimoire-test")
    job_scoped = scoped.create_job(JobRequest(action=JobAction.CONVERT_MARKDOWN))

    # Une seconde bibliothèque avec son propre job (via SQL direct : le
    # gateway est toujours scopé à un seul tag par construction).
    other_uuid = uuid.uuid4()
    other_job_id = uuid.uuid4()
    with psycopg.connect(pg_library) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO libraries (library_uuid, name, base_path)"
                " VALUES (%s, %s, %s)",
                (other_uuid, "autre-lib", "/tmp/autre-lib"),
            )
            cur.execute(
                "INSERT INTO jobs (id, library_uuid, action, status)"
                " VALUES (%s, %s, 'sync-library', 'pending')",
                (other_job_id, other_uuid),
            )
        conn.commit()

    # Lecture scopée : le job de l'autre bibliothèque est invisible.
    assert scoped.get_job(str(other_job_id)) is None
    page = scoped.list_jobs_page(None, None, 1, 10)
    assert [j.id for j in page.items] == [job_scoped.id]
    scoped.close()

    # Lecture globale (sans tag) : les jobs des deux bibliothèques.
    unscoped = PgLibraryGateway(pg_library)
    assert unscoped.get_job(str(other_job_id)) is not None
    assert unscoped.get_job(job_scoped.id) is not None
    all_ids = {j.id for j in unscoped.list_jobs_page(None, None, 1, 10).items}
    assert all_ids == {job_scoped.id, str(other_job_id)}
    unscoped.close()


# --- Groupes d'alias d'auteurs (author_entity / author_entity_member) ---
# Seed pg_library : auteurs local_id 1=Frank Herbert, 2=J.R.R. Tolkien,
# 3=Neil Gaiman, 4=Terry Pratchett - les 4 existent déjà, la fusion des
# groupes A (1,2) et B (3,4) n'a donc besoin d'aucun auteur supplémentaire.


def _add_alias(gw, a, b):
    return gw.add_author_alias(a, b)


def test_pg_get_aliases_sans_groupe(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    group = gw.get_author_aliases("1")

    assert group.group == ("1",) and group.names["1"]
    assert group.names == {"1": "Frank Herbert"}
    gw.close()


def test_pg_get_aliases_auteur_inconnu(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(AuthorNotFoundError):
        gw.get_author_aliases("9999")
    gw.close()


def test_pg_add_puis_get_aliases(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    group = _add_alias(gw, "1", "2")

    assert set(group.group) == {"1", "2"}
    assert group.names == {"1": "Frank Herbert", "2": "J.R.R. Tolkien"}
    assert set(gw.get_author_aliases("2").group) == {"1", "2"}
    gw.close()


def test_pg_add_alias_auto_association_rejetee(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidAliasError):
        _add_alias(gw, "1", "1")
    gw.close()


def test_pg_add_alias_inconnu_rejetee(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(AuthorNotFoundError):
        _add_alias(gw, "1", "9999")
    with pytest.raises(AuthorNotFoundError):
        _add_alias(gw, "9999", "1")
    gw.close()


def test_pg_fusion_de_deux_groupes(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.add_author_alias("1", "2")  # groupe A
    gw.add_author_alias("3", "4")  # groupe B

    group = gw.add_author_alias("1", "3")  # fusion

    assert set(group.group) == {"1", "2", "3", "4"}
    assert set(gw.get_author_aliases("4").group) == {"1", "2", "3", "4"}
    # La fusion est effective en base : une seule entité subsiste.
    with gw._connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM author_entity")
        assert cur.fetchone()[0] == 1
    gw.close()


def test_pg_add_alias_deja_dans_le_meme_groupe_est_sans_effet(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.add_author_alias("1", "2")

    group = gw.add_author_alias("2", "1")

    assert set(group.group) == {"1", "2"}
    with gw._connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM author_entity")
        assert cur.fetchone()[0] == 1
    gw.close()


def test_pg_display_author_est_l_auteur_createur_du_groupe(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    gw.add_author_alias("1", "2")

    row = _pg_fetchone(
        pg_library,
        "SELECT a.local_id FROM author_entity ae"
        " JOIN authors a ON a.id = ae.display_author_id",
    )
    assert row == (1,)
    gw.close()


def test_pg_remove_alias_puis_groupe_monopersonne_nettoye(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.add_author_alias("1", "2")

    group = gw.remove_author_alias("1", "2")

    assert group.group == ("1",)
    assert gw.get_author_aliases("2").group == ("2",)
    # plus aucune ligne author_entity résiduelle :
    with gw._connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM author_entity")
        assert cur.fetchone()[0] == 0
    gw.close()


def test_pg_remove_alias_garde_le_groupe_multi_membres(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.add_author_alias("1", "2")
    gw.add_author_alias("1", "3")

    group = gw.remove_author_alias("1", "2")

    assert set(group.group) == {"1", "3"}
    # L'alias détaché reste un auteur de la bibliothèque, sans groupe.
    assert gw.get_author_aliases("2").group == ("2",)
    gw.close()


def test_pg_remove_alias_hors_groupe_rejetee(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidAliasError):
        gw.remove_author_alias("1", "2")
    gw.close()


def test_pg_remove_alias_auto_association_rejetee(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidAliasError):
        gw.remove_author_alias("1", "1")
    gw.close()


# --- apply_author_name : correction en masse des graphies (spec §7.3) ---
# Seed pg_library : auteur 1 = Frank Herbert (livre 1 Dune), 2 = J.R.R. Tolkien
# (livre 2 The Hobbit), 3 = Neil Gaiman + 4 = Terry Pratchett (livre 3
# Good Omens, deux auteurs). Le brief se fonde sur les noms "Herbert, Frank"
# (les author_sort) ; les noms réels du seed sont "Frank Herbert", etc.


def test_pg_apply_name_par_id_repointe_les_livres(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.add_author_alias("1", "2")

    result = gw.apply_author_name(
        "1",
        ApplyNameRequest(match="^Frank Herbert$", target=NameTargetById(author_id="2")),
    )

    assert result == ApplyNameResult(applied=("1",), skipped=(), missing_ids=())
    books = {
        b.title for b in gw.query_books_page(BookQuery(author_ids=("2",)), 1, 100).items
    }
    assert {"Dune", "The Hobbit"} <= books
    # l'auteur source n'a plus aucun livre
    assert gw.query_books_page(BookQuery(author_ids=("1",)), 1, 100).items == ()
    gw.close()


def test_pg_apply_name_regexp_non_correspondante(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.add_author_alias("1", "2")

    with pytest.raises(AuthorNameMismatchError):
        gw.apply_author_name(
            "1",
            ApplyNameRequest(
                match="^nom qui n'existe pas$",
                target=NameTargetById(author_id="2"),
            ),
        )
    gw.close()


def test_pg_apply_name_regexp_invalide(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidApplyNameError):
        gw.apply_author_name(
            "1",
            ApplyNameRequest(match="(", target=NameTargetById(author_id="2")),
        )
    gw.close()


def test_pg_apply_name_cible_hors_groupe_rejetee(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(InvalidAliasError):
        gw.apply_author_name(
            "1", ApplyNameRequest(match=".", target=NameTargetById(author_id="2"))
        )  # 2 pas dans le groupe (aucun groupe)
    gw.close()


def test_pg_apply_name_par_name_cree_la_ligne_et_groupe(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.apply_author_name(
        "1",
        ApplyNameRequest(
            match="^Frank Herbert$", target=NameTargetByName(name="F. Herbert")
        ),
    )

    assert result.applied == ("1",)
    details = gw.get_book_details(["1"])
    assert "F. Herbert" in details.books[0].authors
    # la ligne auteur a été créée et fait partie du groupe de l'auteur 1
    group = gw.get_author_aliases("1")
    assert "F. Herbert" in set(group.names.values())
    gw.close()


def test_pg_apply_name_par_name_auteur_existant_rejoint_le_groupe(pg_library):
    # Cible par nom désignant un auteur EXISTANT hors groupe : il est admis
    # dans le groupe et les livres sont transférés (fusion par graphie).
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    result = gw.apply_author_name(
        "1",
        ApplyNameRequest(
            match="^Frank Herbert$",
            target=NameTargetByName(name="J.R.R. Tolkien"),
        ),
    )

    assert result.applied == ("1",)
    assert set(gw.get_author_aliases("1").group) == {"1", "2"}
    books = {
        b.title for b in gw.query_books_page(BookQuery(author_ids=("2",)), 1, 100).items
    }
    assert "Dune" in books
    gw.close()


def test_pg_apply_name_dry_run_n_ecrit_rien(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.add_author_alias("1", "2")
    avant = gw.query_books_page(BookQuery(author_ids=("1",)), 1, 100)

    result = gw.apply_author_name(
        "1",
        ApplyNameRequest(
            match="^Frank Herbert$",
            target=NameTargetById(author_id="2"),
            dry_run=True,
        ),
    )

    assert result.applied == ("1",)  # même réponse qu'une exécution réelle
    assert (
        gw.query_books_page(BookQuery(author_ids=("1",)), 1, 100).items == avant.items
    )
    # le groupe d'alias non plus n'a pas bougé
    assert gw.get_author_aliases("1").group == ("1", "2")
    gw.close()


def test_pg_apply_name_livres_non_lies_dans_skipped(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.add_author_alias("1", "2")

    result = gw.apply_author_name(
        "1",
        ApplyNameRequest(
            match="^Frank Herbert$",
            target=NameTargetById(author_id="2"),
            book_ids=("1", "3"),
        ),
    )  # livre 3 (Good Omens) sans l'auteur 1

    assert result == ApplyNameResult(applied=("1",), skipped=("3",), missing_ids=())
    # les autres auteurs du livre sauté ne sont jamais touchés
    details = gw.get_book_details(["3"])
    assert set(details.books[0].authors) == {"Neil Gaiman", "Terry Pratchett"}
    gw.close()


def test_pg_apply_name_ids_inconnus_dans_missing(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.add_author_alias("1", "2")

    result = gw.apply_author_name(
        "1",
        ApplyNameRequest(
            match="^Frank Herbert$",
            target=NameTargetById(author_id="2"),
            book_ids=("1", "999"),
        ),
    )

    assert result == ApplyNameResult(applied=("1",), skipped=(), missing_ids=("999",))
    gw.close()


def test_pg_apply_name_recannonicalise_display_author(pg_library):
    # Décision liée de la revue T7 : quand la cible résout vers un auteur
    # différent du display_author_id du groupe, le groupe est re-canonisé.
    gw = PgLibraryGateway(pg_library, "grimoire-test")
    gw.add_author_alias("1", "2")  # display = 1 (créateur)
    row = _pg_fetchone(
        pg_library,
        "SELECT a.local_id FROM author_entity ae"
        " JOIN authors a ON a.id = ae.display_author_id",
    )
    assert row == (1,)

    gw.apply_author_name(
        "1",
        ApplyNameRequest(match="^Frank Herbert$", target=NameTargetById(author_id="2")),
    )

    row = _pg_fetchone(
        pg_library,
        "SELECT a.local_id FROM author_entity ae"
        " JOIN authors a ON a.id = ae.display_author_id",
    )
    assert row == (2,)
    gw.close()


def test_pg_apply_name_cible_soi_meme_leve_invalid_apply(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    # par id : cible = l'auteur lui-même
    with pytest.raises(InvalidApplyNameError):
        gw.apply_author_name(
            "1", ApplyNameRequest(match=".", target=NameTargetById(author_id="1"))
        )
    # par name : le nom résout vers l'auteur lui-même
    with pytest.raises(InvalidApplyNameError):
        gw.apply_author_name(
            "1",
            ApplyNameRequest(match=".", target=NameTargetByName(name="Frank Herbert")),
        )
    gw.close()


def test_pg_apply_name_auteur_inconnu(pg_library):
    gw = PgLibraryGateway(pg_library, "grimoire-test")

    with pytest.raises(AuthorNotFoundError):
        gw.apply_author_name(
            "9999",
            ApplyNameRequest(match=".", target=NameTargetByName(name="X. Y")),
        )
    gw.close()
