"""Turn documents and websites into knowledge-base entries.

    PDF / Word (.docx) / text  ->  sections (by heading)  ->  chunks of ~1,500 characters  ->  KnowledgeItems
    Website URL (+ linked pages on the same site)  ->  the same

Runs in a background thread (imports can take a while); the KnowledgeSource row shows progress and errors.
"""
import hashlib
import io
import logging
import re
import threading
import zipfile
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse
from xml.etree import ElementTree

import requests
from django.conf import settings
from django.db import close_old_connections, transaction

from core.netguard import UnsafeHostError, assert_public_host

from .models import KnowledgeItem, KnowledgeSource

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 300
MAX_CHARS_PER_SOURCE = 400_000
MAX_ENTRIES_PER_SOURCE = 300
CHUNK_TARGET, CHUNK_MAX = 1200, 1800
CHUNK_MIN = 220  # sections shorter than this are merged with their neighbours
MAX_WEB_PAGES = 15
MAX_PAGE_BYTES = 3 * 1024 * 1024
# Pages most worth reading on an organisation's site (schools, consultancies, shops, clinics...)
USEFUL_LINK_WORDS = [
    "about", "course", "program", "programme", "fee", "fees", "price", "pricing", "admission", "admissions", "faq",
    "service", "services", "visa", "study", "abroad", "country", "countries", "university", "college", "scholarship",
    "contact", "class", "classes", "batch", "schedule", "product", "shop", "delivery", "policy", "team", "why",
]
SKIP_LINK_WORDS = ["login", "signin", "register", "cart", "checkout", "account", "privacy", "terms", "cookie", "wp-admin",
                   "feed", "tag/", "author/", "page/", "search", "mailto:", "tel:", "javascript:"]


class IngestError(Exception):
    """Shown to the user as the import's error."""


