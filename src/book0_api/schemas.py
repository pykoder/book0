from pydantic import BaseModel

from book0_core.models import Book


class BookOut(BaseModel):
    id: int
    title: str
    authors: list[str]
    pubdate: str | None

    @classmethod
    def from_book(cls, book: Book) -> "BookOut":
        return cls(
            id=book.id,
            title=book.title,
            authors=list(book.authors),
            pubdate=book.pubdate,
        )
