from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from app.models.domain import ConceptObjective, ContentSnippet

logger = logging.getLogger(__name__)


CONTENT_ROOT = Path(__file__).resolve().parents[2] / "content"


@dataclass(frozen=True)
class ParsedContentDocument:
    path: Path
    metadata: dict[str, str]
    body: str


class ContentLibraryService:
    def retrieve(
        self,
        topic_slug: str,
        focus_objective: ConceptObjective | None = None,
        *,
        limit: int = 3,
        preferred_types: tuple[str, ...] = (),
    ) -> list[ContentSnippet]:
        focus_slug = focus_objective.slug if focus_objective is not None else None
        focus_tokens = set()
        if focus_objective is not None:
            focus_tokens.update(token.lower() for token in focus_objective.title.split())
            focus_tokens.update(token.lower() for token in focus_objective.description.split())

        scored: list[tuple[float, ContentSnippet]] = []
        for document in _load_content_documents():
            snippet = self._to_snippet(document)
            if snippet.topic_slug != topic_slug:
                continue

            score = 5.0
            if focus_slug and focus_slug in snippet.objective_slugs:
                score += 5.0
            if preferred_types and snippet.content_type in preferred_types:
                score += 2.0
            haystack = f"{snippet.title} {snippet.summary} {snippet.text}".lower()
            score += sum(0.4 for token in focus_tokens if token and token in haystack)
            scored.append((score, snippet))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [snippet for _, snippet in scored[:limit]]

    def _to_snippet(self, document: ParsedContentDocument) -> ContentSnippet:
        metadata = document.metadata
        snippet_id = str(uuid5(NAMESPACE_URL, document.path.as_posix()))
        objective_slugs = [
            item.strip()
            for item in metadata.get("objective_slugs", "").split(",")
            if item.strip()
        ]
        try:
            estimated_minutes = int(metadata.get("estimated_minutes", "5"))
        except (ValueError, TypeError):
            estimated_minutes = 5
        return ContentSnippet(
            id=snippet_id,
            title=metadata.get("title", document.path.stem),
            topic_slug=metadata.get("topic_slug", "general"),
            objective_slugs=objective_slugs,
            content_type=metadata.get("content_type", "overview"),
            difficulty=metadata.get("difficulty", "beginner"),
            source_name=metadata.get("source_name", "Adaptive Tutor Library"),
            summary=metadata.get("summary", document.body.splitlines()[0] if document.body else document.path.stem),
            text=document.body.strip(),
            estimated_minutes=estimated_minutes,
        )


@lru_cache(maxsize=1)
def _load_content_documents() -> tuple[ParsedContentDocument, ...]:
    if not CONTENT_ROOT.exists():
        return tuple()

    documents: list[ParsedContentDocument] = []
    for path in sorted(CONTENT_ROOT.glob("*.md")):
        try:
            documents.append(_parse_content_document(path))
        except (ValueError, OSError) as exc:
            logger.warning("Skipping malformed content file %s: %s", path, exc)
    return tuple(documents)


def _parse_content_document(path: Path) -> ParsedContentDocument:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"Content file {path} is missing frontmatter")

    parts = raw.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError(f"Content file {path} has unclosed frontmatter")
    _, metadata_block, body = parts
    metadata: dict[str, str] = {}
    for line in metadata_block.strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')

    return ParsedContentDocument(
        path=path,
        metadata=metadata,
        body=body.strip(),
    )
