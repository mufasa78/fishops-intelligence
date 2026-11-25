"""Shared candidate record model, polite HTTP fetching, and CSV export."""

from __future__ import annotations

import csv
import json
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup

from fishops.config import get_settings
from fishops.normalization import (
    classify_business_type,
    clean_text,
    compute_candidate_fingerprint,
    extract_emails,
    extract_phones,
    infer_county,
)


@dataclass
class CandidateRecord:
    """Unverified raw prospect candidate emitted by any collector adapter."""

    business_name: str
    source_name: str
    adapter_name: str
    source_url: str
    country_code: str = "KE"
    phone_raw: str = ""
    phone_normalized: str = ""
    email_raw: str = ""
    website_raw: str = ""
    profile_url: str = ""
    external_id: str = ""
    county_inferred: str = ""
    location_text_raw: str = ""
    latitude: float | None = None
    longitude: float | None = None
    business_type_hint: str = "unknown"
    classification_confidence: str = "none"
    raw_text: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verification_status: str = "unverified"
    review_required: bool = True
    fingerprint: str = ""

    def finalize(self) -> CandidateRecord:
        """Populate derived normalization hints without mutating raw fields."""
        self.business_name = clean_text(self.business_name)
        self.raw_text = clean_text(self.raw_text)
        self.location_text_raw = clean_text(self.location_text_raw)

        if not self.phone_raw and self.raw_text:
            phones = extract_phones(self.raw_text, country_code=self.country_code)
            if phones:
                self.phone_raw, self.phone_normalized = phones[0]
        elif self.phone_raw and not self.phone_normalized:
            phones = extract_phones(self.phone_raw, country_code=self.country_code)
            if phones:
                self.phone_normalized = phones[0][1]

        if not self.email_raw and self.raw_text:
            emails = extract_emails(self.raw_text)
            if emails:
                self.email_raw = emails[0]

        if not self.county_inferred:
            self.county_inferred = infer_county(
                f"{self.location_text_raw} {self.raw_text}", country_code=self.country_code
            )

        if self.business_type_hint in ("", "unknown"):
            result = classify_business_type(
                self.business_name, raw_text=self.raw_text, hint=self.location_text_raw
            )
            self.business_type_hint = result.business_type
            self.classification_confidence = result.confidence

        if not self.fingerprint:
            self.fingerprint = compute_candidate_fingerprint(
                business_name=self.business_name,
                phone_normalized=self.phone_normalized,
                phone_raw=self.phone_raw,
                profile_url=self.profile_url or self.website_raw,
                county=self.county_inferred,
                country_code=self.country_code,
            )
        return self

    def to_flat_dict(self) -> dict[str, Any]:
        """Serialize to a CSV-friendly flat dictionary."""
        self.finalize()
        data = asdict(self)
        payload = data.pop("raw_payload", {})
        data["raw_payload_json"] = json.dumps(payload, ensure_ascii=False)
        return data


class BaseCollector(ABC):
    """Base class for conservative, provenance-preserving collectors."""

    adapter_name: str = "base"
    source_name: str = "Unknown"

    def __init__(
        self,
        delay: float = 3.0,
        timeout: int | None = None,
        respect_robots: bool = True,
        session: requests.Session | None = None,
    ) -> None:
        settings = get_settings()
        self.delay = max(delay, settings.min_request_delay_seconds)
        self.timeout = timeout or settings.request_timeout_seconds
        self.respect_robots = respect_robots
        self.headers = {"User-Agent": settings.user_agent}
        self.session = session or requests.Session()
        self._robots_cache: dict[str, RobotFileParser | None] = {}

    def is_allowed_by_robots(self, url: str) -> bool:
        """Check robots.txt for the target origin; fail open on unreachable robots.txt."""
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots_cache:
            robots_url = f"{origin}/robots.txt"
            parser = RobotFileParser()
            try:
                resp = self.session.get(robots_url, headers=self.headers, timeout=min(self.timeout, 10))
                if resp.status_code == 200 and resp.text:
                    parser.parse(resp.text.splitlines())
                    self._robots_cache[origin] = parser
                else:
                    self._robots_cache[origin] = None
            except requests.RequestException:
                self._robots_cache[origin] = None
        cached = self._robots_cache[origin]
        if cached is None:
            return True
        return cached.can_fetch(self.headers["User-Agent"], url)

    def fetch_text(self, url: str, expected_types: tuple[str, ...] = ("text/html", "application/xhtml+xml")) -> str:
        """Fetch a public URL while enforcing robots.txt and content-type checks."""
        if not self.is_allowed_by_robots(url):
            raise PermissionError(f"Blocked by robots.txt: {url}")
        response = self.session.get(url, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if expected_types and content_type and not any(ct in content_type for ct in expected_types):
            raise ValueError(f"Unexpected content type '{content_type}' at {url}")
        return response.text

    def fetch_html(self, url: str) -> BeautifulSoup:
        """Fetch and parse an HTML page."""
        return BeautifulSoup(self.fetch_text(url), "lxml")

    def sleep_politely(self) -> None:
        """Pause between consecutive network requests."""
        time.sleep(self.delay)

    @abstractmethod
    def collect(self, **kwargs: Any) -> list[CandidateRecord]:
        """Collect unverified candidate records from this source."""


def deduplicate_candidates(records: list[CandidateRecord]) -> list[CandidateRecord]:
    """Deduplicate candidate records by normalized fingerprint while keeping first-seen order."""
    unique: dict[str, CandidateRecord] = {}
    for record in records:
        record.finalize()
        if not record.business_name:
            continue
        if record.fingerprint not in unique:
            unique[record.fingerprint] = record
    return list(unique.values())


def export_candidates_csv(records: list[CandidateRecord], output_path: Path) -> Path:
    """Export candidate records to a UTF-8 BOM CSV for spreadsheet review."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [record.to_flat_dict() for record in records]
    df = pd.DataFrame(rows)
    if df.empty:
        columns = list(CandidateRecord(business_name="", source_name="", adapter_name="", source_url="").to_flat_dict().keys())
        df = pd.DataFrame(columns=columns)
    df.to_csv(output_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    return output_path
