"""Regresión del bug crítico del harness: la fixture `neo4j_session` destruía la
capa cruda de TODOS los manuscritos (wipe global sin scope), borrando obras reales
como pride-and-prejudice en cada corrida de integración.

Ver docs/known-issues.md → "Follow-ups tras bugfixes + demo HP1", punto 1.

El contrato ahora: la limpieza del harness solo toca manuscritos de test
(`test-*` + fixtures crafted). Ningún otro manuscript_id se ve afectado.
"""

from __future__ import annotations

import pytest

from tests.conftest import _wipe_manuscripts

pytestmark = pytest.mark.integration

_FOREIGN_ID = "real-book-do-not-delete"


def _manuscript_exists(sess, mid: str) -> bool:
    rec = sess.run(
        "MATCH (m:Manuscript {manuscript_id: $mid}) RETURN count(m) AS c", mid=mid
    ).single()
    return bool(rec and rec["c"])


def test_wipe_manuscripts_only_touches_given_ids(neo4j_session) -> None:
    """`_wipe_manuscripts` borra exactamente los ids dados y respeta el resto."""
    sess = neo4j_session
    sess.run("MERGE (:Manuscript {manuscript_id: $mid})", mid=_FOREIGN_ID)
    sess.run("MERGE (:Manuscript {manuscript_id: 'test-scratch'})")
    try:
        _wipe_manuscripts(sess, ["test-scratch"])

        assert _manuscript_exists(sess, _FOREIGN_ID), (
            "El harness borró un manuscrito ajeno — regresión del wipe global."
        )
        assert not _manuscript_exists(sess, "test-scratch")
    finally:
        sess.run(
            "MATCH (m:Manuscript {manuscript_id: $mid}) DETACH DELETE m", mid=_FOREIGN_ID
        )


def test_wipe_manuscripts_rejects_unscoped_delete(neo4j_session) -> None:
    """Guard: no existe ruta para un borrado sin scope (lista vacía = no-op)."""
    sess = neo4j_session
    sess.run("MERGE (:Manuscript {manuscript_id: $mid})", mid=_FOREIGN_ID)
    try:
        _wipe_manuscripts(sess, [])  # lista vacía: no debe borrar nada
        assert _manuscript_exists(sess, _FOREIGN_ID)
    finally:
        sess.run(
            "MATCH (m:Manuscript {manuscript_id: $mid}) DETACH DELETE m", mid=_FOREIGN_ID
        )
