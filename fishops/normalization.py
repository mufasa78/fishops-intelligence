"""Text, phone, location, and value-chain classification helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from fishops.constants import KENYA_COUNTIES, KENYA_TOWN_TO_COUNTY

PHONE_EXTRACT_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
EMAIL_EXTRACT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_LEGAL_SUFFIX_RE = re.compile(
    r"\b(limited|ltd|llc|inc|incorporated|plc|co\.?|company|enterprises?|"
    r"ventures?|group|holdings?|services?|kenya)\b",
    re.IGNORECASE,
)

# Ordered from more specific value-chain roles to broader farm terms.
_BUSINESS_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("hatchery", ("hatchery", "hatcheries", "fingerling", "fry", "broodstock", "seed production")),
    ("feed_manufacturer", ("fish feed", "aquafeed", "feed mill", "feeds", "pellet", "extruded feed")),
    ("processor", ("processing", "processor", "fillet", "cold storage", "smoked fish", "value addition")),
    ("distributor", ("distributor", "wholesale", "exporter", "importer", "fish trader", "trading", "fishmonger", "supply")),
    ("input_supplier", ("cage", "liner", "pond liner", "aerator", "equipment", "netting", "water quality", "test kit", "inputs")),
    ("cooperative", ("cooperative", "co-op", "sacco", "cluster", "cbo", "self help", "bmu", "beach management")),
    ("research_training", ("university", "research", "institute", "kmfri", "training", "college", "academy")),
    ("regulator_association", ("ministry", "fisheries service", "kefs", "directorate", "association", "board", "authority")),
    ("fish_farm", ("fish farm", "aquaculture", "tilapia", "catfish", "trout", "ponds", "cages", "mariculture", "fisheries", "farm")),
)


@dataclass(frozen=True)
class ClassificationResult:
    """Heuristic business-type classification for human review."""

    business_type: str
    confidence: str
    matched_keywords: tuple[str, ...]


def clean_text(value: str | None) -> str:
    """Collapse repeated whitespace and strip ends."""
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_business_name(name: str | None) -> str:
    """Produce a comparison key for an organization name without mutating display text."""
    cleaned = clean_text(name).lower()
    cleaned = cleaned.replace("&", " and ")
    cleaned = _LEGAL_SUFFIX_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    return clean_text(cleaned)


def normalize_phone(raw_phone: str | None, country_code: str = "KE") -> str:
    """
    Normalize a phone number without altering the caller's raw value.

    For Kenya (KE), converts 07xxxxxxxx / 01xxxxxxxx / 254xxxxxxxxx / +254...
    and Kenyan landline prefixes (020, 041, 057, etc.) into +254... E.164 format.
    Returns "" when input has fewer than 7 digits.
    """
    raw = clean_text(raw_phone)
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7:
        return ""

    if country_code.upper() == "KE":
        if raw.startswith("+254") and len(digits) >= 12:
            return f"+{digits[:12]}"
        if digits.startswith("00254") and len(digits) >= 14:
            return f"+{digits[2:14]}"
        if digits.startswith("254") and len(digits) == 12:
            return f"+{digits}"
        if digits.startswith("0") and len(digits) in (9, 10):
            return f"+254{digits[1:]}"
        if digits.startswith(("7", "1")) and len(digits) == 9:
            return f"+254{digits}"
    if raw.startswith("+"):
        return f"+{digits}"
    return digits


def extract_phones(text: str | None, country_code: str = "KE") -> list[tuple[str, str]]:
    """Return deduplicated (raw, normalized) phone pairs found in text."""
    if not text:
        return []
    seen_norm: set[str] = set()
    results: list[tuple[str, str]] = []
    for match in PHONE_EXTRACT_RE.findall(text):
        raw = clean_text(match)
        norm = normalize_phone(raw, country_code=country_code)
        key = norm or re.sub(r"\D", "", raw)
        if not key or len(key) < 7 or key in seen_norm:
            continue
        seen_norm.add(key)
        results.append((raw, norm))
    return results


def normalize_email(raw_email: str | None) -> str:
    """Lowercase and trim an email address."""
    return clean_text(raw_email).lower()


def extract_emails(text: str | None) -> list[str]:
    """Extract deduplicated lowercase email addresses from raw text."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in EMAIL_EXTRACT_RE.findall(text):
        email = normalize_email(match)
        if email not in seen:
            seen.add(email)
            out.append(email)
    return out


def normalize_url(raw_url: str | None) -> str:
    """Normalize a website/profile URL for comparison."""
    cleaned = clean_text(raw_url)
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if not parsed.scheme:
        parsed = urlparse(f"https://{cleaned}")
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"{host}{path}" if host else cleaned.lower()


def infer_county(text: str | None, country_code: str = "KE") -> str:
    """
    Conservatively match a Kenyan county name or major town hint from raw text.
    Returns "" when no unambiguous match is found.
    """
    if not text or country_code.upper() != "KE":
        return ""
    lowered = f" {clean_text(text).lower()} "
    for county in KENYA_COUNTIES:
        pattern = rf"(?<![a-z]){re.escape(county.lower())}(?![a-z])"
        if re.search(pattern, lowered):
            return county
    for town, county in KENYA_TOWN_TO_COUNTY.items():
        pattern = rf"(?<![a-z]){re.escape(town)}(?![a-z])"
        if re.search(pattern, lowered):
            return county
    return ""


def classify_business_type(
    business_name: str | None,
    raw_text: str | None = "",
    hint: str | None = "",
) -> ClassificationResult:
    """
    Classify a candidate across the aquaculture value chain.

    This is an initial triage aid only; records stay unverified until reviewed.
    """
    haystack = " ".join(
        part for part in (business_name or "", hint or "", raw_text or "") if part
    ).lower()

    for btype, keywords in _BUSINESS_TYPE_RULES:
        matched = tuple(kw for kw in keywords if kw in haystack)
        if matched:
            confidence = "medium" if len(matched) >= 2 or (business_name and any(kw in business_name.lower() for kw in matched)) else "low"
            return ClassificationResult(
                business_type=btype,
                confidence=confidence,
                matched_keywords=matched,
            )

    return ClassificationResult(
        business_type="unknown",
        confidence="none",
        matched_keywords=(),
    )


def compute_candidate_fingerprint(
    business_name: str,
    phone_normalized: str = "",
    phone_raw: str = "",
    profile_url: str = "",
    county: str = "",
    country_code: str = "KE",
) -> str:
    """
    Compute a stable deduplication fingerprint from normalized identifiers.

    Unlike hashing raw page snippets, using normalized name + normalized phone
    (or normalized profile URL / county) collapses trivial formatting changes.
    """
    norm_name = normalize_business_name(business_name) or clean_text(business_name).lower()
    phone_key = phone_normalized or re.sub(r"\D", "", phone_raw)
    url_key = normalize_url(profile_url)
    location_key = clean_text(county).lower()
    parts = [country_code.upper(), norm_name, phone_key or url_key or location_key]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
