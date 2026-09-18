"""
scraper.py
----------
Rule-based fact extraction for immigration-consultancy websites.

This module NEVER makes judgment calls (that's the LLM's job in llm_judge.py).
It only answers yes/no/count questions that a script can answer reliably:
  - Does a contact form exist?
  - Are there CTA buttons, and what do they say?
  - Are social links present?
  - Is there an FAQ section?
  - What fraction of images have alt text?
  - Does the page declare a mobile viewport?
  - How long did the page take to load?
  - Is a phone number / email visible?

Design choices:
  - requests + BeautifulSoup (static HTML). Sites that are heavily JS-rendered
    (React/Vue SPAs with client-side routing) will under-report content --
    documented as a known limitation in README.md. Swap in Playwright if you
    need JS rendering.
  - Every network call is wrapped so one bad site can't crash the whole batch.
  - A shallow crawl (homepage + a few nav-linked internal pages) approximates
    "page count found" without hammering the site.
"""
import re
import time
import requests
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

USER_AGENT = "ImmigrationSiteAuditBot/1.0 (+educational audit tool; contact: you@example.com)"
REQUEST_TIMEOUT = 10  # seconds
MAX_CRAWL_PAGES = 5   # homepage + up to 4 internal pages found via nav

CTA_KEYWORDS = [
    "book", "consult", "consultation", "free assessment", "apply now",
    "get started", "contact us", "schedule", "request a call",
    "check eligibility", "start now", "enquire", "inquire", "get in touch",
    "whatsapp", "chat with us",
]

SOCIAL_DOMAINS = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "twitter.com": "twitter_x",
    "x.com": "twitter_x",
    "youtube.com": "youtube",
    "wa.me": "whatsapp",
    "whatsapp.com": "whatsapp",
    "tiktok.com": "tiktok",
}

PHONE_RE = re.compile(r"(\+?\d[\d\-\s\(\)]{7,}\d)")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


@dataclass
class SiteFacts:
    url: str
    reachable: bool = False
    error: Optional[str] = None

    http_status: Optional[int] = None
    https: bool = False
    load_time_ms: Optional[int] = None

    title: Optional[str] = None
    meta_description: Optional[str] = None
    has_meta_description: bool = False

    pages_crawled: int = 0
    nav_link_count: int = 0
    internal_link_count: int = 0

    contact_form_present: bool = False
    contact_form_fields: list = field(default_factory=list)
    mailto_link_present: bool = False
    phone_found: bool = False
    email_found: bool = False

    cta_buttons_found: list = field(default_factory=list)
    cta_count: int = 0

    social_links: dict = field(default_factory=dict)

    faq_present: bool = False

    images_total: int = 0
    images_with_alt: int = 0
    alt_text_coverage_pct: Optional[float] = None

    viewport_meta_present: bool = False  # basic mobile-responsiveness signal

    word_count: int = 0

    robots_txt_status: str = "unknown"  # "allowed" | "disallowed" | "unreadable"


def _safe_get(url, session):
    try:
        start = time.time()
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        elapsed_ms = int((time.time() - start) * 1000)
        return resp, elapsed_ms, None
    except requests.exceptions.Timeout:
        return None, None, "timeout"
    except requests.exceptions.SSLError:
        return None, None, "ssl_error"
    except requests.exceptions.ConnectionError:
        return None, None, "connection_error"
    except requests.exceptions.TooManyRedirects:
        return None, None, "too_many_redirects"
    except requests.exceptions.RequestException as e:
        return None, None, f"request_error:{type(e).__name__}"


def _extract_cta_buttons(soup):
    found = []
    for tag in soup.find_all(["a", "button"]):
        text = tag.get_text(strip=True)
        if not text or len(text) > 60:
            continue
        low = text.lower()
        if any(kw in low for kw in CTA_KEYWORDS):
            found.append(text)
    # de-dupe while preserving order
    seen = set()
    deduped = []
    for t in found:
        if t.lower() not in seen:
            seen.add(t.lower())
            deduped.append(t)
    return deduped


def _extract_social_links(soup):
    socials = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        netloc = urlparse(href).netloc.lower()
        for domain, platform in SOCIAL_DOMAINS.items():
            if domain in netloc:
                socials.setdefault(platform, href)
    return socials


def _extract_contact_form(soup):
    forms = soup.find_all("form")
    for form in forms:
        inputs = form.find_all(["input", "textarea", "select"])
        field_types = [i.get("type", i.name) for i in inputs]
        has_contact_signal = any(
            t in ("email", "tel", "textarea") for t in field_types
        )
        if has_contact_signal or len(inputs) >= 2:
            return True, field_types
    return False, []


