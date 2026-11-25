# Source Collection Report — 2026-11-25

## Outcome

The non-GoAfrica collection attempt did not produce candidates suitable for
review or database staging. No records or contacts from KEFS, OpenStreetMap,
or Wikidata were loaded. Collection was run in dry-run mode; the production
database was not written to during this attempt.

## Source results

| Source | Result | Candidate records |
| --- | --- | ---: |
| KEFS public pages (`/faqs`, `/node/135`) | Both requests failed TLS certificate-chain verification (`SSLCertVerificationError: unable to get local issuer certificate`). Certificate verification was not disabled. | 0 |
| OpenStreetMap Overpass (`overpass-api.de`) | HTTP 502 Bad Gateway. | 0 |
| OpenStreetMap Overpass (`overpass.kumi.systems`) | Alternate endpoint timed out; a narrower query also timed out. | 0 |
| Wikidata SPARQL | Query returned HTTP 200 with zero rows. | 0 |

No candidate CSV was generated for this attempt because the collector had no
records to export. The existing GoAfrica CSV exports were not changed.

## Production database baseline after the dry run

The read-only Supabase `prospects` schema audit returned:

| Table / measure | Count |
| --- | ---: |
| Organizations | 37 |
| People | 0 |
| Contact points | 30 |
| Source records | 37 |
| Collection runs | 1 |
| Verification logs | 0 |
| Suppression entries | 0 |

All 30 existing contact points are phone channels. All 37 source records are
from Go Africa Online and remain pending review. No new records, contacts, or
collection-run entries were written by the dry run.

## Follow-up

1. Retry KEFS once the machine's trusted CA configuration can validate the
   site's certificate chain; do not disable certificate checks.
2. Retry Overpass after its public endpoints recover, keeping requests
   bounded and respectful of service limits.
3. Wikidata currently has no matching rows for the configured conservative
   query; broaden its scope only after reviewing the query and expected data.
4. Run a dry run again and inspect candidate names, provenance, and explicit
   contact fields before staging.
5. After a successful stage, verify the run log, source-record counts, and
   contact-point counts in Supabase. All scraped contacts must remain
   unverified pending manual review.
