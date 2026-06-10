"""Registro acumulado de entidades (research R2).

Crece escena a escena en orden narrativo; se serializa como lista de
RegistryEntry para incluirlo en el prompt de contexto.
"""

from __future__ import annotations

import re
import unicodedata

from backend.extraction.schemas import RegistryEntry

_HONORIFICS = re.compile(
    r"^(mr\.?|mrs\.?|ms\.?|miss|dr\.?|prof\.?|sir|lord|lady|don|doña|"
    r"señor|señora|señorita|monsieur|madame|mademoiselle)\s+",
    re.IGNORECASE,
)


def _normalize(name: str) -> str:
    """Casefold + eliminar diacríticos + honoríficos para comparación."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    stripped = _HONORIFICS.sub("", ascii_str)
    return stripped.casefold().strip()


class EntityRegistry:
    """Registro mutable de personajes conocidos durante la extracción."""

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}  # canonical_name → entry
        self._alias_index: dict[str, str] = {}  # norm(alias/name) → canonical_name

    # ── Escritura ─────────────────────────────────────────────────────────────

    def add(self, canonical_name: str, aliases: list[str], role: str) -> RegistryEntry:
        """Registra una entidad nueva o actualiza aliases/rol de una existente."""
        key = _normalize(canonical_name)
        if key in self._alias_index:
            canonical = self._alias_index[key]
            entry = self._entries[canonical]
            new_aliases = list({*entry.aliases, *aliases} - {canonical_name})
            entry = RegistryEntry(
                canonical_name=entry.canonical_name,
                aliases=new_aliases,
                role=role if role != "unknown" else entry.role,
            )
            self._entries[canonical] = entry
        else:
            entry = RegistryEntry(canonical_name=canonical_name, aliases=aliases, role=role)
            self._entries[canonical_name] = entry
            self._alias_index[key] = canonical_name
            for alias in aliases:
                self._alias_index[_normalize(alias)] = canonical_name
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
        # canonical_b se convierte en alias de canonical_a → re-apuntar en el índice
        self._alias_index[_normalize(canonical_b)] = canonical_a
        for alias in entry_b.aliases:
            self._alias_index[_normalize(alias)] = canonical_a

    # ── Lectura ───────────────────────────────────────────────────────────────

    def find(self, name: str) -> RegistryEntry | None:
        """Busca una entidad por nombre canónico o alias (normalizado)."""
        canonical = self._alias_index.get(_normalize(name))
        if canonical:
            return self._entries.get(canonical)
        return None

    def get_canonical(self, name: str) -> str | None:
        """Devuelve el canonical_name correspondiente a un nombre/alias."""
        return self._alias_index.get(_normalize(name))

    def all_entries(self) -> list[RegistryEntry]:
        return list(self._entries.values())

    def to_json_list(self) -> list[dict]:
        return [e.model_dump() for e in self._entries.values()]

    def __len__(self) -> int:
        return len(self._entries)
