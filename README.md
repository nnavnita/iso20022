# iso20022

An interactive encyclopedia of ISO 20022 payments messages.

**[nnavnita.com/iso20022](https://nnavnita.com/iso20022/)**

One self-contained page covering the payments core — `pain`, `pacs`, `camt`,
`remt`, `head`. For each message: what it is and when it is used, an annotated
field tree with cardinality, a sample XML document cross-linked to the fields,
the legacy SWIFT MT equivalent with field-level mapping, and how CBPR+, SEPA,
NPP and Fedwire restrict the base definition.

Search any field path or code (`ChrgBr`, `SLEV`, `pacs.008`) to find every
message it appears in.

## Run locally

```sh
python3 build.py
open dist/index.html
```

No dependencies, no server, no build toolchain beyond Python 3.

## Contributing data

See `CLAUDE.md` for the data model — flat dotted field paths, shared codelists,
scheme overlays, and the `tier` convention that keeps the default view readable.

Field notes are hand-written explanation rather than a copy of the ISO 20022
e-Repository. Corrections welcome.

## Licence

MIT. See `LICENSE`.
