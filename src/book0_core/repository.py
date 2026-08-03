from typing import Protocol

from book0_core.models import Book


class BookRepository(Protocol):
    def list_books(self) -> list[Book]: ...
