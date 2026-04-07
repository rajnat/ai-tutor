from app.models.domain import ConceptObjective
from app.services.content_library import ContentLibraryService


def test_content_library_retrieves_objective_relevant_snippets() -> None:
    library = ContentLibraryService()
    snippets = library.retrieve(
        topic_slug="algebra",
        focus_objective=ConceptObjective(
            id="obj-1",
            slug="algebra:notation",
            title="Notation and vocabulary",
            description="Use algebraic symbols correctly.",
        ),
        limit=2,
    )

    assert len(snippets) >= 1
    assert snippets[0].topic_slug == "algebra"
    assert any("notation" in slug for slug in snippets[0].objective_slugs)
