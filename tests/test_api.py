import pytest
from fastapi.testclient import TestClient

from ehri_skgif.app import BLOG_VENUE, app
from ehri_skgif.store import ENTITY_TYPES, Store

KASSIBER_POST = "https://blog.ehri-project.eu/2026/07/30/secret-notes-from-austrian-resistance/"
KALININDORF_POST = "https://blog.ehri-project.eu/2026/06/29/the-extermination-of-jews-in-the-kalinindorf/"
UKRAINE_POST = "https://blog.ehri-project.eu/2026/04/30/scholars-path-through-fragmentation/"
YAD_VASHEM = "https://portal.ehri-project.eu/institutions/il-002798"
GARF = "https://portal.ehri-project.eu/institutions/ru-003205"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def store():
    return Store.from_file()


def test_every_entity_has_a_unique_identifier_and_known_type(store):
    identifiers = [e["local_identifier"] for e in store.entities]
    assert len(identifiers) == len(set(identifiers))
    assert {e["entity_type"] for e in store.entities} <= set(ENTITY_TYPES)


def test_every_referenced_identifier_resolves(store):
    """No dangling references: the demo document is a closed graph."""
    for entity in store.entities:
        for referenced in store.neighbourhood(entity["local_identifier"]):
            assert referenced["local_identifier"] in store.by_id


def test_no_product_asserts_a_relation_without_an_ehri_item_embed(store):
    """None of the four posts embeds a unit-level ehri-item, so none cites."""
    for product in store.products():
        assert "related_products" not in product


def test_institution_embeds_land_in_relevant_organisations(client):
    kalinindorf = client.get("/entity", params={"id": KALININDORF_POST}).json()
    assert kalinindorf["relevant_organisations"] == [GARF]

    ukraine = client.get("/entity", params={"id": UKRAINE_POST}).json()
    assert ukraine["relevant_organisations"] == [YAD_VASHEM]


def test_posts_without_embeds_carry_no_archival_reference(client):
    post = client.get("/entity", params={"id": KASSIBER_POST}).json()
    assert "relevant_organisations" not in post
    assert "related_products" not in post


def test_topics_reference_only_blog_tags(store):
    """Topics are the blog's own tags; no ehri_terms alignments are asserted."""
    for topic in store.list("topic"):
        assert topic["local_identifier"].startswith("https://blog.ehri-project.eu/tag/")
        for identifier in topic["identifiers"]:
            assert "portal.ehri-project.eu" not in identifier["value"]


def test_dump_is_a_jsonld_document(client):
    response = client.get("/dump")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/ld+json")
    document = response.json()
    assert "https://w3id.org/skg-if/context/skg-if.json" in document["@context"]
    assert document["@graph"]


def test_blog_posts_are_literature_in_the_blog_venue(client):
    results = client.get("/blog-posts").json()["results"]
    assert len(results) == 4
    for post in results:
        assert post["product_type"] == "literature"
        assert post["manifestations"][0]["biblio"]["in"] == BLOG_VENUE
        assert any(i["scheme"] == "doi" for i in post["identifiers"])


def test_translation_is_a_second_manifestation(client):
    post = client.get("/entity", params={"id": KALININDORF_POST}).json()
    assert [m["identifiers"][0]["value"] for m in post["manifestations"]] == [
        "10.82169/3d43-gtxa",
        "10.82169/nyen-609n",
    ]
    assert set(post["titles"]) == {"en", "ru"}


def test_entity_lookup_and_404(client):
    assert client.get("/entity", params={"id": KASSIBER_POST}).status_code == 200
    assert client.get("/entity", params={"id": "https://example.org/nope"}).status_code == 404


def test_unknown_entity_type_is_rejected(client):
    assert client.get("/entities", params={"type": "archive"}).status_code == 400


def test_graph_resolves_author_topics_and_organisations(client):
    document = client.get("/graph", params={"id": KALININDORF_POST}).json()
    identifiers = {e["local_identifier"] for e in document["@graph"]}
    assert KALININDORF_POST in identifiers
    assert GARF in identifiers
    assert "https://blog.ehri-project.eu/author/alexander-kruglov/" in identifiers
    assert "https://blog.ehri-project.eu/tag/massacres/" in identifiers
    assert "https://portal.ehri-project.eu/institutions/ua-003297" in identifiers


def test_search_matches_titles_and_abstracts(client):
    results = client.get("/search", params={"q": "kalinindorf"}).json()["results"]
    assert {e["local_identifier"] for e in results} == {KALININDORF_POST}


def test_paging(client):
    first = client.get("/entities", params={"limit": 2, "offset": 0}).json()
    second = client.get("/entities", params={"limit": 2, "offset": 2}).json()
    assert first["total"] == second["total"]
    assert first["results"] != second["results"]
    assert len(first["results"]) == 2
