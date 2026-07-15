"""Pipeline de ingestión: parse -> no-narrativo -> capítulos -> escenas -> modelos.

Produce un `Manuscript` validado (capa cruda) con identidad por hash de contenido
(Principio VI). Determinista: el mismo contenido produce el mismo `manuscript_id` y la
misma segmentación (SC-005, FR-009).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from backend.core.errors import NoNarrativeContentError, UnsupportedFormatError
from backend.core.hashing import content_id, normalize_narrative
from backend.ingest import non_narrative
from backend.ingest.models import (
    Chapter,
    Manuscript,
    NonNarrativeBlock,
    Scene,
    SourceFormat,
)
from backend.ingest.parsers.base import Parser
from backend.ingest.parsers.docx_parser import DocxParser
from backend.ingest.parsers.epub_parser import EpubParser
from backend.ingest.parsers.txt_parser import TxtParser
from backend.ingest.segmentation.chapters import ChapterDraft, segment_chapters
from backend.ingest.segmentation.paratext import partition_paratext
from backend.ingest.segmentation.scenes import segment_scenes

_SEP = "\n\n"
_SNIPPET_DEFAULT = 120

_PARSERS: dict[SourceFormat, type[Parser]] = {
    "epub": EpubParser,
    "txt": TxtParser,
    "docx": DocxParser,
}


def get_parser(source_format: str) -> Parser:
    cls = _PARSERS.get(source_format)  # type: ignore[arg-type]
    if cls is None:
        raise UnsupportedFormatError(
            f"Formato '{source_format}' no soportado. Use epub, txt o docx."
        )
    return cls()


def _snippet(text: str, length: int = _SNIPPET_DEFAULT) -> str:
    flat = " ".join(text.split())
    return flat[:length]


def parse_manuscript(
    path: Path,
    source_format: SourceFormat,
    *,
    ingested_at: datetime | None = None,
) -> Manuscript:
    """Ejecuta el pipeline completo y devuelve la capa cruda validada."""
    parser = get_parser(source_format)
    doc = parser.parse(path)

    narrative_blocks, paratext_blocks = partition_paratext(doc.blocks)
    chapter_drafts, frontmatter = segment_chapters(narrative_blocks)
    nn_drafts = non_narrative.classify(paratext_blocks + frontmatter)

    # Pass 1: escenas normalizadas por capítulo (descarta capítulos sin narrativa).
    built: list[tuple[ChapterDraft, list[tuple[str, str]]]] = []
    for draft in chapter_drafts:
        scenes = []
        for sd in segment_scenes(draft.blocks):
            text = normalize_narrative(sd.text)
            if text:
                scenes.append((text, sd.boundary_reason))
        if scenes:
            built.append((draft, scenes))

    if not built:
        raise NoNarrativeContentError("No se detectó contenido narrativo segmentable.")

    # Pass 2: ofsets sobre el texto narrativo ensamblado e identidad por hash.
    flat_texts = [text for _, scenes in built for text, _ in scenes]
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for text in flat_texts:
        offsets.append((cursor, cursor + len(text)))
        cursor += len(text) + len(_SEP)
    narrative = _SEP.join(flat_texts)
    manuscript_id = content_id(narrative)

    # Pass 3: construir modelos con ids derivados.
    chapters: list[Chapter] = []
    flat_idx = 0
    global_order = 0
    for ch_order, (draft, scenes) in enumerate(built):
        chapter_id = f"{manuscript_id}:c{ch_order}"
        scene_models: list[Scene] = []
        ch_start = offsets[flat_idx][0]
        ch_word_count = 0
        for in_chapter, (text, reason) in enumerate(scenes):
            start, end = offsets[flat_idx]
            scene_models.append(
                Scene(
                    scene_id=f"{chapter_id}:s{in_chapter}",
                    chapter_id=chapter_id,
                    manuscript_id=manuscript_id,
                    order_in_chapter=in_chapter,
                    order_narrative_global=global_order,
                    text=text,
                    char_count=len(text),
                    start_offset=start,
                    end_offset=end,
                    boundary_reason=reason,
                    snippet=_snippet(text),
                )
            )
            ch_word_count += len(text.split())
            ch_end = end
            flat_idx += 1
            global_order += 1
        chapters.append(
            Chapter(
                chapter_id=chapter_id,
                manuscript_id=manuscript_id,
                order_narrative=ch_order,
                title=draft.title,
                kind=draft.kind,
                word_count=ch_word_count,
                start_offset=ch_start,
                end_offset=ch_end,
                scenes=scene_models,
            )
        )

    nn_blocks = [
        NonNarrativeBlock(
            block_id=f"{manuscript_id}:nn{i}",
            manuscript_id=manuscript_id,
            kind=d.kind,
            text=d.text,
            detected_by=d.detected_by,
            position="before",
        )
        for i, d in enumerate(nn_drafts)
    ]

    return Manuscript(
        manuscript_id=manuscript_id,
        title=doc.title,
        source_format=source_format,
        word_count=len(narrative.split()),
        chapter_count=len(chapters),
        ingested_at=ingested_at or datetime.now(UTC),
        chapters=chapters,
        non_narrative_blocks=nn_blocks,
    )
