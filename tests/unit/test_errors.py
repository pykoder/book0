from book0_core.errors import (
    LibraryNotFoundError,
    NotACalibreLibraryError,
    TagRequiredError,
)


def test_library_not_found_error_is_an_exception():
    assert issubclass(LibraryNotFoundError, Exception)


def test_not_a_calibre_library_error_is_an_exception():
    assert issubclass(NotACalibreLibraryError, Exception)


def test_tag_required_error_is_an_exception():
    assert issubclass(TagRequiredError, Exception)
