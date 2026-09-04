class LibraryNotFoundError(Exception):
    pass


class NotACalibreLibraryError(Exception):
    pass


class TagRequiredError(Exception):
    pass


class BookNotFoundError(Exception):
    pass


class NoEpubError(Exception):
    pass


class InvalidExtractError(Exception):
    pass


class InvalidFilterError(Exception):
    pass


class InvalidPatchError(Exception):
    pass


class UnknownJobError(Exception):
    pass


class UnknownJobActionError(Exception):
    pass


class AuthorNotFoundError(Exception):
    pass


class AuthorNameMismatchError(Exception):
    pass


class InvalidAliasError(Exception):
    pass


class InvalidApplyNameError(Exception):
    pass
