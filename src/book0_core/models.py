from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    id: str
    title: str
    authors: tuple[str, ...]
    pubdate: str | None


@dataclass(frozen=True)
class Author:
    id: str
    name: str


@dataclass(frozen=True)
class Publisher:
    id: str
    name: str
