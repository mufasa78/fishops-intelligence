# Partner Contact Research — 2026-11-25

## Scope and handling

Checked the partner URLs supplied for this task, using publicly accessible
institutional pages only. No account login, credential use, or form submission
was attempted. Directly published institutional contact channels are included;
named staff-directory contacts and form placeholders are excluded. Imported
records are prospects for manual review: contact points remain unverified and
their lawful basis remains `unknown`.

## Publicly available contact channels

| Organization | Public contacts found | Public source |
| --- | --- | --- |
| Kenya Marine and Fisheries Research Institute (KMFRI) | `director@kmfri.go.ke`; `+254 20 8021561`; `+254 712 003 853` | [KMFRI contact page](https://www.kmfri.go.ke/contact-us) |
| National Trout Hatchery | `troutkiganjo@yahoo.com`; `020 2327236` | [National Trout Hatchery website](https://nationaltrouthatcheryke.wordpress.com/) |
| Lake Victoria Fisheries Organization (LVFO) | `lvfo-sec@lvfo.org`; `+256 434 125 000` (Secretariat, Jinja, Uganda) | [LVFO contact page](https://www.lvfo.org/content/contact-us) |
| Aquaculture Business Development Programme (ABDP) | Public contact form; no email address or phone number published on the accessible page. The form was not submitted. | [ABDP contact page](https://www.abdpcu.org/contact-us/) |

KMFRI's page also lists station coordinators' direct numbers. They were not
included in this import; only the institution's general office channels were
used.

## Not collected

| Partner/link supplied | Outcome |
| --- | --- |
| Ministry of Mining, Blue Economy and Maritime Affairs | Official URL could not be fetched because of a transport/TLS failure. No alternate or authenticated source used. |
| Kenya Marine Fisheries & Socio-economic Development (KEMFSED) | The public fetch service blocked the URL because it resolved to a loopback address. Not accessed. |
| Fish Levy Trust Fund | Official URL could not be fetched because of a transport/TLS failure. |
| Kenya Fishing Industries Corporation (KFIC) | Official URL could not be fetched because of a transport/TLS failure. |
| Kenya Fish Marketing Authority (KFMA) link supplied | The supplied URL points to the Kenya Fisheries Service (KEFS) aquaculture page. That host was not reachable through the available public fetch path; no data was collected. |
| Kenya Coast Guard Service | Official URL could not be fetched because of a transport/TLS failure. |

Fetch failures are not evidence that these sites require authentication. Their
contacts were simply left uncollected rather than bypassing access controls or
trust checks.

## CRM load

The four organizations with a public direct contact route were staged as
pending source records. Only values shown on the cited pages were added. Any
phone, email, or website contact point remains unverified; manual review is
required before use. The ABDP contact form is stored as a public website
contact point, not submitted.

Import verification for `Official partner public contact pages`:

- 4 organizations, 5 source records, and 11 contact points added.
- Contact points: 3 email, 4 phone, and 4 website/form routes.
- 1 collection run completed; 0 duplicate skips and 0 staging errors.
- All 5 source records are `pending`; all 11 contact points are
  `unverified` with `lawful_basis=unknown`.

The full Supabase `prospects` schema now contains 41 organizations, 0 people,
41 contact points, 42 source records, 2 collection runs, 0 verification
logs, and 0 suppression entries. All 41 organizations remain `discovered` and
`unverified`; all 42 source records remain pending review. The previous
GoAfrica records were left unchanged.
