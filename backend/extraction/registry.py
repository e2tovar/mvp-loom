"""Registro acumulado de entidades (research R2).

Crece escena a escena en orden narrativo; se serializa como lista de
RegistryEntry para incluirlo en el prompt de contexto.
"""

from __future__ import annotations

import re
import unicodedata

from backend.extraction.schemas import RegistryEntry

_HONORIFIC = re.compile(
    r"^(mr|mrs|ms|miss|dr|prof|sir|lord|lady|don|dona|"
    r"senor|senora|senorita|monsieur|madame|mademoiselle)\.?\s+",
    re.IGNORECASE,
)

_PRONOUNS = frozenset({
    "she", "he", "her", "him", "his", "hers", "they", "them", "their", "theirs",
    "it", "its", "i", "you", "we", "me", "us", "myself", "herself", "himself",
    "ella", "el", "le", "la", "lo", "les", "las", "los", "su", "sus", "yo",
    "tu", "usted", "ustedes", "nosotros", "nosotras", "ellos", "ellas",
})

_GENERIC_HEAD = frozenset({
    "mother", "father", "mamma", "mama", "papa", "mom", "dad", "parents",
    "sister", "brother", "aunt", "uncle", "cousin", "niece", "nephew",
    "wife", "husband", "son", "daughter", "child", "children", "family",
    "friend", "friends", "neighbour", "neighbor",
    "grandfather", "grandmother", "grandson", "granddaughter", "grandparent",
    "madre", "padre", "hermana", "hermano", "tia", "tio",
    "prima", "primo", "esposa", "esposo", "marido", "mujer", "hija", "hijo",
    "amiga", "amigo", "vecina", "vecino", "familia", "nina", "nino",
    "abuelo", "abuela", "nieto", "nieta",
})

_ALIAS_PREFIX = re.compile(
    r"^(my|your|her|his|their|our|the|that|this|"
    r"mi|tu|su|nuestra|nuestro|la|el|esa|ese|esta|este)\s+",
    re.IGNORECASE,
)

_LEADING_ARTICLE = re.compile(
    r"^(the|a|an|el|la|los|las|un|una|unos|unas|one of the|one of|some of the)\s+",
    re.IGNORECASE,
)

# Descriptor relacional: "<parentesco> de/of <Nombre>" o "<Nombre>'s <parentesco>".
# El nombre propio embebido pertenece a OTRO personaje, no al descrito.
_RELATIONAL_GENITIVE = re.compile(r"^(?P<head>\S+)\s+(?:de|of)\s+\S+", re.IGNORECASE)
_RELATIONAL_POSSESSIVE = re.compile(r"^.+['']s\s+(?P<head>\S+)\s*$", re.IGNORECASE)


def _is_relational_descriptor(stripped: str) -> bool:
    """True si es un descriptor por parentesco con nombre propio ajeno embebido."""
    for pattern in (_RELATIONAL_GENITIVE, _RELATIONAL_POSSESSIVE):
        match = pattern.match(stripped)
        if match and _ascii_fold(match.group("head")) in _GENERIC_HEAD:
            return True
    return False


def is_unnamed(name: str) -> bool:
    """Descriptor genérico sin nombre propio («the waiter», «el anciano»).

    Tras quitar el artículo inicial, si ningún token empieza en mayúscula no hay
    nombre propio. Se aplica a canonical names (filtro de entidades, resolution)
    y a aliases (is_valid_alias): un descriptor indexado como clave de fusión
    fusiona personajes distintos (caso Ollivander/Dumbledore vía «el anciano»).
    Trade-off: epítetos legítimos en minúscula («el niño que vivió») quedan fuera
    de aliases — sus menciones siguen enlazadas vía links_to (kind='description').
    """
    stripped = _LEADING_ARTICLE.sub("", name.strip())
    if not stripped:
        return True
    if _is_relational_descriptor(stripped):
        return True
    return not any(tok[:1].isupper() for tok in stripped.split())


def _ascii_fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return nfkd.encode("ascii", "ignore").decode("ascii").casefold().strip()


def is_valid_alias(alias: str) -> bool:
    """Un alias válido es un nombre propio, no un pronombre ni un parentesco.

    Rechaza: pronombres ("she", "ella"), y descriptores relacionales con o sin
    posesivo/artículo ("her friend", "your mother", "mamma", "la madre").
    Un error del LLM aquí envenena el nivel 1 de la cascada para siempre
    (auto-merge determinista por alias) — de ahí el filtro duro.
    """
    norm = _ascii_fold(alias)
    if not norm:
        return False
    if norm in _PRONOUNS:
        return False
    head = _ALIAS_PREFIX.sub("", norm).strip()
    if head in _GENERIC_HEAD:
        return False
    if is_unnamed(alias):
        return False
    return True


