"""Collector for the publicly visible BusinessList.co.ke fish-merchants page."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from fishops.collectors.base import BaseCollector, CandidateRecord
from fishops.normalization import clean_text

LIST_URL = "https://www.businesslist.co.ke/companies/fish-merchants"


class BusinessListFishMerchantsCollector(BaseCollector):
    """Collect visible listing details only; never opens premium Data Hub content."""

    adapter_name = "businesslist_fish_merchants"
    source_name = "BusinessList.co.ke — Fish merchants"

    def collect(self, max_pages: int = 1, **_kwargs: Any) -> list[CandidateRecord]:
        del max_pages, _kwargs
        soup = self.fetch_html(LIST_URL)
        records: list[CandidateRecord] = []

        for listing in soup.select(".company[data-cmpid]"):
            heading_link = listing.select_one(".company_header h3 a[href]")
            if heading_link is None:
                continue

            name = clean_text(heading_link.get_text(" ", strip=True))
            if not name:
                continue

            address_node = listing.select_one(".company_header .address")
            address = (
                clean_text(address_node.get_text(" ", strip=True))
                if address_node is not None
                else ""
            )
            phone_node = listing.select_one('[aria-label="Phone number"]')
            phone_container = (
                phone_node.find_parent(class_="s") if phone_node is not None else None
            )
            phone = (
                clean_text(phone_container.get_text(" ", strip=True))
                if phone_container is not None
                else ""
            )

            record = CandidateRecord(
                business_name=name,
                source_name=self.source_name,
                adapter_name=self.adapter_name,
                source_url=LIST_URL,
                profile_url=urljoin(LIST_URL, str(heading_link["href"])),
                external_id=clean_text(listing.get("data-cmpid")),
                phone_raw=phone,
                address_raw=address,
                location_text_raw=address,
                raw_text=" | ".join(value for value in (name, address, phone) if value),
            )
            records.append(record.finalize())

        return records
