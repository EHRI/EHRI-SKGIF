"""SKG-IF demo service exposing EHRI Document Blog posts as research products.

Every response is either a bare SKG-IF entity, a list of them, or a JSON-LD
document (``@context`` + ``@graph``) built from the same static file, so the
output can be handed straight to an SKG-IF consumer such as the GRAPHIA
Federated Gateway.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from .store import ENTITY_TYPES, Store

JSONLD_MEDIA_TYPE = "application/ld+json"

BLOG_VENUE = "https://blog.ehri-project.eu"

app = FastAPI(
    title="EHRI SKG-IF demo service",
    version="0.1.0",
    description=(
        "Static SKG-IF v1.0.0 records for the four most recent EHRI Document Blog "
        "posts. A demo profile, not an authoritative EHRI service."
    ),
)

_store = Store.from_file()


def get_store() -> Store:
    return _store


StoreDep = Annotated[Store, Depends(get_store)]


def jsonld(document: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=document, media_type=JSONLD_MEDIA_TYPE)


@app.get("/", summary="Service description")
def root(store: StoreDep) -> dict[str, Any]:
    return {
        "name": app.title,
        "interoperability_framework": "SKG-IF v1.0.0",
        "context": "https://w3id.org/skg-if/context/skg-if.json",
        "counts": {name: len(store.list(name)) for name in ENTITY_TYPES},
        "endpoints": [
            "/dump",
            "/entities?type=product",
            "/entity?id=<local_identifier>",
            "/products?product_type=literature",
            "/blog-posts",
            "/graph?id=<local_identifier>",
            "/search?q=<text>",
        ],
        "data_provenance": (
            "The four most recent EHRI Document Blog posts. Posts, DOIs, authors and "
            "EHRI Portal institutions were verified against live sources. A post refers "
            "to archival material only where it embeds an ehri-item Web Component."
        ),
    }


@app.get("/dump", summary="Full SKG-IF JSON-LD document")
def dump(store: StoreDep) -> JSONResponse:
    return jsonld(store.as_document(store.entities))


@app.get("/entities", summary="List entities, optionally filtered by type")
def entities(
    store: StoreDep,
    type: str | None = Query(default=None, description="SKG-IF entity_type"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    if type is None:
        selected = store.entities
    elif type in ENTITY_TYPES:
        selected = store.list(type)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown entity_type {type!r}; expected one of {list(ENTITY_TYPES)}",
        )
    return _page(selected, limit, offset)


@app.get("/entity", summary="Fetch one entity by local_identifier")
def entity(store: StoreDep, id: str = Query(description="local_identifier")) -> dict[str, Any]:
    found = store.get(id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"No entity with local_identifier {id!r}")
    return found


@app.get("/products", summary="List research products")
def products(
    store: StoreDep,
    product_type: str | None = Query(
        default=None,
        description="literature | research data | research software | other",
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return _page(store.products(product_type), limit, offset)


@app.get("/blog-posts", summary="Research products published in the EHRI Document Blog")
def blog_posts(store: StoreDep) -> dict[str, Any]:
    selected = [p for p in store.products("literature") if _venue_of(p) == BLOG_VENUE]
    return _page(selected, limit=len(selected) or 1, offset=0)


@app.get("/graph", summary="An entity and everything it directly references")
def graph(store: StoreDep, id: str = Query(description="local_identifier")) -> JSONResponse:
    neighbourhood = store.neighbourhood(id)
    if not neighbourhood:
        raise HTTPException(status_code=404, detail=f"No entity with local_identifier {id!r}")
    return jsonld(store.as_document(neighbourhood))


@app.get("/search", summary="Substring search over titles, abstracts, labels and names")
def search(
    store: StoreDep,
    q: str = Query(min_length=2),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return _page(store.search(q), limit, offset)


def _page(selected: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    window = selected[offset : offset + limit]
    return {"total": len(selected), "offset": offset, "limit": limit, "results": window}


def _venue_of(product: dict[str, Any]) -> str | None:
    for manifestation in product.get("manifestations", []):
        if venue := (manifestation.get("biblio") or {}).get("in"):
            return venue
    return None
