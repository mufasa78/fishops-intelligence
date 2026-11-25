"""
Wikidata SPARQL adapter for Kenya aquaculture businesses.

Uses the public Wikidata Query Service (no API key required, 1-minute timeout).
Conservative query: returns only items explicitly typed as aquaculture facilities
or fish farms and located in Kenya.

Wikidata data is licensed CC0.  Wikidata SPARQL TOS:
https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/API
"""

from __future__ import annotations

import json
from typing import Any

import requests

from fishops.collectors.base import BaseCollector, CandidateRecord
from fishops.normalization import clean_text

SPARQL_URL = "https://query.wikidata.org/sparql"

SPARQL_QUERY = """
SELECT DISTINCT
  ?item ?itemLabel ?itemDescription
  ?countryLabel ?adminLabel
  ?phone ?email ?website
  ?osm_id
  ?instance_label
WHERE {
  VALUES ?fish_types {
    wd:Q188610     # aquaculture
    wd:Q22661306   # fish farm
    wd:Q51415      # hatchery
    wd:Q7978738    # tilapia farm
  }
  ?item wdt:P31/wdt:P279* ?fish_types .
  ?item wdt:P17 wd:Q114 .   # Kenya

  OPTIONAL { ?item wdt:P131 ?admin . }
  OPTIONAL { ?item wdt:P1329 ?phone . }
  OPTIONAL { ?item wdt:P968  ?email . }
  OPTIONAL { ?item wdt:P856  ?website . }
  OPTIONAL { ?item wdt:P402  ?osm_id . }
  OPTIONAL { ?item wdt:P31   ?instance . BIND(REPLACE(STR(?instance),".*Q","Q") AS ?instance_id) }

  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en,sw,fr" .
    ?item rdfs:label ?itemLabel .
    ?item schema:description ?itemDescription .
    ?admin rdfs:label ?adminLabel .
    ?instance rdfs:label ?instance_label .
  }
}
LIMIT 500
"""


class WikidataCollector(BaseCollector):
    """Collect structured aquaculture business data from Wikidata."""

    adapter_name = "wikidata"
    source_name = "Wikidata SPARQL"

    def collect(self, **_kwargs: Any) -> list[CandidateRecord]:
        print("[Wikidata] Running SPARQL query for Kenya aquaculture …")

        try:
            response = self.session.get(
                SPARQL_URL,
                params={"query": SPARQL_QUERY, "format": "json"},
                headers={**self.headers, "Accept": "application/sparql-results+json"},
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

        bindings = data.get("results", {}).get("bindings", [])
        print(f"  Rows returned: {len(bindings)}")

        records = [self._binding_to_record(row) for row in bindings]
        records = [r for r in records if r is not None]
        print(f"  Candidates with names: {len(records)}")
        return records  # type: ignore[return-value]

    def _binding_to_record(self, row: dict[str, Any]) -> CandidateRecord | None:
        def val(key: str) -> str:
            return clean_text(row.get(key, {}).get("value", ""))

        name = val("itemLabel")
        item_uri = val("item")
        if not name or name.startswith("Q") and name[1:].isdigit():
            return None

        qid = item_uri.rsplit("/", 1)[-1] if "/" in item_uri else item_uri
        source_url = f"https://www.wikidata.org/wiki/{qid}"
        county = val("adminLabel")
        phone_raw = val("phone")
        email_raw = val("email")
        website_raw = val("website")
        instance_label = val("instance_label")
        description = val("itemDescription")

        raw_payload = {
            "qid": qid,
            "description": description,
            "admin_label": county,
            "phone": phone_raw,
            "email": email_raw,
            "website": website_raw,
            "instance_label": instance_label,
        }

        record = CandidateRecord(
            business_name=name,
            source_name=self.source_name,
            adapter_name=self.adapter_name,
            source_url=source_url,
            external_id=qid,
            phone_raw=phone_raw,
            email_raw=email_raw,
            website_raw=website_raw,
            county_inferred=county,
            location_text_raw=county,
            country_code="KE",
            business_type_hint="fish_farm",
            raw_text=" | ".join(f"{k}={v}" for k, v in raw_payload.items() if v),
            raw_payload=raw_payload,
        )
        record.finalize()
        return record
