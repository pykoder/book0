from pydantic import BaseModel

from book0_core.models import Author, Book


class AuthorOut(BaseModel):
    id: int
    name: str

    @classmethod
    def from_author(cls, author: Author) -> "AuthorOut":
        return cls(id=author.id, name=author.name)


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
