"""CLI: python -m backend.extraction.wipe <manuscript_id> [--yes]

Borra la capa M1 (Character, Mention, MergeCandidate) de un manuscrito.
NO toca la capa cruda (Manuscript/Chapter/Scene). ATENCIÓN: borra también
las decisiones humanas de merge (MergeCandidate accepted/rejected) — por
eso exige confirmación explícita.
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

_M1_LABELS = ["Character", "Mention", "MergeCandidate"]


def wipe_extraction(sess, manuscript_id: str) -> dict[str, int]:
    """Borra los nodos M1 del manuscrito; devuelve conteos por label."""
    counts: dict[str, int] = {}
    for label in _M1_LABELS:
        rec = sess.run(
            f"MATCH (n:{label} {{manuscript_id: $mid}}) RETURN count(n) AS c",
            mid=manuscript_id,
        ).single()
        counts[label] = rec["c"] if rec else 0
    sess.run(
        "MATCH (n) WHERE n.manuscript_id = $mid "
        "AND (n:Character OR n:Mention OR n:MergeCandidate) DETACH DELETE n",
        mid=manuscript_id,
    )
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description="Wipe de la capa M1 de un manuscrito.")
    p.add_argument("manuscript_id")
    p.add_argument("--yes", action="store_true", help="No pedir confirmación")
    args = p.parse_args()

    from backend.graph.client import session as db_session

    with db_session() as sess:
        preview: dict[str, int] = {}
        for label in _M1_LABELS:
            rec = sess.run(
                f"MATCH (n:{label} {{manuscript_id: $mid}}) RETURN count(n) AS c",
                mid=args.manuscript_id,
            ).single()
            preview[label] = rec["c"] if rec else 0

        total = sum(preview.values())
        print(f"A borrar en {args.manuscript_id}: {preview} ({total} nodos)")
        if total == 0:
            print("Nada que borrar.")
            return
        if not args.yes:
            answer = input("¿Confirmar borrado? Se pierden decisiones de merge. [y/N] ")
            if answer.strip().lower() != "y":
                print("Abortado.")
                sys.exit(1)
        counts = wipe_extraction(sess, args.manuscript_id)
        print(f"Borrado: {counts}")


if __name__ == "__main__":
    main()
