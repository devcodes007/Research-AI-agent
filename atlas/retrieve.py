"""Retrieval: search (Composio SDK, with a clearly-labelled fallback), safe page fetch, cache, quote checking.

The LLM never browses. Code retrieves pages, caches them, and later checks every quoted claim against the cache.
"""
import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.parse
from html.parser import HTMLParser

from .config import env, sub

UA = "ToolkitAtlas/1.0 (integration research; public documentation only)"
KEYWORDS = ["oauth", "api key", "api-key", "apikey", "token", "authenticat", "authoriz", "credential", "bearer",
            "basic auth", "pricing", "plan", "free", "trial", "paid", "enterprise", "partner", "approval", "approved",
            "review", "contact sales", "request access", "waitlist", "sandbox", "developer account", "rate limit",
            "mcp", "model context protocol", "webhook", "rest", "graphql", "sdk", "endpoint", "scope"]


# ---------------------------------------------------------------- text extraction
class _Text(HTMLParser):
    SKIP = {"script", "style", "svg", "noscript", "nav", "footer", "head"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag in {"p", "li", "tr", "h1", "h2", "h3", "h4", "br", "div", "pre", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip() + " ")


def html_to_text(html: str) -> str:
    parser = _Text()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = "".join(parser.parts)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", text)).strip()


def norm(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def quote_match(quote: str, text: str) -> str:
    """'exact' if the normalised quote occurs verbatim, 'fuzzy' if >=85% of its 4-grams do, else 'missing'."""
    q, t = norm(quote or ""), norm(text or "")
    if len(q) < 12:
        return "missing"
    if q in t:
        return "exact"
    words = q.split()
    if len(words) < 5:
        return "missing"
    grams = {" ".join(words[i:i + 4]) for i in range(len(words) - 3)}
    hit = sum(1 for g in grams if g in t)
    return "fuzzy" if grams and hit / len(grams) >= 0.85 else "missing"


def windows(text: str, budget: int = 3600, radius: int = 260) -> str:
    """Keep the passages around integration-relevant keywords, within a character budget."""
    if len(text) <= budget:
        return text
    low, spans = text.lower(), []
    for kw in KEYWORDS:
        for m in re.finditer(re.escape(kw), low):
            spans.append((max(0, m.start() - radius), min(len(text), m.end() + radius)))
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    out, used = [text[:500]], 500
    for a, b in merged:
        if a < 500:
            continue
        chunk = text[a:b]
        if used + len(chunk) > budget:
            chunk = chunk[: max(0, budget - used)]
        if not chunk:
            break
        out.append(chunk)
        used += len(chunk)
        if used >= budget:
            break
    return "\n...\n".join(out)


# ---------------------------------------------------------------- safe fetch + cache
def public_url(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise ValueError("only public https URLs")
    if p.port not in (None, 443):
        raise ValueError("non-standard port")
    for info in socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("non-public host")
    return url


def cache_path(url: str):
    return sub("cache") / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")


def fetch(url: str, refresh: bool = False) -> dict:
    """Fetch a public page (cached). Returns {url, final_url, status, text, thin, fetched_at, error?}."""
    path = cache_path(url)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    import httpx
    result = {"url": url, "final_url": url, "status": None, "text": "", "thin": True,
              "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        public_url(url)
        with httpx.Client(follow_redirects=False, timeout=25, headers={"User-Agent": UA, "Accept": "text/html,text/markdown,text/plain,application/json"}) as client:
            current = url
            for _ in range(5):
                resp = client.get(current)
                if resp.is_redirect and resp.headers.get("location"):
                    current = public_url(urllib.parse.urljoin(current, resp.headers["location"]))
                    continue
                break
            result.update(status=resp.status_code, final_url=current)
            ctype = resp.headers.get("content-type", "")
            body = resp.content[:2_000_000].decode(resp.encoding or "utf-8", errors="replace")
            text = html_to_text(body) if ("html" in ctype or body.lstrip().startswith("<")) else body
            result.update(text=text, thin=len(text) < 400)
    except Exception as exc:  # network failure is recorded, never hidden
        result["error"] = str(exc)[:300]
    if result["status"] == 200 or result.get("error"):
        path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


# ---------------------------------------------------------------- search backends
def harvest(obj, out=None):
    """Find {title,url,snippet}-like dicts anywhere in an unknown tool-response structure."""
    out = [] if out is None else out
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        url = next((obj[k] for k in ("url", "link", "href") if isinstance(obj.get(k), str) and obj[k].startswith("http")), None)
        if url:
            out.append({"title": str(obj.get("title") or obj.get("name") or ""), "url": url,
                        "snippet": str(obj.get("snippet") or obj.get("content") or obj.get("description") or obj.get("body") or "")[:400]})
        for v in obj.values():
            harvest(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            harvest(v, out)
    elif isinstance(obj, str) and obj.strip().startswith(("{", "[")):
        try:
            harvest(json.loads(obj), out)
        except ValueError:
            pass
    return out


class ComposioSearcher:
    """Web search through the Composio SDK (COMPOSIO_SEARCH toolkit). Session-based execution works with any LLM."""
    name = "composio"
    SLUGS = ["COMPOSIO_SEARCH_DUCK_DUCK_GO_SEARCH", "COMPOSIO_SEARCH_SEARCH", "COMPOSIO_SEARCH_TAVILY_SEARCH"]

    def __init__(self):
        from composio import Composio
        key = env("COMPOSIO_API_KEY")
        if not key:
            raise RuntimeError("COMPOSIO_API_KEY is not set (free Hobby plan key from composio.dev)")
        self.client = Composio(api_key=key)
        self.user_id = env("COMPOSIO_USER_ID", "toolkit-atlas")
        self.session = None
        for toolkits in (["composio_search"], ["COMPOSIO_SEARCH"]):
            try:
                self.session = self.client.create(user_id=self.user_id, toolkits=toolkits)
                break
            except Exception as exc:
                self.last_error = exc
        self.session_error = None if self.session else self.last_error
        self.slug = env("ATLAS_SEARCH_TOOL")
        self.mode = "session" if self.session else "direct"

    @staticmethod
    def _slugs_in(obj, out=None):
        out = [] if out is None else out
        if hasattr(obj, "model_dump"):
            obj = obj.model_dump()
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("slug", "tool_slug", "name", "tool_name") and isinstance(v, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{5,}", v):
                    out.append(v)
                ComposioSearcher._slugs_in(v, out)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                ComposioSearcher._slugs_in(v, out)
        return out

    def discover(self):
        """Ask Composio which web-search tools this project can actually run (never guess slugs)."""
        found = []
        try:
            if self.session is not None:
                found += self._slugs_in(self.session.search(query="search the web and return result links for a query"))
                try:
                    found += self._slugs_in(self.session.tools())
                except Exception:
                    pass
            for tk in ("composio_search", "COMPOSIO_SEARCH"):
                found += [t.slug for t in self.client.tools.get_raw_composio_tools(toolkits=[tk], limit=60)]
        except Exception:
            pass
        found = list(dict.fromkeys(found))
        skip = ("IMAGE", "NEWS", "SHOPPING", "MAPS", "FINANCE", "SCHOLAR", "TRENDS", "EVENT", "SIMILAR", "SEARCH_TOOLS", "MULTI_EXECUTE")
        usable = [s for s in found if ("SEARCH" in s or "WEB" in s) and not any(k in s for k in skip)]
        order = [s for s in self.SLUGS if s in usable] + [s for s in usable if s not in self.SLUGS]
        return order, found

    def search(self, query: str, limit: int = 8):
        if not self.slug and not getattr(self, "_slugs", None):
            self._slugs, self._all = self.discover()
        slugs = [self.slug] if self.slug else (self._slugs or self.SLUGS)
        errors = []
        for slug in slugs:
            try:
                if self.session is not None:
                    res = self.session.execute(slug, arguments={"query": query})
                else:  # key without session permission: Composio's direct tool execution
                    res = self.client.tools.execute(slug, arguments={"query": query}, user_id=self.user_id,
                                                    dangerously_skip_version_check=True)
                hits = harvest(res)
                if hits:
                    self.slug = slug
                    return hits[:limit]
                errors.append(f"{slug}: no results parsed")
            except Exception as exc:
                errors.append(f"{slug}: {str(exc)[:120]}")
        raise RuntimeError(f"Composio search failed. Visible tools: {getattr(self, '_all', [])[:15]}. Errors: {errors}")


_search_lock = threading.Lock()


class DuckSearcher:
    """Keyless fallback using the `ddgs` metasearch package, trying several engines until one returns results."""
    name = "ddg"
    BACKENDS = ["auto", "duckduckgo", "bing", "brave", "yahoo", "mojeek", "google"]

    def __init__(self):
        self.working = None
        self.errors = []

    def search(self, query: str, limit: int = 8):
        with _search_lock:
            time.sleep(0.8)
            return self._search(query, limit)

    def _search(self, query: str, limit: int = 8):
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        order = [self.working] if self.working else self.BACKENDS
        for backend in order:
            for attempt in range(2):
                try:
                    res = DDGS(timeout=15).text(query, region="us-en", max_results=limit, backend=backend)
                    hits = [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")[:400]} for r in res or []]
                    if hits:
                        self.working = backend
                        return hits
                    break
                except TypeError:  # older package without backend= argument
                    res = DDGS().text(query, max_results=limit)
                    return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")[:400]} for r in res or []]
                except Exception as exc:
                    self.errors.append(f"{backend}: {str(exc)[:80]}")
                    time.sleep(1.5)
        self.working = None
        raise RuntimeError(f"all search engines returned nothing: {self.errors[-6:]}")


def make_searcher():
    backend = env("ATLAS_SEARCH_BACKEND", "composio")
    return DuckSearcher() if backend == "ddg" else ComposioSearcher()


# ---------------------------------------------------------------- ranking
BAD_HOSTS = ("reddit.com", "medium.com", "quora.com", "youtube.com", "facebook.com/public", "pinterest.com/pin",
             "linkedin.com/pulse", "g2.com", "capterra.com", "trustpilot.com", "stackshare.io", "zapier.com", "make.com",
             "pipedream.com", "n8n.io", "composio.dev")


def host_of(hint_or_url: str):
    m = re.search(r"([a-z0-9][a-z0-9.-]+\.[a-z]{2,})(/[^\s)]*)?", hint_or_url.lower())
    return (m.group(1), (m.group(2) or "")) if m else (None, "")


def rank(app: dict, hits: list) -> list:
    host, path = host_of(app.get("hint", ""))
    tokens = [t for t in re.split(r"[^a-z0-9]+", app["name"].lower()) if len(t) > 2]
    scored = {}
    for h in hits:
        url = h["url"]
        if not url.startswith("https://") or any(b in url for b in BAD_HOSTS):
            continue
        u = url.lower()
        score = 0
        if host and host.split("/")[0] in u:
            score += 4
        if any(t in urllib.parse.urlsplit(u).netloc for t in tokens):
            score += 3
        if re.search(r"(developer|developers|docs|api|dev\.|help|support|learn)", u):
            score += 2
        if re.search(r"(auth|oauth|token|credential|getting-started|quickstart|pricing|mcp|rate-limit|access)", u):
            score += 1
        if score > scored.get(url, (-1,))[0]:
            scored[url] = (score, h)
    return [h for _, h in sorted(scored.values(), key=lambda x: -x[0])]


def collect_sources(app: dict, searcher, queries: list, k: int = 6, trace=None) -> list:
    """Search, rank, fetch. Returns [{id:'S1', url, text, thin, status, from}] with provenance."""
    seeds = [(u, "lead") for u in app.get("leads", [])]
    host, path = host_of(app.get("hint", ""))
    # Seed with the hint only when it points at documentation (has a path or a docs/developer host); bare homepages waste a source slot.
    if host and "(" not in app.get("hint", "").split("/")[0] and (path.strip("/") or re.match(r"(developer|developers|docs|api|dev|open)\.", host)):
        seeds.append((f"https://{host}{path}".rstrip(")"), "hint"))
    hits, searched = [], []
    for q in queries:
        try:
            res = searcher.search(q)
            searched.append({"query": q, "results": len(res), "backend": getattr(searcher, "name", "?")})
            hits.extend(res)
        except Exception as exc:
            searched.append({"query": q, "error": str(exc)[:200], "backend": getattr(searcher, "name", "?")})
    if trace is not None:
        trace["searches"] = searched
    urls, seen = [], set()
    for u, origin in seeds + [(h["url"], "search") for h in rank(app, hits)]:
        if u not in seen:
            seen.add(u)
            urls.append((u, origin))
    sources = []
    for u, origin in urls:
        if len(sources) >= k:
            break
        page = fetch(u)
        if page.get("status") == 200 and not page["thin"]:
            sources.append({"id": f"S{len(sources) + 1}", "url": page["final_url"] or u, "requested_url": u,
                            "text": page["text"], "from": origin})
        elif trace is not None:
            trace.setdefault("skipped", []).append({"url": u, "status": page.get("status"), "thin": page.get("thin"), "error": page.get("error")})
    return sources
