"""PostExtractor — DOM tree → 11-field PostRecord (S03 C3).

Per S02 A2 + S03 design §C3:
  - Input: raw HTML from `BrowserLeaseClient.dom_extract()` (or a
    `MockBrowserBackend.dom_extract()` payload of the same shape).
  - Output: a populated `PostRecord` dataclass with the 11 business
    fields filled and meta fields (`screenshot_path`,
    `collection_backend`) set by the caller (pipeline) per O4.
  - Missing fields are filled with the sentinel `N_A` (string "N/A") for
    string fields, `None` for the nullable `view_count`, and `0` for
    integer metrics so downstream callers can distinguish parse failure
    ("N/A") from a real zero ("0" engagement).

The extractor is intentionally tolerant of partial DOMs because X
profile pages render lazily; the spec requires a placeholder rather
than a raise when a field is missing (A-C3-2).

The 11 fields per S02 A2 §1:
    1.  post_id            : str  (X status id, decimal)
    2.  author_handle      : str  (without leading @)
    3.  text               : str  (normalised whitespace)
    4.  created_at         : str  (ISO-8601 UTC) — or N/A
    5.  post_url           : str  (canonical https://x.com/<h>/status/<id>)
    6.  reply_count        : int
    7.  repost_count       : int
    8.  like_count         : int
    9.  view_count         : Optional[int]    (None if missing/locked)
    10. urls               : str  (comma-joined extracted URLs, "" if none)
    11. dom_hash           : str  (sha256 of normalised HTML)

`screenshot_path` (12) and `collection_backend` (13) live in
`PostRecord` but are owned by the pipeline/lease layer per O5; the
extractor only sets `collection_backend` from a constructor arg
(default `"browser_agent"` matching S02 §C3 narrative).
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

from .schema import PostRecord

logger = logging.getLogger(__name__)

# Sentinel placeholder per A-C3-2.
N_A = "N/A"

# The 11 business-field names — single source of truth, used by tests
# and introspection. Order matches the dataclass declaration.
POST_RECORD_FIELDS: Tuple[str, ...] = (
    "post_id",
    "author_handle",
    "text",
    "created_at",
    "post_url",
    "reply_count",
    "repost_count",
    "like_count",
    "view_count",
    "urls",
    "dom_hash",
)


_TWEET_ID_RX = re.compile(r"/status/(\d{6,})")
_HANDLE_RX = re.compile(r"@?([A-Za-z0-9_]{1,15})")
_WHITESPACE_RX = re.compile(r"\s+")
_URL_RX = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_INT_RX = re.compile(r"-?\d[\d,]*")
_MAX_REASONABLE_SOCIAL_COUNT = 1_000_000_000


def _normalise_text(value: str) -> str:
    return _WHITESPACE_RX.sub(" ", value).strip()


def _parse_count(value: Optional[str]) -> Optional[int]:
    """Parse '1,240' / '9873' / '' → int. None means 'could not parse'."""
    if value is None:
        return None
    match = _INT_RX.search(value)
    if not match:
        return None
    try:
        parsed = int(match.group(0).replace(",", ""))
    except ValueError:
        return None
    if abs(parsed) > _MAX_REASONABLE_SOCIAL_COUNT:
        return None
    return parsed


class _ArticleHTMLParser(HTMLParser):
    """Tiny HTMLParser that captures the data-testid map per article.

    X profile pages mark each tweet container with
    `<article data-testid="tweet" data-tweet-id="…">` and sub-blocks
    with `data-testid="User-Name|tweetText|reply|retweet|like|view"`.
    We capture the **first** article in the DOM and collect:
      - data-tweet-id attribute (post_id)
      - inner text per testid bucket
      - any anchor href + nested datetime inside the article
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._in_article = False
        self._article_depth = -1
        self.tweet_id: Optional[str] = None
        self._buckets: Dict[str, List[str]] = {}
        self._current_bucket: Optional[str] = None
        self._bucket_open_depth: Optional[int] = None
        self.hrefs: List[str] = []
        self.datetimes: List[str] = []
        self.bare_text: List[str] = []

    def handle_starttag(self, tag, attrs):
        self._depth += 1
        attrs_dict = dict(attrs)
        testid = attrs_dict.get("data-testid")

        if not self._in_article and tag == "article" and testid == "tweet":
            self._in_article = True
            self._article_depth = self._depth
            self.tweet_id = attrs_dict.get("data-tweet-id")

        if not self._in_article:
            return

        if tag == "a":
            href = attrs_dict.get("href")
            if href:
                self.hrefs.append(href)
        if tag == "time":
            dt = attrs_dict.get("datetime")
            if dt:
                self.datetimes.append(dt)

        if testid in {"User-Name", "tweetText", "reply", "retweet", "like", "view"}:
            self._current_bucket = testid
            self._bucket_open_depth = self._depth
            self._buckets.setdefault(testid, [])

    def handle_endtag(self, tag):
        if (
            self._in_article
            and self._current_bucket is not None
            and self._bucket_open_depth is not None
            and self._depth == self._bucket_open_depth
        ):
            self._current_bucket = None
            self._bucket_open_depth = None
        if self._in_article and self._depth == self._article_depth and tag == "article":
            self._in_article = False
        self._depth -= 1

    def handle_data(self, data):
        if not self._in_article:
            return
        if self._current_bucket is not None:
            self._buckets[self._current_bucket].append(data)
        else:
            self.bare_text.append(data)

    def bucket_text(self, name: str) -> str:
        return _normalise_text("".join(self._buckets.get(name, [])))

    def has_article(self) -> bool:
        return self.tweet_id is not None or any(self._buckets.values())


