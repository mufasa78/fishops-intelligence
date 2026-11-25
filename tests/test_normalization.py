"""Tests for normalization utilities."""

from __future__ import annotations

import pytest
from fishops.auth import get_authorized_administrator
from fishops.normalization import (
    classify_business_type,
    clean_text,
    compute_candidate_fingerprint,
    extract_emails,
    extract_phones,
    infer_county,
    normalize_business_name,
    normalize_email,
    normalize_phone,
    normalize_url,
)


class TestCleanText:
    def test_collapses_whitespace(self):
        assert clean_text("  hello   world  ") == "hello world"

    def test_handles_none(self):
        assert clean_text(None) == ""

    def test_handles_empty(self):
        assert clean_text("") == ""


class TestNormalizePhone:
    def test_kenyan_07(self):
        assert normalize_phone("0712 345678", "KE") == "+254712345678"

    def test_kenyan_plus254(self):
        assert normalize_phone("+254 712 345 678", "KE") == "+254712345678"

    def test_kenyan_254_prefix(self):
        assert normalize_phone("254712345678", "KE") == "+254712345678"

    def test_kenyan_leading_7(self):
        assert normalize_phone("712345678", "KE") == "+254712345678"

    def test_too_short(self):
        assert normalize_phone("1234", "KE") == ""

    def test_empty(self):
        assert normalize_phone("", "KE") == ""


class TestExtractPhones:
    def test_extracts_kenyan_number(self):
        pairs = extract_phones("Call us on 0712 345 678 today", country_code="KE")
        assert len(pairs) == 1
        raw, norm = pairs[0]
        assert norm == "+254712345678"

    def test_deduplicates(self):
        pairs = extract_phones("0712345678 / 0712345678", country_code="KE")
        assert len(pairs) == 1

    def test_no_numbers(self):
        assert extract_phones("No numbers here", country_code="KE") == []


class TestExtractEmails:
    def test_extracts_email(self):
        emails = extract_emails("Contact: info@example.co.ke or hello@fishops.com")
        assert emails == ["info@example.co.ke", "hello@fishops.com"]

    def test_deduplicates(self):
        emails = extract_emails("info@example.com and INFO@EXAMPLE.COM")
        assert len(emails) == 1


class TestNormalizeBusinessName:
    def test_strips_ltd(self):
        key = normalize_business_name("Sagana Fish Farm Limited")
        assert "limited" not in key
        assert "sagana" in key
        assert "fish farm" in key

    def test_handles_ampersand(self):
        key = normalize_business_name("Fish & Feed Kenya")
        assert "and" in key
        assert "&" not in key

    def test_handles_none(self):
        result = normalize_business_name(None)
        assert result == ""


class TestNormalizeEmail:
    def test_lowercases(self):
        assert normalize_email("HELLO@Example.CO.KE") == "hello@example.co.ke"


class TestAdministratorAuthorization:
    def test_authorizes_configured_email_case_insensitively(self, monkeypatch):
        monkeypatch.setenv("FISHOPS_ADMIN_EMAIL_1", "mburutracy81@gmail.com")
        monkeypatch.delenv("FISHOPS_ADMIN_EMAIL_2", raising=False)

        administrator = get_authorized_administrator("  MBURUTRACY81@GMAIL.COM ")

        assert administrator is not None
        assert administrator.name == "Tracy Wambui Mburu"

    def test_denies_email_not_in_allowlist(self, monkeypatch):
        monkeypatch.setenv("FISHOPS_ADMIN_EMAIL_1", "mburutracy81@gmail.com")
        monkeypatch.setenv("FISHOPS_ADMIN_EMAIL_2", "njorogestan12@gmail.com")

        assert get_authorized_administrator("someone@example.com") is None

    def test_authorizes_stanley_by_email(self, monkeypatch):
        monkeypatch.setenv("FISHOPS_ADMIN_EMAIL_1", "mburutracy81@gmail.com")
        monkeypatch.setenv("FISHOPS_ADMIN_EMAIL_2", "njorogestan12@gmail.com")

        administrator = get_authorized_administrator("njorogestan12@gmail.com")

        assert administrator is not None
        assert administrator.name == "Stanley Gathekia"


class TestNormalizeUrl:
    def test_strips_www(self):
        assert "www." not in normalize_url("https://www.example.co.ke/about/")

    def test_strips_trailing_slash(self):
        assert normalize_url("https://example.co.ke/") == "example.co.ke"


class TestInferCounty:
    def test_exact_county(self):
        assert infer_county("Located in Kisumu county, Kenya") == "Kisumu"

    def test_town_to_county(self):
        assert infer_county("Located in Sagana, Central Kenya") == "Kirinyaga"

    def test_no_match(self):
        assert infer_county("Somewhere unspecified") == ""

    def test_non_ke(self):
        assert infer_county("Kisumu, Kenya", country_code="TZ") == ""


class TestClassifyBusinessType:
    def test_hatchery(self):
        result = classify_business_type("Sagana Fish Hatchery")
        assert result.business_type == "hatchery"

    def test_feed(self):
        result = classify_business_type("AquaFeed Mills Kenya")
        assert result.business_type == "feed_manufacturer"

    def test_processor(self):
        result = classify_business_type("Lake Victoria Fish Processing Ltd")
        assert result.business_type == "processor"

    def test_fish_farm_fallback(self):
        result = classify_business_type("Tilapia farm, Kisumu")
        assert result.business_type == "fish_farm"

    def test_unknown(self):
        result = classify_business_type("Random Business 123")
        assert result.business_type == "unknown"


class TestFingerprintStability:
    def test_same_name_and_phone(self):
        fp1 = compute_candidate_fingerprint("Sagana Farm", phone_normalized="+254712345678")
        fp2 = compute_candidate_fingerprint("Sagana Farm", phone_normalized="+254712345678")
        assert fp1 == fp2

    def test_different_name(self):
        fp1 = compute_candidate_fingerprint("Farm A", phone_normalized="+254712345678")
        fp2 = compute_candidate_fingerprint("Farm B", phone_normalized="+254712345678")
        assert fp1 != fp2
