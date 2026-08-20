# ehri-skgif

A demo service that serves the four most recent [EHRI Document
Blog](https://blog.ehri-project.eu) posts as **SKG-IF v1.0.0** research products, so
they can be consumed by an SKG-IF client such as the GRAPHIA Federated Gateway.

The data is static, real and verified against live sources: posts, DOIs, authors and
EHRI Portal institutions were each fetched and checked before being recorded.

## Install and run

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run main.py
```

The service starts on <http://127.0.0.1:8000>.

It is a WSGI application, so in production it is served by gunicorn:

```bash
uv run gunicorn -w 4 -b 0.0.0.0:8000 wsgi:application
```

## Endpoints

| Endpoint | Returns |
| --- | --- |
| `GET /` | Service description and entity counts |
| `GET /dump` | The whole graph as one JSON-LD document (`application/ld+json`) |
| `GET /entities?type=product` | Entities of one SKG-IF type, paged |
| `GET /entity?id=<local_identifier>` | One entity |
| `GET /products?product_type=literature` | Research products, optionally filtered by product type |
| `GET /blog-posts` | The products published in the EHRI Document Blog |
| `GET /graph?id=<local_identifier>` | An entity plus everything it references, as JSON-LD |
| `GET /search?q=kalinindorf` | Substring search over titles, abstracts, labels and names |

`local_identifier` values are URLs, so they are passed as a query parameter rather
than a path segment:

```bash
curl -s 'localhost:8000/entity?id=https://blog.ehri-project.eu/2026/06/29/the-extermination-of-jews-in-the-kalinindorf/'
```

`/entities` and `/products` accept `limit` (1–500, default 50) and `offset`, and
return `{"total": …, "offset": …, "limit": …, "results": […]}`. `/dump` and `/graph`
return `{"@context": …, "@graph": […]}` with the official SKG-IF context.

## What the graph contains

| Post | Author | DOI |
| --- | --- | --- |
| ‘Since the collar is stiff…’: Secret Notes from Austrian Resistance Members in Gestapo Captivity | Barnabas Balint | `10.82169/0uvs-h85n` |
| The Extermination of Jews in the Kalinindorf Jewish National Raion of 1941 | Alexander Kruglov | `10.82169/3d43-gtxa` (Russian version: `10.82169/nyen-609n`) |
| “A Child is Born”: The Mysterious Case of Harry Wapniarka | Olga Ştefan | `10.82169/6njj-cnqx` |
| Holocaust Studies in Ukraine: A Scholar’s Path through Fragmentation | Hanna Abakunova | `10.82169/9pnj-35bm` |

Alongside the four posts: their authors (`person`), six organisations
(`organisation`), ten blog subject tags (`topic`), the blog as `venue` and as
`datasource`.

Each post is a `product` with `product_type: "literature"`, a manifestation typed
`fabio:BlogPost` and identified by its DOI. Where a post has a translation, that
translation is an additional manifestation on the same product with its own DOI.

A post is linked to archival material only where the post itself embeds an EHRI
Portal record as an `ehri-item` component. Two posts embed an institution, which
appears in their `relevant_organisations`; none embeds a record set, so no post
carries `related_products`.
