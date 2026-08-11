from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    id: int
    title: str
    authors: tuple[str, ...]
    pubdate: str | None


@dataclass(frozen=True)
class Author:
    id: int
    name: str