def _split(name: str) -> tuple[str, str]:
    """Separa un nombre en (honorífico_norm, base_norm).

    El honorífico es lo único que distingue a personajes que comparten apellido
    (`Mr. Bennet` vs `Mrs. Bennet`, `Lady Lucas` vs `Miss Lucas`). Por eso NO se
    descarta: se conserva aparte para que la comparación pueda decidir que dos
    honoríficos distintos sobre la misma base son entidades diferentes.

    Devuelve `("", base)` cuando no hay honorífico. Si el nombre es solo un
    honorífico ("Mr."), se trata como base sin honorífico.
    """
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii").casefold().strip()
    match = _HONORIFIC.match(ascii_str)
    if match:
        base = ascii_str[match.end() :].strip()
        if base:
            return match.group(1), base
    return "", ascii_str


class EntityRegistry:
    """Registro mutable de personajes conocidos durante la extracción."""

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}  # canonical_name → entry
        # base_norm → {honorífico_norm → canonical_name}. El honorífico "" es la
        # forma sin título; distintos honoríficos sobre la misma base coexisten.
        self._index: dict[str, dict[str, str]] = {}

    # ── Índice honorífico-aware ─────────────────────────────────────────────────

    def _register_key(self, name: str, canonical: str) -> None:
        hon, base = _split(name)
        self._index.setdefault(base, {})[hon] = canonical

    def _lookup(self, name: str) -> str | None:
        """Resuelve un nombre/alias a su canonical respetando el honorífico.

        - Honorífico exacto (o base sin honorífico exacta) → esa entidad.
        - Nombre con honorífico + existe la forma sin título de esa base → misma
          entidad (`Mr. Darcy` encuentra `Darcy`) SOLO si no hay otro honorífico
          explícito distinto en el bucket. Si lo hay (p. ej. el bucket ya tiene
          `"mr"`), la forma desnuda pertenece a esa persona titulada y matchear un
          honorífico distinto (`Miss Darcy`) sería fusionar hermanos → se difiere
          al nivel 2.
        - Nombre sin honorífico + una única forma con título → esa entidad
          (`Darcy` encuentra `Mr. Darcy`). Si hay varias formas con título
          distintas, es ambiguo → sin match.
        """
        hon, base = _split(name)
        buckets = self._index.get(base)
        if not buckets:
            return None
        if hon in buckets:
            return buckets[hon]
        if hon and "" in buckets:
            if not any(h not in ("", hon) for h in buckets):
                return buckets[""]
            return None
        if not hon and len(buckets) == 1:
            return next(iter(buckets.values()))
        return None

    # ── Escritura ─────────────────────────────────────────────────────────────

    def add(self, canonical_name: str, aliases: list[str], role: str) -> RegistryEntry:
        """Registra una entidad nueva o actualiza aliases/rol de una existente."""
        aliases = [a for a in aliases if is_valid_alias(a)]
        canonical = self._lookup(canonical_name)
        if canonical is not None:
            entry = self._entries[canonical]
            new_aliases = list({*entry.aliases, *aliases} - {canonical})
            entry = RegistryEntry(
                canonical_name=entry.canonical_name,
                aliases=new_aliases,
                role=role if role != "unknown" else entry.role,
            )
            self._entries[canonical] = entry
            for alias in aliases:
                self._register_key(alias, canonical)
        else:
            entry = RegistryEntry(canonical_name=canonical_name, aliases=aliases, role=role)
            self._entries[canonical_name] = entry
            self._register_key(canonical_name, canonical_name)
            for alias in aliases:
                self._register_key(alias, canonical_name)
        return entry

    def merge_into(self, canonical_a: str, canonical_b: str) -> None:
        """Fusiona B en A: mueve aliases de B a A y elimina B del registro."""
        entry_a = self._entries.get(canonical_a)
        entry_b = self._entries.get(canonical_b)
        if entry_a is None or entry_b is None:
            return
        aliases_b = [a for a in entry_b.aliases if is_valid_alias(a)]
        merged_aliases = list({*entry_a.aliases, canonical_b, *aliases_b} - {canonical_a})
        self._entries[canonical_a] = RegistryEntry(
            canonical_name=canonical_a,
            aliases=merged_aliases,
            role=entry_a.role if entry_a.role != "unknown" else entry_b.role,
        )
        del self._entries[canonical_b]
        # canonical_b y sus aliases pasan a apuntar a canonical_a en el índice.
        self._register_key(canonical_b, canonical_a)
        for alias in aliases_b:
            self._register_key(alias, canonical_a)

    # ── Lectura ───────────────────────────────────────────────────────────────

    def find(self, name: str) -> RegistryEntry | None:
        """Busca una entidad por nombre canónico o alias (honorífico-aware)."""
        canonical = self._lookup(name)
        if canonical:
            return self._entries.get(canonical)
        return None

    def get_canonical(self, name: str) -> str | None:
        """Devuelve el canonical_name correspondiente a un nombre/alias."""
        return self._lookup(name)

    def all_entries(self) -> list[RegistryEntry]:
        return list(self._entries.values())

    def to_json_list(self) -> list[dict]:
        return [e.model_dump() for e in self._entries.values()]

    def __len__(self) -> int:
        return len(self._entries)
