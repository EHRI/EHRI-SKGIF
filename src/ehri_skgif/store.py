"""In-memory store over a static SKG-IF JSON-LD document.

The demo service does not talk to the EHRI Knowledge Graph. It loads a single
JSON-LD file whose ``@graph`` holds every entity, indexes it by
``local_identifier`` and by ``entity_type``, and serves slices of that graph.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

Entity = dict[str, Any]

DEFAULT_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "ehri_demo.jsonld"

ENTITY_TYPES = (
    "product",
    "person",
    "organisation",
    "topic",
    "venue",
    "datasource",
    "grant",
)


@dataclass
class Store:
    context: Any
    entities: list[Entity]
    by_id: dict[str, Entity] = field(default_factory=dict)
    by_type: dict[str, list[Entity]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def from_file(cls, path: Path | str = DEFAULT_DATA_FILE) -> "Store":
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        store = cls(context=document.get("@context"), entities=document.get("@graph", []))
        store.reindex()
        return store

    def reindex(self) -> None:
        self.by_id = {}
        self.by_type = defaultdict(list)
        for entity in self.entities:
            identifier = entity.get("local_identifier")
            if identifier:
                self.by_id[identifier] = entity
            self.by_type[entity.get("entity_type", "unknown")].append(entity)

    # -- lookups ---------------------------------------------------------

    def get(self, local_identifier: str) -> Entity | None:
        return self.by_id.get(local_identifier)

    def list(self, entity_type: str) -> list[Entity]:
        return list(self.by_type.get(entity_type, []))

    def products(self, product_type: str | None = None) -> list[Entity]:
        products = self.list("product")
        if product_type is not None:
            products = [p for p in products if p.get("product_type") == product_type]
        return products

    def search(self, query: str) -> list[Entity]:
        """Naive substring match over titles, labels, names and abstracts."""
        needle = query.casefold()
        return [e for e in self.entities if needle in _searchable_text(e)]

    # -- graph traversal -------------------------------------------------

    def neighbourhood(self, local_identifier: str) -> list[Entity]:
        """The entity plus everything it directly points at, resolved.

        For a blog post this returns its authors, publisher, topics, venue and
        related organisations as a self-contained SKG-IF graph.
        """
        root = self.get(local_identifier)
        if root is None:
            return []
        collected: dict[str, Entity] = {local_identifier: root}
        for referenced in _referenced_identifiers(root):
            entity = self.get(referenced)
            if entity is not None:
                collected.setdefault(referenced, entity)
        return list(collected.values())

    def as_document(self, entities: Iterable[Entity]) -> dict[str, Any]:
        """Wrap entities back into a JSON-LD document with the SKG-IF context."""
        return {"@context": self.context, "@graph": list(entities)}


def _searchable_text(entity: Entity) -> str:
    parts: list[str] = []
    for key in ("titles", "abstracts", "labels"):
        value = entity.get(key)
        if isinstance(value, dict):
            for translation in value.values():
                parts.extend(translation if isinstance(translation, list) else [translation])
    for key in ("name", "short_name", "acronym", "local_identifier"):
        value = entity.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).casefold()


def _referenced_identifiers(entity: Entity) -> list[str]:
    """Every local_identifier the given entity refers to, in document order."""
    refs: list[str] = []

    for contribution in entity.get("contributions", []):
        if by := contribution.get("by"):
            refs.append(by)
        refs.extend(contribution.get("declared_affiliations", []))

    for topic in entity.get("topics", []):
        if term := topic.get("term"):
            refs.append(term)
        for provenance in topic.get("provenance", []):
            if agent := provenance.get("associated_with"):
                refs.append(agent)

    for manifestation in entity.get("manifestations", []):
        biblio = manifestation.get("biblio") or {}
        refs.extend(filter(None, (biblio.get("in"), biblio.get("hosting_data_source"))))

    refs.extend(entity.get("relevant_organisations", []))
    refs.extend(entity.get("funding", []))
    refs.extend(entity.get("beneficiaries", []))

    for affiliation in entity.get("affiliations", []):
        if org := affiliation.get("affiliation"):
            refs.append(org)

    for identifiers in (entity.get("related_products") or {}).values():
        refs.extend(identifiers)

    return refs
