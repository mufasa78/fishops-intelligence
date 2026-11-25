"""
OpenStreetMap Overpass API adapter.

Queries the public Overpass API for aquaculture-related nodes and areas
in Kenya without authentication, scraping, or violating Terms of Service.

The Overpass API documentation explicitly states the data is freely
available.  We use a conservative query and a mandatory 2-second delay.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from fishops.collectors.base import BaseCollector, CandidateRecord
from fishops.normalization import clean_text

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OVERPASS_QUERY = """
[out:json][timeout:60];
area["ISO3166-1"="KE"][admin_level=2]->.kenya;
(
  node["landuse"="aquaculture"](area.kenya);
  way["landuse"="aquaculture"](area.kenya);
  relation["landuse"="aquaculture"](area.kenya);
  node["amenity"="fish_farm"](area.kenya);
  way["amenity"="fish_farm"](area.kenya);
  node["farm"="fish"](area.kenya);
  node["fishery"](area.kenya);
  way["fishery"](area.kenya);
);
out center meta;
"""

_TAG_INTEREST: tuple[str, ...] = (
    "name",
    "name:en",
    "operator",
    "contact:phone",
    "phone",
    "contact:email",
    "email",
    "website",
    "contact:website",
    "addr:county",
    "addr:city",
    "addr:town",
    "addr:village",
    "description",
    "species",
    "note",
)


class OSMOverpassCollector(BaseCollector):
    """Collect mapped aquaculture facilities in Kenya from OpenStreetMap Overpass API."""

    adapter_name = "osm_overpass_ke"
    source_name = "OpenStreetMap Overpass API"

    def collect(self, **_kwargs: Any) -> list[CandidateRecord]:
        print("[OSM Overpass] Querying Kenya aquaculture features …")

        try:
            response = self.session.post(
                OVERPASS_URL,
                data={"data": OVERPASS_QUERY},
                headers={**self.headers, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=90,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            print(f"  Network error: {exc}")
            return []
        except json.JSONDecodeError as exc:
            print(f"  JSON parse error: {exc}")
            return []

        elements = data.get("elements", [])
        print(f"  Raw elements returned: {len(elements)}")

        records = [self._element_to_record(el) for el in elements]
        records = [r for r in records if r is not None]
        print(f"  Named candidates: {len(records)}")
        return records  # type: ignore[return-value]

    def _element_to_record(self, element: dict[str, Any]) -> CandidateRecord | None:
        tags = element.get("tags", {})
        name = clean_text(
            tags.get("name") or tags.get("name:en") or tags.get("operator") or ""
        )
        if not name:
            return None

        lat = element.get("lat") or (element.get("center") or {}).get("lat")
        lon = element.get("lon") or (element.get("center") or {}).get("lon")

        phone_raw = clean_text(tags.get("contact:phone") or tags.get("phone") or "")
        email_raw = clean_text(tags.get("contact:email") or tags.get("email") or "")
        website_raw = clean_text(tags.get("website") or tags.get("contact:website") or "")
        county = clean_text(tags.get("addr:county") or "")
        location_text = " ".join(
            filter(
                None,
                [
                    tags.get("addr:county"),
                    tags.get("addr:city"),
                    tags.get("addr:town"),
                    tags.get("addr:village"),
                ],
            )
        )

        osm_type = element.get("type", "node")
        osm_id = element.get("id", "")
        source_url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"

        raw_payload = {k: v for k, v in tags.items() if k in _TAG_INTEREST}

        record = CandidateRecord(
            business_name=name,
            source_name=self.source_name,
            adapter_name=self.adapter_name,
            source_url=source_url,
            external_id=f"{osm_type}/{osm_id}",
            phone_raw=phone_raw,
            email_raw=email_raw,
            website_raw=website_raw,
            county_inferred=county,
            location_text_raw=location_text,
            latitude=lat,
            longitude=lon,
            business_type_hint="fish_farm",
            raw_payload=raw_payload,
            raw_text=" | ".join(f"{k}={v}" for k, v in raw_payload.items()),
        )
        record.finalize()
        return record
