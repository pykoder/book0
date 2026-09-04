import psycopg
import pytest

from book0_core.errors import InvalidPatchError, LibraryNotFoundError
from book0_core.gateway import ReadLibraryGateway
from book0_core.models import (
    Author,
    BookPatch,
    BookQuery,
    BookSort,
    EditBooksResult,
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
    _expected_details_with_cover,
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
