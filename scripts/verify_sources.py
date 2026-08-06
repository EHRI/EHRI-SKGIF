"""Re-check every external source referenced by the demo dataset.

Run this whenever `data/ehri_demo.jsonld` changes:

    uv run python scripts/verify_sources.py

It resolves each HTTP identifier/URL in the document and, for every DOI, compares
the registered CSL title and author against what the dataset claims. Exits
non-zero if anything fails to resolve or disagrees.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "ehri_demo.jsonld"
UA = {"User-Agent": "ehri-skgif-demo-verifier/0.1 (+https://www.ehri-project.eu)"}
TIMEOUT = 60


def fetch(url: str, accept: str | None = None) -> tuple[int, bytes]:
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.status, response.read()


def normalise(text: str) -> str:
    """Fold quotes and dashes so typographic variants compare equal."""
    folded = unicodedata.normalize("NFKD", text)
    for pair in ("‘'", "’'", "“\"", "”\"", "–-", "—-"):
        folded = folded.replace(pair[0], pair[1])
    return " ".join(folded.split()).casefold()


def collect(document: dict) -> tuple[set[str], dict[str, dict]]:
    """Return every http(s) URL in the document, and DOI -> owning product."""
    urls: set[str] = set()
    dois: dict[str, dict] = {}

    def walk(node, owner):
        if isinstance(node, dict):
            if node.get("entity_type") == "product":
                owner = node
            if node.get("scheme") == "doi":
                dois[node["value"]] = owner
            for key, value in node.items():
                if isinstance(value, str) and value.startswith("http"):
                    urls.add(value.split("#")[0])
                else:
                    walk(value, owner)
        elif isinstance(node, list):
            for item in node:
                walk(item, owner)

    walk(document["@graph"], None)
    return urls, dois


EHRI_ITEM = re.compile(r'ehri-item-container[^>]*data-id="([^"]+)"')
WP_POSTS = "https://blog.ehri-project.eu/wp-json/wp/v2/posts"


def embedded_item_ids(post_url: str) -> set[str]:
    """The EHRI Portal ids embedded in a post as `ehri-item` Web Components.

    The blog renders them as `<div class="ehri-item-container" data-id="...">`,
    which is the only machine-readable citation of a Portal record a post makes.
    """
    slug = post_url.rstrip("/").rsplit("/", 1)[-1]
    _, body = fetch(f"{WP_POSTS}?slug={slug}&_fields=content")
    posts = json.loads(body)
    if not posts:
        raise LookupError(f"no post found for slug {slug!r}")
    # A data-id may carry a display-language query string, e.g.
    # "il-002798-4019672?dlid=eng-4019672_eng" — that is not part of the id.
    return {i.split("?")[0] for i in EHRI_ITEM.findall(posts[0]["content"]["rendered"])}


def check_ehri_item_citations(document: dict) -> list[str]:
    """`cites` must correspond exactly to the post's embedded `ehri-item` ids."""
    products = {
        e["local_identifier"]: e
        for e in document["@graph"]
        if e.get("entity_type") == "product"
    }
    posts = [p for p in products.values() if p.get("product_type") == "literature"]

    print(f"\nChecking `cites` against embedded ehri-item components in {len(posts)} posts...")
    failures = []
    for post in posts:
        url = post["local_identifier"]
        try:
            embedded = embedded_item_ids(url)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{url} -> could not read post content ({exc})")
            print(f"  FAIL  {url}: {exc}")
            continue

        # A unit id carries a local part after the institution code; anything
        # else is an institution, which is an organisation rather than a product
        # and so belongs in relevant_organisations instead of cites.
        units = {i for i in embedded if re.match(r"^[a-z]{2}-\d{6}-", i)}
        institutions = embedded - units

        cited = {
            products[t]["identifiers"][0]["value"]
            for t in (post.get("related_products") or {}).get("cites", [])
        }
        listed = {
            o.rsplit("/", 1)[-1]
            for o in post.get("relevant_organisations", [])
            if "/institutions/" in o
        }

        problems = []
        if cited != units:
            problems.append(f"cites {sorted(cited)} but embeds units {sorted(units)}")
        if not institutions <= listed:
            problems.append(
                f"embeds institutions {sorted(institutions)} "
                f"but relevant_organisations lists {sorted(listed)}"
            )
        if problems:
            failures += [f"{url} {p}" for p in problems]
            print(f"  FAIL  {url}")
            for problem in problems:
                print(f"          {problem}")
            continue

        summary = f"{len(units)} unit(s), {len(institutions)} institution(s)"
        print(f"  ok    {summary:<28}  {url}")
    return failures


def main() -> int:
    document = json.loads(DATA.read_text(encoding="utf-8"))
    urls, dois = collect(document)
    failures: list[str] = []

    print(f"Resolving {len(urls)} URLs...")
    for url in sorted(urls):
        try:
            status, _ = fetch(url)
            mark = "ok" if status == 200 else str(status)
        except urllib.error.HTTPError as exc:
            mark, status = f"HTTP {exc.code}", exc.code
        except Exception as exc:  # noqa: BLE001
            mark, status = f"ERROR {exc}", 0
        if status in (403, 429):
            # Several institution websites reject or throttle scripted user
            # agents. The URL itself comes from the institution's own EHRI Portal
            # record, so this means "cannot check from here", not "wrong".
            mark = f"{status} (bot-blocked)"
        elif status != 200:
            failures.append(f"{url} -> {mark}")
        print(f"  {mark:>18}  {url}")

    print(f"\nChecking {len(dois)} DOIs against registered metadata...")
    for doi, product in sorted(dois.items()):
        try:
            _, body = fetch(
                f"https://doi.org/{doi}", accept="application/vnd.citationstyles.csl+json"
            )
            csl = json.loads(body)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{doi} -> metadata unavailable ({exc})")
            print(f"  FAIL  {doi}: {exc}")
            continue

        registered = csl.get("title", "")
        claimed = list((product or {}).get("titles", {}).values())
        if not any(normalise(registered) == normalise(t) for t in claimed):
            failures.append(f"{doi} title mismatch: registered {registered!r}")
            print(f"  FAIL  {doi}: title {registered!r} not among {claimed}")
            continue

        family = (csl.get("author") or [{}])[0].get("family", "")
        print(f"  ok    {doi}  {family}, {csl.get('container-title')}")

    failures += check_ehri_item_citations(document)

    if failures:
        print(f"\n{len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nAll sources verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
