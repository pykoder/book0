import pytest

from book0_cli_remote.http_gateway import _ERROR_TYPES
from book0_core import errors
from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)

EXPECTED = {
    "BookNotFoundError": 404, "NoEpubError": 404, "InvalidExtractError": 400,
    "InvalidFilterError": 422, "InvalidPatchError": 422, "UnknownJobError": 404,
    "UnknownJobActionError": 422, "AuthorNotFoundError": 404,
    "AuthorNameMismatchError": 422, "InvalidAliasError": 422,
    "InvalidApplyNameError": 422,
}

@pytest.mark.parametrize("name", EXPECTED)
def test_erreur_domaine_existe_et_reconstructible(name):
    cls = getattr(errors, name)
    assert issubclass(cls, Exception)
    assert _ERROR_TYPES[name] is cls


def test_library_not_found_error_is_an_exception():
    assert issubclass(LibraryNotFoundError, Exception)


def test_not_a_calibre_library_error_is_an_exception():
    assert issubclass(NotACalibreLibraryError, Exception)


def test_tag_required_error_is_an_exception():
    assert issubclass(TagRequiredError, Exception)
