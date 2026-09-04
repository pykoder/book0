import re

from book0_core.errors import InvalidFilterError

_INT_PATTERN = re.compile(r"^[0-9]+$")


def _fail(field: str, reason: str) -> InvalidFilterError:
    return InvalidFilterError(f"filter '{field}': {reason}")


def parse_id_list(raw: str, field: str) -> tuple[str, ...]:
    if "-" in raw:
        raise _fail(field, "un intervalle n'est pas permis sur ce champ")
    parts = [p for p in raw.split(",")]
    if any(p == "" for p in parts):
        raise _fail(field, "valeur vide")
    for p in parts:
        if not _INT_PATTERN.match(p):
            raise _fail(field, f"id invalide : {p!r}")
    return tuple(parts)


def parse_int_list(raw: str, field: str, *, comparable: bool) -> tuple[int, ...]:
    values: list[int] = []
    for part in raw.split(","):
        if part == "":
            raise _fail(field, "valeur vide")
        if "-" in part:
            if not comparable:
                raise _fail(field, "un intervalle n'est pas permis sur ce champ")
            a, _, b = part.partition("-")
            if not (_INT_PATTERN.match(a) and _INT_PATTERN.match(b)):
                raise _fail(field, f"intervalle invalide : {part!r}")
            lo, hi = int(a), int(b)
            if lo > hi:
                raise _fail(field, f"intervalle inversé : {part!r}")
            values.extend(range(lo, hi + 1))
        else:
            if not _INT_PATTERN.match(part):
                raise _fail(field, f"valeur invalide : {part!r}")
            values.append(int(part))
    return tuple(sorted(set(values)))


def parse_text_list(raw: str, field: str) -> tuple[str, ...]:
    parts = raw.split(",")
    if any(p == "" or p.startswith("-") for p in parts):
        raise _fail(field, f"valeur invalide : {raw!r}")
    return tuple(parts)
