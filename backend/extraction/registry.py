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
          entidad (`Mr. Darcy` encuentra `Darcy`).
        - Nombre sin honorífico + una única forma con título → esa entidad
          (`Darcy` encuentra `Mr. Darcy`). Si hay varias formas con título
          distintas (p. ej. `Mr. Bennet` y `Mrs. Bennet`), es ambiguo → sin match.
        """
        hon, base = _split(name)
        buckets = self._index.get(base)
        if not buckets:
            return None
        if hon in buckets:
            return buckets[hon]
        if hon and "" in buckets:
            return buckets[""]
        if not hon and len(buckets) == 1:
            return next(iter(buckets.values()))
        return None

    # ── Escritura ─────────────────────────────────────────────────────────────

    def add(self, canonical_name: str, aliases: list[str], role: str) -> RegistryEntry:
        """Registra una entidad nueva o actualiza aliases/rol de una existente."""
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
        merged_aliases = list({*entry_a.aliases, canonical_b, *entry_b.aliases} - {canonical_a})
        self._entries[canonical_a] = RegistryEntry(
            canonical_name=canonical_a,
            aliases=merged_aliases,
            role=entry_a.role if entry_a.role != "unknown" else entry_b.role,
        )
        del self._entries[canonical_b]
        # canonical_b y sus aliases pasan a apuntar a canonical_a en el índice.
        self._register_key(canonical_b, canonical_a)
        for alias in entry_b.aliases:
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
