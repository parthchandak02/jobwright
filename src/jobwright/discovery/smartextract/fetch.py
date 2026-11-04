"""Page loading (Playwright intelligence report) and HTML cleaning for the LLM."""

import json
import logging
import re

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Same logger name as the old single module, so log output is unchanged.
log = logging.getLogger("jobwright.discovery.smartextract")


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# -- Page intelligence collector ---------------------------------------------

def collect_page_intelligence(url: str, headless: bool = True) -> dict:
    """Load a page with Playwright and collect every signal a scraping engineer
    would look at in DevTools. Returns a structured intelligence report."""
    intel: dict = {
        "url": url,
        "json_ld": [],
        "api_responses": [],
        "data_testids": [],
        "page_title": "",
        "dom_stats": {},
        "card_candidates": [],
    }

    captured_responses: list[dict] = []

    def on_response(response):
        ct = response.headers.get("content-type", "")
        rurl = response.url
        if any(ext in rurl for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico", ".gif", ".webp"]):
            return
        if "json" in ct or "/api/" in rurl or "algolia" in rurl or "graphql" in rurl:
            try:
                body = response.text()
                try:
                    data = json.loads(body)
                except Exception:
                    data = None
                captured_responses.append({
                    "url": rurl,
                    "status": response.status,
                    "size": len(body),
                    "data": data,
                })
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(user_agent=UA)
        page.on("response", on_response)

        page.goto(url, timeout=60000)
        page.wait_for_load_state("networkidle")

        intel["page_title"] = page.title()

        # 1. JSON-LD
        for el in page.query_selector_all('script[type="application/ld+json"]'):
            try:
                data = json.loads(el.inner_text())
                intel["json_ld"].append(data)
            except Exception:
                pass

        # 2. __NEXT_DATA__
        next_data = page.query_selector("script#__NEXT_DATA__")
        if next_data:
            try:
                intel["next_data"] = json.loads(next_data.inner_text())
            except Exception:
                pass

        # 3. data-testid attributes
        intel["data_testids"] = page.evaluate("""
            () => {
                const els = document.querySelectorAll('[data-testid]');
                const results = [];
                els.forEach(el => {
                    results.push({
                        testid: el.getAttribute('data-testid'),
                        tag: el.tagName.toLowerCase(),
                        text: el.innerText?.slice(0, 80) || ''
                    });
                });
                return results.slice(0, 50);
            }
        """)

        # 4. DOM stats
        intel["dom_stats"] = page.evaluate("""
            () => {
                const body = document.body;
                return {
                    total_elements: body.querySelectorAll('*').length,
                    links: body.querySelectorAll('a[href]').length,
                    headings: body.querySelectorAll('h1,h2,h3,h4').length,
                    lists: body.querySelectorAll('ul,ol').length,
                    tables: body.querySelectorAll('table').length,
                    articles: body.querySelectorAll('article').length,
                    has_data_ids: body.querySelectorAll('[data-id]').length,
                };
            }
        """)

        # 5. Find repeating card-like elements
        intel["card_candidates"] = page.evaluate("""
            () => {
                const candidates = [];
                const allParents = document.querySelectorAll('*');

                for (const parent of allParents) {
                    const children = Array.from(parent.children);
                    if (children.length < 3) continue;

                    const tagCounts = {};
                    children.forEach(c => {
                        const key = c.tagName;
                        tagCounts[key] = (tagCounts[key] || 0) + 1;
                    });

                    const dominant = Object.entries(tagCounts).sort((a,b) => b[1]-a[1])[0];
                    if (!dominant || dominant[1] < 3) continue;

                    const repeatingChildren = children.filter(c => c.tagName === dominant[0]);
                    const withText = repeatingChildren.filter(c => c.innerText?.trim().length > 20);
                    if (withText.length < 3) continue;

                    const withLinks = withText.filter(c => c.querySelector('a[href]'));
                    const score = withLinks.length * 2 + withText.length;

                    const parentId = parent.id ? '#' + parent.id : '';
                    const parentClasses = Array.from(parent.classList).filter(c => c.length < 30).slice(0, 3).join('.');
                    const parentTag = parent.tagName.toLowerCase();
                    const parentSelector = parentTag + (parentId || (parentClasses ? '.' + parentClasses : ''));

                    const childTag = dominant[0].toLowerCase();
                    const sampleChild = withText[0];
                    const childClasses = Array.from(sampleChild.classList).filter(c => c.length < 30).slice(0, 3).join('.');
                    const childSelector = childTag + (childClasses ? '.' + childClasses : '');

                    const examples = withText.slice(0, 3).map(c => {
                        const clone = c.cloneNode(true);
                        clone.querySelectorAll('script,style,svg,noscript').forEach(el => el.remove());
                        const html = clone.outerHTML;
                        return html.length > 5000 ? html.slice(0, 5000) + '...' : html;
                    });

                    candidates.push({
                        parent_selector: parentSelector,
                        child_selector: childSelector,
                        child_tag: childTag,
                        total_children: repeatingChildren.length,
                        with_text: withText.length,
                        with_links: withLinks.length,
                        score: score,
                        examples: examples,
                    });
                }

                candidates.sort((a,b) => b.score - a.score);
                return candidates.slice(0, 3);
            }
        """)

        # Capture full rendered HTML
        intel["full_html"] = page.content()

        browser.close()

    # Process API responses
    for resp in captured_responses:
        summary: dict = {
            "url": resp["url"][:200],
            "status": resp["status"],
            "size": resp["size"],
            "_raw_data": resp.get("data"),
        }
        data = resp.get("data")
        if data:
            if isinstance(data, list) and data:
                summary["type"] = f"array[{len(data)}]"
                if isinstance(data[0], dict):
                    summary["first_item_keys"] = list(data[0].keys())[:20]
                    summary["first_item_sample"] = {k: str(v)[:100] for k, v in list(data[0].items())[:8]}
            elif isinstance(data, dict):
                summary["type"] = "object"
                summary["keys"] = list(data.keys())[:20]

                def _explore_nested(obj, path_prefix, depth=0):
                    if depth > 3 or not isinstance(obj, dict):
                        return
                    for key in list(obj.keys())[:15]:
                        val = obj[key]
                        path = f"{path_prefix}.{key}" if path_prefix else key
                        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                            info = {
                                "count": len(val),
                                "first_item_keys": list(val[0].keys())[:20],
                                "first_item_sample": {k: str(v)[:200] for k, v in list(val[0].items())[:8]},
                            }
                            for subkey in list(val[0].keys())[:10]:
                                subval = val[0][subkey]
                                if isinstance(subval, list) and len(subval) > 0 and isinstance(subval[0], dict):
                                    info[f"first_item.{subkey}"] = {
                                        "count": len(subval),
                                        "first_item_keys": list(subval[0].keys())[:15],
                                        "first_item_sample": {k: str(v)[:100] for k, v in list(subval[0].items())[:8]},
                                    }
                                elif isinstance(subval, dict):
                                    info[f"first_item.{subkey}"] = {
                                        "type": "object",
                                        "keys": list(subval.keys())[:15],
                                        "sample": {k: str(v)[:150] for k, v in list(subval.items())[:8]},
                                    }
                            summary[f"nested_{path}"] = info
                        elif isinstance(val, dict) and depth < 3:
                            _explore_nested(val, path, depth + 1)
                _explore_nested(data, "")
        intel["api_responses"].append(summary)

    return intel


# -- Card HTML cleaning (allowlist approach) ----------------------------------

_ALLOWED_ATTRS = {"id", "href", "data-testid", "data-id", "data-type", "data-slug",
                  "role", "aria-label", "aria-labelledby", "type", "name", "for"}
_ALLOWED_PREFIXES = ("data-", "aria-")
_UTILITY_CLASS_RE = re.compile(
    r"^("
    r"[a-z]{1,2}-\d+|"
    r"[a-z]{1,3}-[a-z]{1,3}-\d+|"
    r"col-\d+|"
    r"d-\w+|"
    r"align-\w+|justify-\w+|"
    r"flex-\w+|order-\d+|"
    r"text-\w+|font-\w+|"
    r"bg-\w+|border-\w+|"
    r"rounded-?\w*|shadow-?\w*|"
    r"w-\d+|h-\d+|"
    r"position-\w+|overflow-\w+|"
    r"float-\w+|clearfix|"
    r"visible-\w+|invisible|"
    r"sr-only|"
    r"css-[a-z0-9]+|"
    r"sc-[a-zA-Z]+|"
    r"sc-[a-f0-9]+-\d+"
    r")$"
)


def clean_card_html(html: str) -> str:
    """Strip layout noise from card HTML, keep only what the LLM needs for selectors."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(True):
        new_attrs: dict = {}
        for attr, val in list(tag.attrs.items()):
            if attr in _ALLOWED_ATTRS or any(attr.startswith(p) for p in _ALLOWED_PREFIXES):
                new_attrs[attr] = val
            elif attr == "class":
                classes = val if isinstance(val, list) else val.split()
                kept = [c for c in classes if not _UTILITY_CLASS_RE.match(c)]
                if kept:
                    new_attrs["class"] = kept
        tag.attrs = new_attrs

    return str(soup)


def clean_page_html(html: str, max_chars: int = 150_000) -> str:
    """Strip full page HTML to essential structure for LLM card detection."""
    soup = BeautifulSoup(html, "html.parser")

    main = soup.find("main") or soup.find(attrs={"role": "main"})
    if main and len(str(main)) > 1000:
        soup = BeautifulSoup(str(main), "html.parser")

    for tag in soup.find_all(["script", "style", "svg", "noscript", "iframe",
                              "link", "meta", "head", "footer", "nav"]):
        tag.decompose()

    for tag in soup.find_all(True):
        new_attrs: dict = {}
        for attr, val in list(tag.attrs.items()):
            if attr in _ALLOWED_ATTRS or any(attr.startswith(p) for p in _ALLOWED_PREFIXES):
                new_attrs[attr] = val
            elif attr == "class":
                classes = val if isinstance(val, list) else val.split()
                kept = [c for c in classes if not _UTILITY_CLASS_RE.match(c)]
                if kept:
                    new_attrs["class"] = kept
        tag.attrs = new_attrs

    for tag in soup.find_all(True):
        if not tag.get_text(strip=True) and not tag.find("img") and not tag.find("a"):
            tag.decompose()

    result = str(soup)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n<!-- TRUNCATED -->"
    return result