@dataclass
class ExtractionResult:
    """Outcome of `PostExtractor.extract` — used by callers to decide
    whether to drop the record or persist with the placeholders."""

    record: PostRecord
    missing_fields: Tuple[str, ...]
    parse_ok: bool


class PostExtractor:
    """DOM tree → PostRecord.

    Per S03 design §C3 the extractor is a pure function over HTML; it
    does not consult the dedup table — that's `DedupQueue`.
    """

    def __init__(
        self,
        *,
        collection_backend: str = "browser_agent",
        x_host: str = "x.com",
    ) -> None:
        self._collection_backend = collection_backend
        self._x_host = x_host

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def extract(
        self,
        html: str,
        *,
        author_handle_hint: Optional[str] = None,
    ) -> ExtractionResult:
        """Parse `html` → ExtractionResult.

        `author_handle_hint` lets the pipeline supply the profile owner
        when the DOM does not include the @-handle (e.g. degraded
        mobile shell). It is *not* used when the DOM has a handle.
        """
        parser = _ArticleHTMLParser()
        parser.feed(html or "")
        parser.close()

        dom_hash = self._hash_html(html)

        if not parser.has_article():
            # Fully missing article — every business field becomes N/A.
            missing = tuple(POST_RECORD_FIELDS[:-1])  # all except dom_hash
            record = PostRecord(
                post_id=N_A,
                author_handle=author_handle_hint or N_A,
                text=N_A,
                created_at=None,
                post_url=N_A,
                reply_count=0,
                repost_count=0,
                like_count=0,
                view_count=None,
                urls="",
                dom_hash=dom_hash,
                screenshot_path=None,
                collection_backend=self._collection_backend,
            )
            return ExtractionResult(record=record, missing_fields=missing, parse_ok=False)

        # --- handle ---
        user_name_text = parser.bucket_text("User-Name")
        handle = self._first_handle(user_name_text, parser.hrefs, author_handle_hint)

        # --- post_id ---
        post_id = parser.tweet_id
        if not post_id:
            post_id = self._tweet_id_from_hrefs(parser.hrefs, handle)

        # --- text ---
        text = parser.bucket_text("tweetText") or None

        # --- created_at ---
        created_at = parser.datetimes[0] if parser.datetimes else None
        # ISO-8601 normalisation: keep canonical Z form if already valid.

        # --- post_url ---
        post_url = self._post_url(post_id, handle, parser.hrefs)

        # --- metrics ---
        reply_count = _parse_count(parser.bucket_text("reply")) or 0
        repost_count = _parse_count(parser.bucket_text("retweet")) or 0
        like_count = _parse_count(parser.bucket_text("like")) or 0
        view_raw = parser.bucket_text("view")
        view_count = _parse_count(view_raw) if view_raw else None

        # --- urls (embedded links inside tweetText) ---
        urls_list = self._extract_text_urls(text or "")
        # Add any in-article hrefs that are external (not status/profile links).
        external_hrefs = [
            h
            for h in parser.hrefs
            if h.startswith("http") and self._x_host not in h
        ]
        for href in external_hrefs:
            if href not in urls_list:
                urls_list.append(href)
        urls = ",".join(urls_list)

        # Determine missing fields BEFORE filling placeholders.
        missing: List[str] = []
        if not post_id:
            missing.append("post_id")
        if not handle:
            missing.append("author_handle")
        if not text:
            missing.append("text")
        if not created_at:
            missing.append("created_at")
        if not post_url:
            missing.append("post_url")
        if view_count is None and not view_raw:
            missing.append("view_count")
        # `urls` empty is *not* a parse failure — many posts legitimately
        # contain no external links. The placeholder for the string-typed
        # `urls` field is the empty string; absence of links is signal,
        # not error.

        record = PostRecord(
            post_id=post_id or N_A,
            author_handle=handle or N_A,
            text=text or N_A,
            created_at=created_at,  # None is the schema's nullable signal.
            post_url=post_url or N_A,
            reply_count=reply_count,
            repost_count=repost_count,
            like_count=like_count,
            view_count=view_count,
            urls=urls,  # "" is the schema's empty marker.
            dom_hash=dom_hash,
            screenshot_path=None,
            collection_backend=self._collection_backend,
        )
        # Mandatory-fields parse_ok per O4: a record without post_id or
        # handle cannot dedup and cannot be persisted; flag as parse-fail
        # so the pipeline can route to screenshot capture.
        parse_ok = bool(post_id and handle)
        return ExtractionResult(record=record, missing_fields=tuple(missing), parse_ok=parse_ok)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_html(html: str) -> str:
        """sha256 over the raw HTML — must match `MockBrowserBackend.dom_extract()`
        and the future real-mode `dom_hash` so a record's hash is the
        same regardless of which layer computes it."""
        return hashlib.sha256((html or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _first_handle(
        user_name_text: str,
        hrefs: List[str],
        hint: Optional[str],
    ) -> Optional[str]:
        for token in user_name_text.split():
            if token.startswith("@"):
                match = _HANDLE_RX.match(token)
                if match:
                    return match.group(1)
        # Fallback: pull the first profile href.
        for href in hrefs:
            stripped = href.lstrip("/")
            if "/" in stripped:
                head, _, _ = stripped.partition("/")
            else:
                head = stripped
            if _HANDLE_RX.fullmatch(head):
                return head
        if hint:
            cleaned = hint.lstrip("@")
            return cleaned or None
        return None

    @staticmethod
    def _tweet_id_from_hrefs(hrefs: List[str], handle: Optional[str]) -> Optional[str]:
        for href in hrefs:
            match = _TWEET_ID_RX.search(href)
            if match:
                return match.group(1)
        return None

    def _post_url(
        self,
        post_id: Optional[str],
        handle: Optional[str],
        hrefs: List[str],
    ) -> Optional[str]:
        if post_id and handle:
            return f"https://{self._x_host}/{handle}/status/{post_id}"
        for href in hrefs:
            if "/status/" in href:
                if href.startswith("http"):
                    return href
                return f"https://{self._x_host}{href if href.startswith('/') else '/' + href}"
        return None

    @staticmethod
    def _extract_text_urls(text: str) -> List[str]:
        seen: List[str] = []
        for match in _URL_RX.finditer(text):
            url = match.group(0).rstrip(".,);")
            if url not in seen:
                seen.append(url)
        return seen

    @classmethod
    def field_names(cls) -> Tuple[str, ...]:
        return POST_RECORD_FIELDS
