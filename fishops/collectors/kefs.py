"""
Kenya Fisheries Service (KEFS) public-web collector.

Attempts to collect hatchery and aquaculture establishment information
from KEFS public FAQ and register pages.

IMPORTANT:
- This adapter fetches only publicly visible HTML pages.
- It records source URLs for every candidate.
- No login bypass, no form submission, no anti-bot interaction.
- If KEFS requires a login or returns a CAPTCHA, the adapter stops and
  sets status="blocked" on the run record.
"""

from __future__ import annotations

import re
from typing import Any

from fishops.collectors.base import BaseCollector, CandidateRecord
from fishops.normalization import clean_text, extract_emails, extract_phones

KEFS_PAGES: list[dict[str, str]] = [
    {
        "url": "https://kefs.go.ke/faqs",
        "source_name": "KEFS – FAQs",
        "hint": "hatchery",
    },
    {
        "url": "https://kefs.go.ke/node/135",
        "source_name": "KEFS – Genetic & Breeding / Hatchery Register",
        "hint": "hatchery",
    },
]

_LIKELY_TABLE_HEADERS = re.compile(
    r"(hatchery|establishment|farm|owner|contact|county|species|registration|name)",
    re.IGNORECASE,
)


def _is_data_cell(text: str) -> bool:
    """Reject empty, header-like, or very long cells."""
    return bool(text) and 2 < len(text) < 200


class KEFSCollector(BaseCollector):
    """
    Collect publicly visible aquaculture business candidates from KEFS pages.

    The site may paginate results or require JavaScript for some sections.
    This adapter records what it can reach statically.  Rows that cannot be
    parsed are skipped rather than guessed.
    """

    adapter_name = "kefs_ke"
    source_name = "Kenya Fisheries Service"

    def collect(self, **_kwargs: Any) -> list[CandidateRecord]:
        all_records: list[CandidateRecord] = []
        for page_config in KEFS_PAGES:
            records = self._collect_page(page_config)
            all_records.extend(records)
            if page_config is not KEFS_PAGES[-1]:
                self.sleep_politely()
        return all_records

    def _collect_page(self, page_config: dict[str, str]) -> list[CandidateRecord]:
        url = page_config["url"]
        source_name = page_config["source_name"]
        hint = page_config.get("hint", "hatchery")
        print(f"[KEFS] Collecting: {url}")

        try:
            soup = self.fetch_html(url)
        except PermissionError as exc:
            print(f"  Blocked by robots.txt: {exc}")
            return []
        except Exception as exc:
            print(f"  Fetch failed ({type(exc).__name__}): {exc}")
            return []

        records: list[CandidateRecord] = []

        # Strategy 1: look for HTML tables that likely list businesses
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            header_row = rows[0]
            header_text = clean_text(header_row.get_text(" ", strip=True))
            if not _LIKELY_TABLE_HEADERS.search(header_text):
                continue

            # Map column positions from header
            headers = [clean_text(th.get_text(" ", strip=True)).lower() for th in header_row.find_all(["th", "td"])]

            for data_row in rows[1:]:
                cells = [clean_text(td.get_text(" ", strip=True)) for td in data_row.find_all(["td", "th"])]
                if not cells or all(not c for c in cells):
                    continue

                row_dict: dict[str, str] = {}
                for i, header in enumerate(headers):
                    if i < len(cells) and _is_data_cell(cells[i]):
                        row_dict[header] = cells[i]

                # Attempt to match well-known columns
                name = (
                    row_dict.get("hatchery name")
                    or row_dict.get("hatchery")
                    or row_dict.get("establishment")
                    or row_dict.get("business name")
                    or row_dict.get("farm name")
                    or row_dict.get("name")
                    or (cells[0] if cells else "")
                )
                name = clean_text(name)
                if not name or len(name) < 3:
                    continue

                county = row_dict.get("county") or row_dict.get("location") or ""
                raw_contact = (
                    row_dict.get("contact")
                    or row_dict.get("phone")
                    or row_dict.get("telephone")
                    or row_dict.get("mobile")
                    or ""
                )
                email_field = row_dict.get("email") or row_dict.get("e-mail") or ""
                owner_field = row_dict.get("owner") or row_dict.get("manager") or row_dict.get("director") or ""
                species_field = row_dict.get("species") or row_dict.get("fish species") or ""
                reg_field = row_dict.get("registration") or row_dict.get("reg. no") or row_dict.get("registration number") or ""

                phones = extract_phones(raw_contact or " ".join(cells))
                phone_raw, phone_norm = phones[0] if phones else ("", "")
                emails = extract_emails(email_field or " ".join(cells))
                email = emails[0] if emails else ""

                raw_text_parts = [f"{k}: {v}" for k, v in row_dict.items() if v]
                raw_text = " | ".join(raw_text_parts)

                record = CandidateRecord(
                    business_name=name,
                    source_name=source_name,
                    adapter_name=self.adapter_name,
                    source_url=url,
                    country_code="KE",
                    phone_raw=phone_raw,
                    phone_normalized=phone_norm,
                    email_raw=email,
                    county_inferred=county,
                    location_text_raw=county,
                    business_type_hint=hint,
                    raw_text=raw_text,
                    raw_payload={
                        "row_dict": row_dict,
                        "owner": owner_field,
                        "species": species_field,
                        "registration_number": reg_field,
                    },
                )
                record.finalize()
                records.append(record)

        # Strategy 2: look for definition list or paragraph-style listings
        if not records:
            for heading in soup.find_all(["h3", "h4", "strong"]):
                text = clean_text(heading.get_text(" ", strip=True))
                if not text or len(text) < 4 or len(text) > 160:
                    continue
                parent = heading.parent
                if parent is None:
                    continue
                parent_text = clean_text(parent.get_text(" | ", strip=True))
                if len(parent_text) > 2000:
                    continue
                phones = extract_phones(parent_text)
                phone_raw, phone_norm = phones[0] if phones else ("", "")
                if not phone_raw and not text[0].isupper():
                    continue

                record = CandidateRecord(
                    business_name=text,
                    source_name=source_name,
                    adapter_name=self.adapter_name,
                    source_url=url,
                    country_code="KE",
                    phone_raw=phone_raw,
                    phone_normalized=phone_norm,
                    business_type_hint=hint,
                    location_text_raw=parent_text,
                    raw_text=parent_text,
                )
                record.finalize()
                records.append(record)

        print(f"  Candidates found: {len(records)}")
        return records