# ------------------------------------------------------------------ text helpers
def _clean(text):
    text = unescape(text or "").replace(" ", " ").replace("\r", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _looks_like_heading(line):
    """Short line without sentence punctuation: 'Fee Structure', '2. Admission Process', 'BBA Program'."""
    s = line.strip()
    if "|" in s:
        return False  # table rows are data
    if not 3 <= len(s) <= 80 or s.endswith((".", ",", ";", "?")) or s.count(" ") > 9:
        return False
    if s.endswith(":"):
        return True
    if re.match(r"^(\d+(\.\d+)*[.)]?|[IVX]+\.|[A-Z]\.)\s+\S", s):
        return not re.search(r"\d.*\d", s[2:])  # "2. Admission Process" yes, "1. Fill the form by Bhadra 15" no
    if re.search(r"\d|rs\.?\s|\$|रु", s.lower()):
        return False  # prices, dates and counts are facts, not headings
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper = sum(c.isupper() for c in letters) / len(letters)
    titled = sum(w[:1].isupper() for w in s.split() if w[:1].isalpha()) / max(1, len([w for w in s.split() if w[:1].isalpha()]))
    return s.endswith(":") or upper > 0.7 or titled > 0.75 or any("ऀ" <= c <= "ॿ" for c in s[:2])


def sections_from_text(text, default_title):
    """Split plain text into (heading, body) sections using heading-looking lines."""
    sections, title, body = [], default_title, []
    for line in _clean(text).split("\n"):
        if _looks_like_heading(line) and (body or title == default_title):
            if body:
                sections.append((title, "\n".join(body).strip()))
            title, body = line.strip().rstrip(":"), []
        else:
            body.append(line)
    if body:
        sections.append((title, "\n".join(body).strip()))
    return [(t, b) for t, b in sections if b.strip()]


def _split_long(text, limit=CHUNK_MAX):
    """Split a long body at paragraph, then sentence boundaries."""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        pieces = [para] if len(para) <= limit else re.split(r"(?<=[.!?।])\s+", para)
        for piece in pieces:
            while len(piece) > limit:  # one giant "sentence" (e.g. a table): hard cut
                parts.append(piece[:limit])
                piece = piece[limit:]
            if len(cur) + len(piece) + 2 > CHUNK_TARGET and cur:
                parts.append(cur.strip())
                cur = ""
            cur += piece + ("\n\n" if piece is para else " ")
    if cur.strip():
        parts.append(cur.strip())
    return parts


def chunk_sections(sections, doc_name):
    """One entry per heading (precise search and sources); tiny sections are merged, huge ones split."""
    entries, titles, buf = [], [], ""

    def flush():
        nonlocal titles, buf
        if buf.strip():
            named = [t for t in titles if t and t != doc_name] or [doc_name]
            entries.append((" · ".join(dict.fromkeys(named)), buf.strip()))
        titles, buf = [], ""

    for title, body in sections:
        if buf and (len(buf) >= CHUNK_MIN or len(buf) + len(body) > CHUNK_TARGET):
            flush()
        if len(body) > CHUNK_MAX:
            flush()
            for i, part in enumerate(_split_long(body)):
                entries.append((title if i == 0 else f"{title} (cont. {i + 1})", part))
            continue
        if titles and title not in titles:
            body = f"{title}:\n{body}"
        titles.append(title)
        buf += body + "\n\n"
    flush()
    seen, out = set(), []
    for title, content in entries:
        key = hashlib.sha1(re.sub(r"\W+", "", content.lower()).encode()).hexdigest()
        if key in seen or len(re.sub(r"\W", "", content)) < 8:
            continue  # repeated header/footer text, empty bits
        seen.add(key)
        out.append(((title or doc_name)[:200], content[:4000]))
    return out[:MAX_ENTRIES_PER_SOURCE]


# ------------------------------------------------------------------ files
def extract_pdf(data):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise IngestError("This PDF is password-protected. Remove the password and upload it again.") from exc
        pages = reader.pages[:MAX_PDF_PAGES]
        text = "\n\n".join((p.extract_text() or "") for p in pages)
    except PdfReadError as exc:
        raise IngestError("This file isn't a readable PDF.") from exc
    if len(re.sub(r"\s", "", text)) < 40:
        raise IngestError("No text found. This PDF looks like scanned images; upload a PDF with selectable text, or a Word file.")
    return text, len(pages)


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_docx(data):
    """Paragraphs and tables from a .docx, with Word heading styles kept as headings."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ElementTree.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise IngestError("This file isn't a readable Word (.docx) document. Old .doc files: save as .docx first.") from exc
    body = root.find(f"{W}body")
    lines = []

    def para_text(p):
        return "".join(t.text or "" for t in p.iter(f"{W}t")).strip()

    for el in (body if body is not None else []):
        if el.tag == f"{W}p":
            txt = para_text(el)
            if not txt:
                continue
            style = el.find(f"{W}pPr/{W}pStyle")
            is_heading = style is not None and re.match(r"(?i)(heading|title)", style.get(f"{W}val", ""))
            lines.append(f"\n{txt.rstrip(':')}:" if is_heading else txt)
        elif el.tag == f"{W}tbl":
            for row in el.iter(f"{W}tr"):
                cells = [" ".join(para_text(p) for p in c.iter(f"{W}p")).strip() for c in row.iter(f"{W}tc")]
                if any(cells):
                    lines.append(" | ".join(cells))
    text = "\n".join(lines)
    if len(text.strip()) < 20:
        raise IngestError("No text found in this Word document.")
    return text, 0


def extract_text_file(data):
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(enc), 0
        except UnicodeDecodeError:
            continue
    raise IngestError("Couldn't read this text file.")


def extract_file(name, data):
    if len(data) > MAX_FILE_BYTES:
        raise IngestError("The file is larger than 10 MB.")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if data[:5] == b"%PDF-" or ext == "pdf":
        return extract_pdf(data)
    if ext == "docx" or data[:2] == b"PK":
        return extract_docx(data)
    if ext in ("txt", "md", "csv"):
        return extract_text_file(data)
    raise IngestError("Upload a PDF, Word (.docx) or text (.txt) file.")


# ------------------------------------------------------------------ websites
class _PageParser(HTMLParser):
    """Visible text with headings as section breaks, plus the page's links and title."""

    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside", "iframe", "template", "button"}
    BLOCK = {"p", "div", "li", "tr", "br", "section", "article", "table", "ul", "ol", "dd", "dt", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.links, self.title = [""], [], ""
        self._skip, self._in_title, self._heading = 0, False, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
            self.lines.append(" ")
        if self._skip:
            return
        if tag in ("h1", "h2", "h3", "h4"):
            self._heading = True
            self.lines.append("\n")
        elif tag in self.BLOCK:
            self.lines.append("\n")
        elif tag in ("td", "th"):
            self.lines.append(" | ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in ("h1", "h2", "h3", "h4") and not self._skip:
            self._heading = False
            self.lines.append(":\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and data.strip():
            self.lines.append(data)

    def text(self):
        out = "".join(self.lines)
        out = re.sub(r"[ \t]*\|[ \t]*(\| *)+", " | ", out)
        out = re.sub(r"(?m)^[ \t]*\|[ \t]*|[ \t]*\|[ \t]*$", "", out)  # no leading/trailing | on table rows
        return _clean(out)


def _fetch(url):
    """GET a public web page safely (no internal addresses, size and time limits, checked redirects)."""
    for _ in range(4):
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise IngestError("Enter a full website address starting with https://")
        try:
            assert_public_host(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
        except UnsafeHostError as exc:
            raise IngestError(str(exc)) from exc
        try:
            resp = requests.get(url, timeout=12, stream=True, allow_redirects=False, headers={
                "User-Agent": f"OmniInboxBot/1.0 (+{settings.FRONTEND_URL}) knowledge import",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
            })
        except requests.RequestException as exc:
            raise IngestError(f"Couldn't open {parts.hostname}. Check the address and that the site is online.") from exc
        if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
            url = urljoin(url, resp.headers["Location"])
            continue
        if resp.status_code >= 400:
            raise IngestError(f"The website answered {resp.status_code} for {url}.")
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype and "text/plain" not in ctype:
            raise IngestError("That link isn't a web page (it may be a file: download it and upload it instead).")
        body = b""
        for chunk in resp.iter_content(65536):
            body += chunk
            if len(body) > MAX_PAGE_BYTES:
                break
        enc = resp.encoding if resp.encoding and resp.encoding.lower() != "iso-8859-1" else "utf-8"
        return url, body.decode(enc, errors="replace")
    raise IngestError("Too many redirects.")


def _same_site(a, b):
    ha, hb = urlparse(a).hostname or "", urlparse(b).hostname or ""
    return ha.removeprefix("www.") == hb.removeprefix("www.")


def _link_score(url):
    u = url.lower()
    if any(w in u for w in SKIP_LINK_WORDS) or re.search(r"\.(pdf|jpe?g|png|gif|webp|zip|docx?|xlsx?|mp4|mp3)(\?|$)", u):
        return -1
    return sum(3 for w in USEFUL_LINK_WORDS if w in u) + (1 if u.count("/") <= 4 else 0)


def crawl(start_url, follow_links=True, max_pages=MAX_WEB_PAGES):
    """Return [(page_title, url, text)] for the start page and the most useful pages it links to."""
    first_url, html = _fetch(start_url)
    pages, queue, seen = [], [], {urldefrag(first_url)[0].rstrip("/")}

    def add(url, html):
        p = _PageParser()
        p.feed(html)
        text = p.text()
        if len(re.sub(r"\W", "", text)) >= 15:
            pages.append((_clean(p.title)[:200] or urlparse(url).path or url, url, text))
        return p.links

    links = add(first_url, html)
    if follow_links:
        for href in links:
            u = urldefrag(urljoin(first_url, href.strip()))[0].rstrip("/")
            if u not in seen and _same_site(u, first_url) and _link_score(u) >= 0:
                seen.add(u)
                queue.append(u)
        queue.sort(key=_link_score, reverse=True)
        for u in queue[: max_pages - 1]:
            try:
                final, html = _fetch(u)
                add(final, html)
            except IngestError:
                continue
    if not pages:
        raise IngestError("No readable text found on that page. If the site is built only with JavaScript, copy the text in by hand.")
    return pages


# ------------------------------------------------------------------ run an import
def _save_entries(source, entries):
    from . import search
    with transaction.atomic():
        source.items.all().delete()
        items = KnowledgeItem.objects.bulk_create(
            [KnowledgeItem(workspace=source.workspace, source=source, title=t, content=c) for t, c in entries])
    try:
        search.embed_items([i.id for i in items])
    except Exception:  # noqa: BLE001 - search still works by keywords without embeddings
        logger.exception("Embedding imported knowledge failed for source %s", source.id)
    return len(items)


def run_import(source_id, data=None):
    """Background job: read the file/website, create the entries, mark the source ready or failed."""
    close_old_connections()
    source = KnowledgeSource.objects.select_related("workspace").filter(id=source_id).first()
    if source is None:
        return
    try:
        if source.kind == KnowledgeSource.FILE:
            text, pages = extract_file(source.name, data or b"")
            text = text[:MAX_CHARS_PER_SOURCE]
            doc = source.name.rsplit(".", 1)[0]
            entries = chunk_sections(sections_from_text(text, doc), doc)
            source.pages, source.chars = pages, len(text)
        else:
            web = crawl(source.url, follow_links=source.crawl)
            entries, total = [], 0
            for title, url, text in web:
                text = text[: max(0, MAX_CHARS_PER_SOURCE - total)]
                total += len(text)
                entries += chunk_sections(sections_from_text(text, title), title)
            if web[0][0] and (not source.name or source.name == urlparse(source.url).hostname):
                source.name = web[0][0][:255]  # the site's own title instead of its address
            source.pages, source.chars = len(web), total
            entries = entries[:MAX_ENTRIES_PER_SOURCE]
        if not entries:
            raise IngestError("Nothing useful to import was found.")
        _save_entries(source, entries)
        source.status, source.error = KnowledgeSource.READY, ""
    except IngestError as exc:
        source.status, source.error = KnowledgeSource.FAILED, str(exc)[:500]
    except Exception:  # noqa: BLE001
        logger.exception("Knowledge import %s failed", source_id)
        source.status, source.error = KnowledgeSource.FAILED, "Something went wrong while reading it. Try again or upload a different file."
    source.save()
    close_old_connections()


def start_import(source, data=None):
    """Run the import off the request thread (tests can patch this to run inline)."""
    if getattr(settings, "KNOWLEDGE_IMPORT_SYNC", False):
        run_import(source.id, data)
        return
    threading.Thread(target=run_import, args=(source.id, data), daemon=True).start()
