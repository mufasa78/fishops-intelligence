"""Multi-source conservative prospect candidate collectors."""

from fishops.collectors.base import (
    BaseCollector,
    CandidateRecord,
    deduplicate_candidates,
    export_candidates_csv,
)
from fishops.collectors.csv_import import load_candidates_from_csv
from fishops.collectors.goafrica import GoAfricaCollector
from fishops.collectors.kefs import KEFSCollector
from fishops.collectors.osm_overpass import OSMOverpassCollector
from fishops.collectors.wikidata import WikidataCollector

__all__ = [
    "BaseCollector",
    "CandidateRecord",
    "GoAfricaCollector",
    "KEFSCollector",
    "OSMOverpassCollector",
    "WikidataCollector",
    "deduplicate_candidates",
    "export_candidates_csv",
    "load_candidates_from_csv",
]
