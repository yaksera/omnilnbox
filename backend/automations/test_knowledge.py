"""Knowledge import (PDF / Word / text / website), meaning + keyword search, and sources on AI answers."""
import io
import json
import zipfile
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Workspace
from inbox.models import Message

from . import ingest, search
from .models import AssistantSettings, KnowledgeItem, KnowledgeSource
from .tests import Base, llm_returns

PROSPECTUS = """Sunrise College Prospectus 2083

About Us
Sunrise College in Baneshwor, Kathmandu has taught BBA and BCA since 2065. We are affiliated to Tribhuvan University.

BBA Program
Four years, eight semesters. Total fee Rs 4,80,000, payable in 8 instalments. Classes run 7 AM to 12 PM.

Admission Process
1. Fill the online form. 2. Entrance exam on Bhadra 15. 3. Interview. Bring +2 transcript, character certificate and 4 photos.

Scholarships
Full scholarship for the top 5 entrance scores; 50% for Dalit, Janajati and remote-area students.
"""


def make_docx(paragraphs):
    """Minimal .docx: [(text, style or None)]."""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(
        f'<w:p>{f"<w:pPr><w:pStyle w:val=\'{style}\'/></w:pPr>" if style else ""}<w:r><w:t>{text}</w:t></w:r></w:p>'
        for text, style in paragraphs)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def make_pdf(lines):
    """A tiny one-page PDF with real (selectable) text."""
    ops = "BT /F1 11 Tf 50 750 Td " + " ".join(f"({ln}) Tj 0 -16 Td" for ln in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    return out.encode()


class ChunkingTests(TestCase):
    def test_sections_follow_headings(self):
        entries = ingest.chunk_sections(ingest.sections_from_text(PROSPECTUS, "Prospectus"), "Prospectus")
        titles = [t for t, _ in entries]
        self.assertTrue(any("BBA Program" in t or "About Us" in t for t in titles), titles)
        joined = "\n".join(c for _, c in entries)
        for fact in ("Rs 4,80,000", "Bhadra 15", "top 5 entrance"):
            self.assertIn(fact, joined)
        self.assertTrue(all(len(c) <= 4000 for _, c in entries))

    def test_long_text_is_split_and_repeats_dropped(self):
        body = ("Visa documents: passport, offer letter, bank statement. " * 120).strip()
        entries = ingest.chunk_sections([("Visa checklist", body), ("Footer", "© Sunrise 2083"), ("Footer", "© Sunrise 2083")], "Doc")
        self.assertGreater(len(entries), 2)
        self.assertTrue(all(len(c) <= ingest.CHUNK_MAX for _, c in entries))
        self.assertTrue(entries[1][0].startswith("Visa checklist (cont."))

    def test_docx_headings_and_pdf_text(self):
        text, _ = ingest.extract_docx(make_docx([("Fee Structure", "Heading1"), ("BCA: Rs 3,60,000 for 4 years.", None)]))
        self.assertIn("Fee Structure:", text)
        self.assertIn("Rs 3,60,000", text)
        text, pages = ingest.extract_pdf(make_pdf(["Australia Visa Checklist", "Passport, CoE, GTE statement, bank balance letter."]))
        self.assertEqual(pages, 1)
        self.assertIn("GTE statement", text)

    def test_scanned_pdf_and_wrong_file_are_explained(self):
        with self.assertRaisesMessage(ingest.IngestError, "scanned"):
            ingest.extract_pdf(make_pdf([""]))
        with self.assertRaisesMessage(ingest.IngestError, "Upload a PDF"):
            ingest.extract_file("photo.png", b"\x89PNG....")


class KnowledgeImportTests(Base):
    def upload(self, name, data):
        return self.c.post("/api/ai/knowledge/sources/upload/", {"file": SimpleUploadedFile(name, data)}, format="multipart")

    def test_upload_pdf_word_text_creates_reviewable_entries(self):
        r = self.upload("Prospectus 2083.txt", PROSPECTUS.encode())
        self.assertEqual(r.status_code, 201, r.data)
        src = KnowledgeSource.objects.get(id=r.data["id"])
        self.assertEqual(src.status, "ready", src.error)
        self.assertGreater(src.items.count(), 1)
        listed = self.c.get("/api/ai/knowledge/sources/").data
        self.assertEqual(listed[0]["entries"], src.items.count())
        entry = self.c.get("/api/ai/knowledge/").data[0]
        self.assertEqual(entry["source"]["name"], "Prospectus 2083.txt")
        # review & edit an imported entry like any other
        r = self.c.put(f"/api/ai/knowledge/{entry['id']}/", {"title": "Edited", "content": "Corrected fact."}, format="json")
        self.assertEqual(r.status_code, 200)

        self.assertEqual(self.upload("checklist.pdf", make_pdf(["Japan Visa", "COE, passport, Japanese language certificate N5."])).data["status"], "processing")
        self.assertEqual(KnowledgeSource.objects.get(name="checklist.pdf").status, "ready")
        self.upload("fees.docx", make_docx([("Fees", "Heading1"), ("MBA Rs 6,00,000", None)]))
        self.assertEqual(KnowledgeSource.objects.get(name="fees.docx").status, "ready")
        # deleting a document removes its entries
        self.c.delete(f"/api/ai/knowledge/sources/{src.id}/")
        self.assertFalse(KnowledgeItem.objects.filter(source_id=src.id).exists())

    def test_bad_uploads(self):
        self.assertEqual(self.upload("song.mp3", b"ID3....").status_code, 400)
        r = self.upload("scan.pdf", make_pdf([""]))
        self.assertEqual(KnowledgeSource.objects.get(id=r.data["id"]).status, "failed")
        self.assertIn("scanned", KnowledgeSource.objects.get(id=r.data["id"]).error)

    def test_website_import_reads_useful_pages_only(self):
        site = {
            "https://sunrise.edu.np/": '<html><title>Sunrise College</title><nav><a href="/login">Login</a></nav>'
                                       '<h1>Welcome</h1><p>Best BBA college in Kathmandu with 20 years of results.</p>'
                                       '<a href="/fees">Fees</a> <a href="/admission">Admission</a> <a href="https://other.com/x">x</a>'
                                       '<a href="/brochure.pdf">pdf</a><script>var x=1</script><footer>© 2083</footer></html>',
            "https://sunrise.edu.np/fees": "<html><title>Fees</title><h2>BBA fees</h2><table><tr><td>BBA</td><td>Rs 4,80,000</td></tr></table></html>",
            "https://sunrise.edu.np/admission": "<html><title>Admission</title><h2>How to apply</h2><p>Entrance exam on Bhadra 15 every year at the college.</p></html>",
        }
        fetched = []

        class Resp:
            def __init__(self, url):
                self.url, self.status_code = url, 200 if url in site else 404
                self.headers, self.encoding = {"Content-Type": "text/html; charset=utf-8"}, "utf-8"

            def iter_content(self, n):
                yield site.get(self.url, "").encode()

        def get(url, **kw):
            fetched.append(url)
            return Resp(url)

        with mock.patch("automations.ingest.requests.get", side_effect=get), mock.patch("automations.ingest.assert_public_host"):
            r = self.c.post("/api/ai/knowledge/sources/url/", {"url": "https://sunrise.edu.np/", "crawl": True}, format="json")
        src = KnowledgeSource.objects.get(id=r.data["id"])
        self.assertEqual((src.status, src.pages), ("ready", 3), src.error)
        self.assertNotIn("https://sunrise.edu.np/login", fetched)
        self.assertNotIn("https://other.com/x", fetched)
        self.assertFalse(any(u.endswith(".pdf") for u in fetched))
        text = " ".join(src.items.values_list("content", flat=True))
        self.assertIn("Rs 4,80,000", text)
        self.assertIn("Bhadra 15", text)
        self.assertNotIn("var x", text)
        self.assertNotIn("Login", text)

    def test_website_import_blocks_internal_addresses(self):
        r = self.c.post("/api/ai/knowledge/sources/url/", {"url": "http://127.0.0.1:8000/admin/", "crawl": False}, format="json")
        src = KnowledgeSource.objects.get(id=r.data["id"])
        self.assertEqual(src.status, "failed")
        self.assertIn("private address", src.error)

    def test_only_managers_can_import(self):
        from django.contrib.auth import get_user_model
        u = get_user_model().objects.create_user("agent@example.com", "agent@example.com", "Kathmandu-Blue-42")
        self.ws.memberships.create(user=u, role="agent")
        agent = APIClient()
        agent.force_authenticate(u)
        r = agent.post("/api/ai/knowledge/sources/upload/", {"file": SimpleUploadedFile("a.txt", b"hello world " * 10)}, format="multipart")
        self.assertEqual(r.status_code, 403)


class SearchTests(Base):
    def add(self, title, content):
        return KnowledgeItem.objects.create(workspace=self.ws, title=title, content=content)

    def test_keyword_search_understands_nepali_and_romanized(self):
        self.add("Admission fee", "BBA admission costs Rs 25,000 at the time of enrollment.")
        self.add("Location", "We are in Baneshwor, Kathmandu, opposite the Election Commission.")
        self.add("Japan visa", "Documents: COE, passport, language certificate.")
        for q, expected in [("bharna ko shulka kati ho?", "Admission fee"), ("tapai ko office kaha cha?", "Location"),
                            ("जापान भिसा कागजात", "Japan visa"), ("How much is the admission fee?", "Admission fee")]:
            self.assertEqual(search.search(self.ws, q)[0]["title"], expected, q)
        r = self.c.get("/api/ai/knowledge/search/", {"q": "bharna kati"}).data
        self.assertEqual(r[0]["title"], "Admission fee")
        self.assertEqual(r[0]["match"], "keywords")

    @override_settings(EMBEDDINGS_ENABLED=True)
    def test_meaning_search_with_embeddings(self):
        def fake_embed(texts):
            # toy "meaning": dimension 0 = money, 1 = place
            out = []
            for t in texts:
                t = t.lower()
                out.append(search._normalize([1.0 if any(w in t for w in ("fee", "rs", "paisa", "लाग्छ")) else 0.05,
                                              1.0 if any(w in t for w in ("where", "baneshwor", "ठाउँ")) else 0.05]))
            return out
        with mock.patch("automations.search.embed_texts", side_effect=fake_embed):
            a = self.add("Tuition", "Rs 4,80,000 for four years.")
            b = self.add("Campus", "Baneshwor, Kathmandu.")
            search.embed_items([a.id, b.id])
            res = search.search(self.ws, "पढ्न कति पैसा लाग्छ?")  # no shared keywords with "Tuition"
        self.assertEqual(res[0]["title"], "Tuition")
        self.assertEqual(res[0]["match"], "meaning")

    def test_big_knowledge_base_sends_best_matches(self):
        for i in range(60):
            self.add(f"Course {i}", f"Course number {i} covers topic {i}. " * 15)
        self.add("Scholarship", "Full scholarship for top 5 entrance scores.")
        kb, refs = __import__("automations.ai", fromlist=["x"]).knowledge_context(self.ws, "scholarship chha?")
        self.assertEqual(refs[0]["title"], "Scholarship")
        self.assertLessEqual(len(kb), 12000 + 2000)


class SourcesOnAnswersTests(Base):
    def test_bot_reply_records_which_entries_it_used(self):
        cfg = AssistantSettings.for_workspace(self.ws)
        cfg.bot_mode = "always"
        cfg.save()
        src = KnowledgeSource.objects.create(workspace=self.ws, kind="file", name="Prospectus.pdf", status="ready")
        KnowledgeItem.objects.create(workspace=self.ws, source=src, title="BBA fee", content="Rs 4,80,000 for 4 years.")
        KnowledgeItem.objects.create(workspace=self.ws, title="Location", content="Baneshwor.")
        patch, calls = llm_returns({"reply": "BBA ko fee Rs 4,80,000 ho.", "handoff": False, "reason": "",
                                    "category": "question", "sentiment": "neutral", "sources": [1]})
        with patch:
            self.customer_says("BBA ko fee kati ho?")
        self.assertIn("[1] ### BBA fee (from: Prospectus.pdf)", calls[0][0]["content"])
        msg = Message.objects.get(bot="ai", direction="out")
        self.assertEqual(msg.sources, [{"id": msg.sources[0]["id"], "kind": "knowledge", "title": "BBA fee", "source": "Prospectus.pdf"}])
        api_msgs = self.c.get(f"/api/conversations/{msg.conversation_id}/messages/").data
        self.assertEqual([m["sources"][0]["title"] for m in api_msgs if m["bot"] == "ai"], ["BBA fee"])

    def test_playground_and_suggest_return_sources(self):
        KnowledgeItem.objects.create(workspace=self.ws, title="Delivery", content="Rs 100 inside the Valley.")
        patch, _ = llm_returns({"reply": "Rs 100.", "handoff": False, "category": "question", "sentiment": "neutral", "sources": [1, 99, "x"]})
        with patch:
            r = self.c.post("/api/ai/playground/", {"message": "delivery charge?"}, format="json")
        self.assertEqual([s["title"] for s in r.data["sources"]], ["Delivery"])  # bad numbers ignored
