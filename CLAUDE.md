# iso20022

Interactive single-page encyclopedia of ISO 20022 payments messages. Live at
<https://nnavnita.com/iso20022/>.

Covers the payments core: `pain` (customer initiation), `pacs` (FI-to-FI
clearing), `camt` (cash management / reporting), `remt` (remittance) and
`head` (business application header). Four jobs: learn the format, look up
MT -> MX equivalents, search any field or code, and see how CBPR+, SEPA, NPP
and Fedwire restrict the base message.

## Stack

Zero dependencies. Python 3 stdlib for the build, vanilla JS + CSS for the UI.
No npm, no bundler, no framework.

## Build

```sh
python3 build.py          # data/ + src/index.html -> dist/index.html
python3 tests/test_data.py   # data integrity checks
open dist/index.html      # works over file://, no server needed
```

`build.py` hard-fails on malformed or incomplete data. `dist/index.html` is
**committed on purpose** — it is the deliverable, and CI re-runs the build and
fails if the committed output has drifted from `data/`.

## Layout

| Path | What |
|---|---|
| `data/messages/*.json` | one file per message definition |
| `data/codelists.json` | shared code sets, referenced by field, never inlined |
| `data/mt-mapping.json` | legacy SWIFT MT tag -> MX path pairs |
| `data/schemes.json` | per-scheme **overlays** (deltas only) on base ISO |
| `src/index.html` | UI; reads `window.ISO_DATA`, has an `<!--ISO_DATA-->` marker |
| `build.py` | validates, merges, inlines data into `dist/index.html` |
| `dist/index.html` | shippable self-contained page (what Pages serves) |

## Authoring data

Fields use **flat dotted paths** (`CdtTrfTxInf.Dbtr.Nm`), not nested objects.
The tree view is derived by splitting on `.` at render time. A path's parent
must also exist as its own field entry (that is where repetition like `[1..n]`
is recorded) — `tests/test_data.py` enforces this.

`tier` controls visibility and is the hook for a future XSD import:

- `1` core — you will touch this on day one
- `2` situational but real
- `3` completeness only (hidden unless "everything" is selected)

A generated dump of full XSD element lists should land as `tier: 3` so it adds
coverage without drowning the default view.

Schemes store **only deltas** from base ISO, keyed by the same dotted path.
Never copy a whole message to express a scheme variant.

## Deploy

Pushing to `main` runs `.github/workflows/deploy.yml`, which rebuilds, checks
`dist/` is current, and publishes `dist/` to GitHub Pages.

There is deliberately **no `CNAME` file** here. `nnavnita.com` is configured on
the `nnavnita.github.io` user-site repo; project repos inherit the custom
domain and are served at `nnavnita.com/<repo>/`. A `CNAME` in this repo would
hijack the apex domain.

Because the page is served from a subpath, routing is **hash-based**
(`#pacs.008/fields`) — GitHub Pages cannot rewrite real paths to `index.html`,
so path routing would 404 on every shared link.

## Accuracy

Field notes and summaries are hand-written explanation, not a reproduction of
the ISO 20022 e-Repository. Message IDs and element names follow the published
standard; if exhaustive, authoritative definitions are ever needed, download
the XSDs from iso20022.org and review ISO's terms before redistributing any
generated output.
