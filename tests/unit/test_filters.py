import pytest

from book0_api.filters import parse_id_list, parse_int_list, parse_text_list
from book0_core.errors import InvalidFilterError


def test_id_list_simple():
    assert parse_id_list("3", "author_id") == ("3",)
    assert parse_id_list("3,17", "author_id") == ("3", "17")


def test_id_list_rejette_intervalle_et_non_numerique():
    with pytest.raises(InvalidFilterError):
        parse_id_list("3-7", "author_id")
    with pytest.raises(InvalidFilterError):
        parse_id_list("3,abc", "author_id")


def test_int_list_etend_les_intervalles():
    assert parse_int_list("4", "ratings", comparable=True) == (4,)
    assert parse_int_list("1,3-5", "ratings", comparable=True) == (1, 3, 4, 5)


def test_int_list_intervalle_interdit_si_non_comparable():
    with pytest.raises(InvalidFilterError):
        parse_int_list("1-3", "tags", comparable=False)


def test_int_list_intervalle_inverse_rejete():
    with pytest.raises(InvalidFilterError):
        parse_int_list("5-3", "ratings", comparable=True)


def test_text_list_valeurs_multiples():
    assert parse_text_list("classique,science-fiction", "tags") == (
        "classique",
        "science-fiction",
    )


def test_text_list_rejete_element_vide_et_tiret_initial():
    # NB : le split sur ',' est la syntaxe — une valeur contenant une virgule
    # ne peut pas s'exprimer (limite assumée de la convention §5).
    with pytest.raises(InvalidFilterError):
        parse_text_list("classique,", "tags")  # élément vide
    with pytest.raises(InvalidFilterError):
        parse_text_list("-classique", "tags")  # tiret initial ambigu