def _extract_page_facts(html, base_url):
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_desc_tag["content"].strip() if meta_desc_tag and meta_desc_tag.get("content") else None

    viewport_tag = soup.find("meta", attrs={"name": "viewport"})
    viewport_present = viewport_tag is not None

    imgs = soup.find_all("img")
    images_total = len(imgs)
    images_with_alt = sum(1 for img in imgs if img.get("alt", "").strip())

    contact_form_present, contact_fields = _extract_contact_form(soup)
    mailto_present = bool(soup.find("a", href=re.compile(r"^mailto:", re.I)))

    body_text = soup.get_text(separator=" ", strip=True)
    phone_found = bool(PHONE_RE.search(body_text))
    email_found = bool(EMAIL_RE.search(body_text)) or mailto_present

    faq_present = bool(
        soup.find(string=re.compile(r"frequently asked|\bfaq\b", re.I))
    )

    cta_buttons = _extract_cta_buttons(soup)
    social_links = _extract_social_links(soup)

    word_count = len(body_text.split())

    # internal links for a shallow crawl
    internal_links = set()
    nav = soup.find("nav")
    nav_links = nav.find_all("a", href=True) if nav else []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        if urlparse(full).netloc == urlparse(base_url).netloc:
            internal_links.add(full.split("#")[0])

    return {
        "title": title,
        "meta_description": meta_description,
        "viewport_meta_present": viewport_present,
        "images_total": images_total,
        "images_with_alt": images_with_alt,
        "contact_form_present": contact_form_present,
        "contact_form_fields": contact_fields,
        "mailto_link_present": mailto_present,
        "phone_found": phone_found,
        "email_found": email_found,
        "faq_present": faq_present,
        "cta_buttons": cta_buttons,
        "social_links": social_links,
        "word_count": word_count,
        "internal_links": internal_links,
        "nav_link_count": len(nav_links),
    }


def audit_site(url: str, robots_status: str = "unknown", max_pages: int = MAX_CRAWL_PAGES) -> SiteFacts:
    """
    Fetches the homepage (+ a few internal pages found in nav) and returns
    a SiteFacts object. Never raises -- failures are captured in .error.
    """
    facts = SiteFacts(url=url, robots_txt_status=robots_status)
    facts.https = url.lower().startswith("https://")

    session = requests.Session()
    resp, elapsed_ms, err = _safe_get(url, session)

    if err:
        facts.reachable = False
        facts.error = err
        return facts

    facts.reachable = True
    facts.http_status = resp.status_code
    facts.load_time_ms = elapsed_ms

    if resp.status_code >= 400:
        facts.error = f"http_{resp.status_code}"
        return facts

    page_data = _extract_page_facts(resp.text, url)

    # aggregate homepage facts
    all_cta = list(page_data["cta_buttons"])
    all_social = dict(page_data["social_links"])
    total_images = page_data["images_total"]
    images_with_alt = page_data["images_with_alt"]
    total_words = page_data["word_count"]
    contact_form_present = page_data["contact_form_present"]
    contact_fields = page_data["contact_form_fields"]
    mailto_present = page_data["mailto_link_present"]
    phone_found = page_data["phone_found"]
    email_found = page_data["email_found"]
    faq_present = page_data["faq_present"]

    pages_crawled = 1
    to_visit = list(page_data["internal_links"])[: max_pages - 1]

    for link in to_visit:
        r2, _, err2 = _safe_get(link, session)
        if err2 or r2 is None or r2.status_code >= 400:
            continue
        sub = _extract_page_facts(r2.text, url)
        pages_crawled += 1
        all_cta.extend(sub["cta_buttons"])
        all_social.update(sub["social_links"])
        total_images += sub["images_total"]
        images_with_alt += sub["images_with_alt"]
        total_words += sub["word_count"]
        contact_form_present = contact_form_present or sub["contact_form_present"]
        if sub["contact_form_fields"]:
            contact_fields = contact_fields or sub["contact_form_fields"]
        mailto_present = mailto_present or sub["mailto_link_present"]
        phone_found = phone_found or sub["phone_found"]
        email_found = email_found or sub["email_found"]
        faq_present = faq_present or sub["faq_present"]
        time.sleep(0.5)  # be polite between requests

    facts.title = page_data["title"]
    facts.meta_description = page_data["meta_description"]
    facts.has_meta_description = bool(page_data["meta_description"])
    facts.pages_crawled = pages_crawled
    facts.nav_link_count = page_data["nav_link_count"]
    facts.internal_link_count = len(page_data["internal_links"])
    facts.contact_form_present = contact_form_present
    facts.contact_form_fields = contact_fields
    facts.mailto_link_present = mailto_present
    facts.phone_found = phone_found
    facts.email_found = email_found
    facts.cta_buttons_found = list(dict.fromkeys(all_cta))  # de-dupe, keep order
    facts.cta_count = len(facts.cta_buttons_found)
    facts.social_links = all_social
    facts.faq_present = faq_present
    facts.images_total = total_images
    facts.images_with_alt = images_with_alt
    facts.alt_text_coverage_pct = (
        round(100 * images_with_alt / total_images, 1) if total_images else None
    )
    facts.viewport_meta_present = page_data["viewport_meta_present"]
    facts.word_count = total_words

    return facts
