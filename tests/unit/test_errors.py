from book0_core.errors import LibraryNotFoundError, NotACalibreLibraryError


def test_library_not_found_error_is_an_exception():
    assert issubclass(LibraryNotFoundError, Exception)


def test_not_a_calibre_library_error_is_an_exception():
    assert issubclass(NotACalibreLibraryError, Exception)
