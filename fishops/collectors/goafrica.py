"""
Go Africa Online – Kenya Aquaculture & Fish Farming directory adapter.

Collects publicly visible business listing candidates.
Respects robots.txt, enforces polite delays, and exports unverified records only.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from fishops.collectors.base import BaseCollector, CandidateRecord
from fishops.normalization import clean_text

START_URL = "https://www.goafricaonline.com/ke/directory/aquaculture-fish-farming"

_SKIP_HEADINGS: frozenset[str] = frozenset(
    {
        "profile",
        "directions",
        "aquaculture and fish farming in kenya",
        "most viewed companies",
        "featured companies",
        "login",
        "register",
        "search",
        "select your country",
        "choose your country",
    }
)

_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")


def _find_listing_container(heading: Any, max_ancestor_steps: int = 7) -> Any:
    """
    Walk up the DOM from a heading and return the first ancestor that is both
    compact (<2 500 chars) and contains a likely phone pattern.
    Returns the heading's parent when no such ancestor exists.
    """
    current = heading
    for _ in range(max_ancestor_steps):
        parent = current.parent
        if parent is None:
            break
        text = clean_text(parent.get_text(" ", strip=True))
        if 30 < len(text) < 2500 and _PHONE_RE.search(text):
            return parent
        current = parent
    return heading.parent or heading


def _extract_next_page_url(soup: Any, current_url: str) -> str | None:
    """Find a pagination 'next' link."""
    link = soup.find("a", rel=lambda v: isinstance(v, list) and "next" in v)
    if not link:
        for a in soup.find_all("a", href=True):
            label = clean_text(a.get_text(" ", strip=True)).lower()
            if label in {"next", "next →", "next »", "›", "»"}:
                link = a
                break
    if link and link.get("href"):
        return urljoin(current_url, link["href"])
    return None


class GoAfricaCollector(BaseCollector):
    """
    Adapter for the Go Africa Online Kenya aquaculture directory.

    The site shows ~52 results.  Business-type classification is applied
    heuristically; every record is marked ``unverified`` until reviewed.
    """

    adapter_name = "goafrica_ke"
    source_name = "Go Africa Online"

    def collect(self, max_pages: int = 5, **_kwargs: Any) -> list[CandidateRecord]:
        visited: set[str] = set()
        records: list[CandidateRecord] = []
        current_url: str | None = START_URL

        for page_number in range(1, max(max_pages, 1) + 1):
            if not current_url or current_url in visited:
                break
            visited.add(current_url)
            print(f"[GoAfrica {page_number}/{max_pages}] {current_url}")

            try:
                soup = self.fetch_html(current_url)
            except PermissionError as exc:
                print(f"  Blocked: {exc}")
                break
            except Exception as exc:
                print(f"  Fetch error: {exc}")
                break

            page_records = self._extract_records(soup, current_url)
            records.extend(page_records)
            print(f"  Found {len(page_records)} candidate(s).")
            current_url = _extract_next_page_url(soup, current_url)

            if current_url and page_number < max_pages:
                self.sleep_politely()

        return records

    def _extract_records(self, soup: Any, page_url: str) -> list[CandidateRecord]:
        results: list[CandidateRecord] = []

        for heading in soup.find_all(["h2", "h3", "h4"]):
            name = clean_text(heading.get_text(" ", strip=True))
            if not name or name.lower() in _SKIP_HEADINGS or len(name) > 160:
                continue

            container = _find_listing_container(heading)
            raw_text = clean_text(container.get_text(" | ", strip=True))

            if not raw_text or len(raw_text) > 2500:
                continue

            anchor = heading.find("a", href=True)
            profile_url = urljoin(page_url, anchor["href"]) if anchor else ""

            phones = _PHONE_RE.findall(raw_text)
            phone_raw = clean_text(phones[0]) if phones else ""

            record = CandidateRecord(
                business_name=name,
                source_name=self.source_name,
                adapter_name=self.adapter_name,
                source_url=page_url,
                profile_url=profile_url,
                phone_raw=phone_raw,
                location_text_raw=raw_text,
                raw_text=raw_text,
            )
            record.finalize()
            results.append(record)

        return results
