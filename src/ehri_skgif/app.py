"""SKG-IF demo service exposing EHRI Document Blog posts as research products.

Every response is either a bare SKG-IF entity, a list of them, or a JSON-LD
document (``@context`` + ``@graph``) built from the same static file, so the
output can be handed straight to an SKG-IF consumer such as the GRAPHIA
Federated Gateway.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, abort, jsonify, request
from werkzeug.exceptions import HTTPException

from .store import ENTITY_TYPES, Store

JSONLD_MEDIA_TYPE = "application/ld+json"

BLOG_VENUE = "https://blog.ehri-project.eu"

SERVICE_TITLE = "EHRI SKG-IF demo service"

app = Flask(__name__)
app.json.sort_keys = False
app.json.ensure_ascii = False

_store = Store.from_file()


@app.errorhandler(HTTPException)
def handle_http_exception(error: HTTPException):
    """Errors stay JSON, in the ``{"detail": …}`` shape clients already parse."""
    return jsonify(detail=error.description), error.code


def jsonld(document: dict[str, Any]):
    return app.response_class(app.json.dumps(document), mimetype=JSONLD_MEDIA_TYPE)


@app.get("/")
def root() -> dict[str, Any]:
    """Service description."""
    return {
        "name": SERVICE_TITLE,
        "interoperability_framework": "SKG-IF v1.0.0",
        "context": "https://w3id.org/skg-if/context/skg-if.json",
        "counts": {name: len(_store.list(name)) for name in ENTITY_TYPES},
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


@app.get("/dump")
def dump():
    """Full SKG-IF JSON-LD document."""
    return jsonld(_store.as_document(_store.entities))


@app.get("/entities")
def entities() -> dict[str, Any]:
    """List entities, optionally filtered by type."""
    entity_type = request.args.get("type")
    if entity_type is None:
        selected = _store.entities
    elif entity_type in ENTITY_TYPES:
        selected = _store.list(entity_type)
    else:
        abort(
            400,
            description=(
                f"Unknown entity_type {entity_type!r}; expected one of {list(ENTITY_TYPES)}"
            ),
        )
    return _page(selected, *_paging())


@app.get("/entity")
def entity() -> dict[str, Any]:
    """Fetch one entity by local_identifier."""
    identifier = _required_arg("id")
    found = _store.get(identifier)
    if found is None:
        abort(404, description=f"No entity with local_identifier {identifier!r}")
    return found


@app.get("/products")
def products() -> dict[str, Any]:
    """List research products."""
    product_type = request.args.get("product_type")
    return _page(_store.products(product_type), *_paging())


@app.get("/blog-posts")
def blog_posts() -> dict[str, Any]:
    """Research products published in the EHRI Document Blog."""
    selected = [p for p in _store.products("literature") if _venue_of(p) == BLOG_VENUE]
    return _page(selected, limit=len(selected) or 1, offset=0)


@app.get("/graph")
def graph():
    """An entity and everything it directly references."""
    identifier = _required_arg("id")
    neighbourhood = _store.neighbourhood(identifier)
    if not neighbourhood:
        abort(404, description=f"No entity with local_identifier {identifier!r}")
    return jsonld(_store.as_document(neighbourhood))


@app.get("/search")
def search() -> dict[str, Any]:
    """Substring search over titles, abstracts, labels and names."""
    query = _required_arg("q", min_length=2)
    return _page(_store.search(query), *_paging())


def _paging() -> tuple[int, int]:
    """The ``limit`` and ``offset`` shared by every paged endpoint."""
    return (
        _int_arg("limit", default=50, minimum=1, maximum=500),
        _int_arg("offset", default=0, minimum=0),
    )


def _int_arg(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        abort(400, description=f"{name} must be an integer, got {raw!r}")
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"at least {minimum}" if maximum is None else f"between {minimum} and {maximum}"
        abort(400, description=f"{name} must be {bound}, got {value}")
    return value


def _required_arg(name: str, min_length: int = 1) -> str:
    value = request.args.get(name)
    if value is None:
        abort(400, description=f"Missing required query parameter {name!r}")
    if len(value) < min_length:
        abort(400, description=f"{name} must be at least {min_length} characters long")
    return value


def _page(selected: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    window = selected[offset : offset + limit]
    return {"total": len(selected), "offset": offset, "limit": limit, "results": window}


def _venue_of(product: dict[str, Any]) -> str | None:
    for manifestation in product.get("manifestations", []):
        if venue := (manifestation.get("biblio") or {}).get("in"):
            return venue
    return None
