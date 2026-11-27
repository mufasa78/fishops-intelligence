"""Tests for the public BusinessList fish-merchants collector."""

from bs4 import BeautifulSoup

from fishops.collectors.businesslist import (
    LIST_URL,
    BusinessListFishMerchantsCollector,
)


def test_collector_extracts_only_visible_listing_fields(monkeypatch):
    html = """
    <div class="company g_0" data-cmpid="84564">
      <div class="company_header">
        <h3><a href="/company/84564/fish-way">FISH-WAY</a></h3>
        <div class="address">Kisauni Rd, <b>Mombasa</b>, Kenya</div>
      </div>
      <div class="s">
        <i aria-label="Phone number"></i><span><b>(254) 41 - 2495975</b></span>
      </div>
    </div>
    <div class="company company_ad"><a href="/saas">Plans</a></div>
    """
    collector = BusinessListFishMerchantsCollector()
    fetched_urls: list[str] = []

    def fake_fetch_html(url: str) -> BeautifulSoup:
        fetched_urls.append(url)
        return BeautifulSoup(html, "lxml")

    monkeypatch.setattr(collector, "fetch_html", fake_fetch_html)

    [candidate] = collector.collect()

    assert fetched_urls == [LIST_URL]
    assert candidate.business_name == "FISH-WAY"
    assert candidate.external_id == "84564"
    assert candidate.profile_url == (
        "https://www.businesslist.co.ke/company/84564/fish-way"
    )
    assert candidate.phone_raw == "(254) 41 - 2495975"
    assert candidate.phone_normalized == "+254412495975"
    assert candidate.county_inferred == "Mombasa"
    assert candidate.source_url == LIST_URL
