# Working on ehri-skgif

Internal notes for developers and coding agents. User-facing documentation lives in
`README.md` — keep implementation rationale out of it.

## Layout

```
data/ehri_demo.jsonld       the entire dataset: @context + @graph
src/ehri_skgif/store.py     loads and indexes the graph, resolves references
src/ehri_skgif/app.py       Flask routes
wsgi.py                     gunicorn entry point (`wsgi:application`)
scripts/verify_sources.py   network re-verification of every source and every citation
tests/test_api.py           endpoint tests and closed-graph checks
```

To change the data, edit `data/ehri_demo.jsonld` only — nothing is hard-coded in the
service except `BLOG_VENUE` in `app.py`, used to recognise blog posts.

## The rule that governs this dataset

**Nothing is asserted that a source does not state.** Every field traces to something
fetched over the network, and `scripts/verify_sources.py` re-checks all of it. When
adding or changing data, run it and make it pass:

```bash
uv run python scripts/verify_sources.py
```

It (1) resolves every HTTP URL in the dataset, (2) compares each DOI against its
registered CSL metadata, and (3) re-reads each post from the blog and checks that
`related_products.cites` matches exactly the unit-level `ehri-item` embeds and that
every institution-level embed appears in `relevant_organisations`.

Institution websites returning HTTP 403/429 to scripted requests (`yadvashem.org`,
`statearchive.ru`) are reported as blocked, not failed — those URLs come from the
institutions' own EHRI Portal records.

### `ehri-item` is the only citation signal

The blog embeds EHRI Portal records as
`<div class="ehri-item-container" data-id="…">`. That `data-id` is the only
machine-readable reference a post makes to a Portal record. Archives merely named in
prose are **not** citations — three of the four current posts name archives that
appear nowhere in the graph, and that is correct.

A `data-id` may carry a display-language query string
(`il-002798-4019672?dlid=eng-4019672_eng`); strip it. Unit ids have a local part after
the institution code (`^[a-z]{2}-\d{6}-`); anything else is an institution.

- **unit embed** → the unit becomes a `product` with `product_type: "other"`,
  manifestation-typed `rico:RecordSet`, and is linked with a reciprocal
  `related_products.cites` / `is_documented_by` pair.
- **institution embed** → goes in `relevant_organisations`. SKG-IF `related_products`
  relates products to products only, so an institution cannot be a `cites` target.
  Modelling archives as products so they could be cited was considered and rejected.

No post in the current set embeds a unit, so the graph has no record-set products and
no `related_products` at all. The unit path is unexercised but is the agreed mapping;
implement it as described if a post gains one.

## Deliberate omissions — do not "fix" these

| Field | Why it is absent |
| --- | --- |
| `licence` | The blog publishes no reuse licence; it carries `© 2015-2026 EHRI Consortium`. Manifestations state `access_rights.status: "open"` with the copyright position in the description. |
| `funding` | The blog states only that EHRI is funded under FP7 and Horizon 2020. EHRI-3 (GA 871111) ended 28 February 2025, before all four posts, so per-post attribution would be a guess. |
| ORCIDs | ORCID records exist for names matching these authors, but none could be confirmed as the same person. Persons are identified by their blog author page. Real EHRI-held ORCIDs belong in `identifiers`. |
| Affiliation for Barnabas Balint | His author-page biography states a completed doctorate and past fellowships, but no current post. |
| `ehri_terms` on topics | The blog's tag vocabulary is not aligned to the Portal `ehri_terms` vocabulary. Topics carry only their tag page identifier and the blog's own label. |
| EHRI Portal `datasource` | Dropped once the record-set products were removed — nothing referenced it. Reinstate it alongside the first unit-level record set. |

## Relation to T4.4

Aligning the blog tag vocabulary to `ehri_terms` is the job of the EHRI Subject
Labelling Tool. Its output would enter this dataset either as additional
`identifiers` on the `topic` entities, or as extra `topics` on the products carrying
`provenance.trust < 1.0`. Everything currently in the graph is editor-assigned and
carries `trust: 1.0`, so trust is available as the discriminator between human and
machine labels.

## Data sources used to build the dataset

- Blog WordPress REST API (`/wp-json/wp/v2/posts`, `/tags`, `/users`) — titles,
  permalinks, publication and modification timestamps, tags, author bios, and the
  post HTML containing the `ehri-item` embeds. Timestamps are GMT; append `+00:00`.
- `doi.org` content negotiation with
  `Accept: application/vnd.citationstyles.csl+json` — registered title, author,
  container title and publisher. EHRI mints under the `10.82169` prefix and resolves
  via `pids.ehri-project.eu`.
- EHRI Portal `/institutions/{id}` and `/units/{id}` pages — names, alternate names,
  websites, titles.
- ROR v2 API (`https://api.ror.org/v2/organizations?query=…`) — organisation IDs.
  Note the v2 response shape: names are under `names[]` with
  `types: ["ror_display"]`, not a flat `name` field.

Translations are separate blog posts with their own DOIs. Model them as an extra
`manifestation` on the same product, not a separate product, and add the translated
title to `titles`.

## Conventions

- Python 3.12. Flask served over WSGI by gunicorn, to match EHRI's other Python
  applications; stdlib only in `scripts/`.
- `local_identifier` values are URLs, so endpoints take them as a query parameter
  (`?id=`) rather than a path segment.
- Tests are offline and must stay that way; network checks belong in
  `scripts/verify_sources.py`.
- Prefer deleting dead code to keeping it "just in case" — the record-set endpoint
  and its helpers were removed when the data stopped exercising them.
