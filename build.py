#!/usr/bin/env python3
"""Build dist/index.html by inlining everything under data/ into src/index.html.

Run with no arguments. Exits non-zero on any data problem, so a broken data
file can never reach dist/ and get published.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SRC = ROOT / "src" / "index.html"
OUT = ROOT / "dist" / "index.html"
MARKER = "<!--ISO_DATA-->"

REQUIRED_MESSAGE_KEYS = ("id", "short", "name", "domain", "label", "direction", "summary", "fields")
REQUIRED_FIELD_KEYS = ("path", "name", "card", "type")
VALID_TIERS = (1, 2, 3)
VALID_USAGE = ("mandatory", "forbidden", "restricted", "optional")

# Order domains deliberately: the lifecycle of a payment, not alphabetically.
DOMAIN_ORDER = ["pain", "pacs", "camt", "remt", "head"]
DOMAIN_LABELS = {
    "pain": "pain — customer initiation",
    "pacs": "pacs — interbank clearing",
    "camt": "camt — cash management",
    "remt": "remt — remittance advice",
    "head": "head — business header",
}


class DataError(Exception):
    """A data file is wrong. Always fatal — never degrade to a partial build."""


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise DataError(f"{path.relative_to(ROOT)}: invalid JSON at line {exc.lineno}: {exc.msg}")


def load_messages(codelists):
    messages = {}
    paths = sorted((DATA / "messages").glob("*.json"))
    if not paths:
        raise DataError("data/messages/ contains no JSON files")

    for path in paths:
        msg = load_json(path)
        where = path.relative_to(ROOT)

        missing = [k for k in REQUIRED_MESSAGE_KEYS if k not in msg]
        if missing:
            raise DataError(f"{where}: missing required key(s): {', '.join(missing)}")
        if msg["domain"] not in DOMAIN_ORDER:
            raise DataError(f"{where}: unknown domain {msg['domain']!r}; expected one of {DOMAIN_ORDER}")
        if msg["short"] in messages:
            raise DataError(f"{where}: duplicate message short name {msg['short']!r}")

        validate_fields(msg, where, codelists)

        # Authoring convenience: samples are written as a list of lines so the
        # JSON stays diffable. The page wants one string.
        sample = msg.get("sample")
        if isinstance(sample, list):
            msg["sample"] = "\n".join(sample)

        messages[msg["short"]] = msg

    return messages


def validate_fields(msg, where, codelists):
    seen = set()
    for field in msg["fields"]:
        missing = [k for k in REQUIRED_FIELD_KEYS if k not in field]
        if missing:
            raise DataError(f"{where}: field {field.get('path', '?')!r} missing {', '.join(missing)}")

        path = field["path"]
        if path in seen:
            raise DataError(f"{where}: duplicate field path {path!r}")
        seen.add(path)

        tier = field.get("tier", 2)
        if tier not in VALID_TIERS:
            raise DataError(f"{where}: field {path!r} has tier {tier!r}; expected 1, 2 or 3")
        field["tier"] = tier

        ref = field.get("codelist")
        if ref and ref not in codelists:
            raise DataError(f"{where}: field {path!r} references unknown codelist {ref!r}")

    # The tree view is derived by splitting dotted paths, so every ancestor has
    # to exist as its own entry or the field becomes unreachable in the UI.
    for path in sorted(seen):
        if "." in path and path.rsplit(".", 1)[0] not in seen:
            raise DataError(
                f"{where}: field {path!r} has no parent entry "
                f"{path.rsplit('.', 1)[0]!r} — add it, or the tree cannot render this field"
            )


def validate_schemes(schemes, messages):
    for name, scheme in schemes.items():
        for key, body in scheme.items():
            if key in ("label", "scope", "caveat"):
                continue
            if key not in messages:
                raise DataError(f"data/schemes.json: {name} overlays unknown message {key!r}")
            paths = {f["path"] for f in messages[key]["fields"]}
            for path, rule in body.items():
                if path not in paths:
                    raise DataError(
                        f"data/schemes.json: {name}/{key} overlays unknown path {path!r}"
                    )
                usage = rule.get("usage")
                if usage not in VALID_USAGE:
                    raise DataError(
                        f"data/schemes.json: {name}/{key}/{path} has usage {usage!r}; "
                        f"expected one of {VALID_USAGE}"
                    )


def validate_mt_mapping(mapping, messages):
    for mt, body in mapping.items():
        target = body.get("mx")
        if not target:
            raise DataError(f"data/mt-mapping.json: {mt} has no mx target")
        # "pacs.009 COV" and similar carry a qualifier; the message is the first token.
        short = target.split()[0]
        if short not in messages:
            raise DataError(f"data/mt-mapping.json: {mt} maps to unknown message {short!r}")

        # A few MT types legitimately map to more than one ISO message — MT104
        # covers both the customer-to-bank and the interbank leg. Record every
        # target so each message's MT tab finds it.
        extra = body.get("alsoMx", [])
        for other in extra:
            if other not in messages:
                raise DataError(
                    f"data/mt-mapping.json: {mt} alsoMx names unknown message {other!r}"
                )

        body["mxShort"] = short
        body["mxAll"] = [short] + list(extra)


def find_scheme_conflicts(schemes, messages):
    """Flag overlays that contradict the base definition.

    A scheme forbidding something base ISO makes mandatory is a real
    contradiction, not a restriction. Rather than silently trusting either
    source, surface it in the page so the reader can see the data disagrees.
    """
    conflicts = []
    for name, scheme in schemes.items():
        for key, body in scheme.items():
            if key in ("label", "scope", "caveat"):
                continue
            cards = {f["path"]: f["card"] for f in messages[key]["fields"]}
            for path, rule in body.items():
                if rule.get("usage") == "forbidden" and cards[path].startswith("[1"):
                    conflicts.append(
                        {"scheme": name, "message": key, "path": path, "card": cards[path]}
                    )
    return conflicts


def main():
    try:
        codelists = load_json(DATA / "codelists.json")
        messages = load_messages(codelists)
        schemes = load_json(DATA / "schemes.json")
        mapping = load_json(DATA / "mt-mapping.json")
        validate_schemes(schemes, messages)
        validate_mt_mapping(mapping, messages)
        conflicts = find_scheme_conflicts(schemes, messages)
    except DataError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1

    ordered = sorted(
        messages.values(),
        key=lambda m: (DOMAIN_ORDER.index(m["domain"]), m["short"]),
    )

    bundle = {
        "messages": ordered,
        "codelists": codelists,
        "schemes": schemes,
        "mtMapping": mapping,
        "meta": {
            "domainOrder": DOMAIN_ORDER,
            "domainLabels": DOMAIN_LABELS,
            "messageCount": len(ordered),
            "fieldCount": sum(len(m["fields"]) for m in ordered),
            "codeCount": sum(len(c["codes"]) for c in codelists.values()),
            "conflicts": conflicts,
        },
    }

    template = SRC.read_text(encoding="utf-8")
    if MARKER not in template:
        print(f"build failed: {SRC.relative_to(ROOT)} has no {MARKER} marker", file=sys.stderr)
        return 1

    # separators= keeps the payload tight; </script> must be broken up or it
    # would terminate the surrounding script element early.
    payload = json.dumps(bundle, separators=(",", ":"), ensure_ascii=False)
    payload = payload.replace("</", "<\\/")
    html = template.replace(MARKER, f'<script>window.ISO_DATA={payload};</script>')

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    meta = bundle["meta"]
    print(
        f"built {OUT.relative_to(ROOT)}: "
        f"{meta['messageCount']} messages, {meta['fieldCount']} fields, "
        f"{len(codelists)} codelists ({meta['codeCount']} codes), "
        f"{len(schemes)} schemes, {len(mapping)} MT types, "
        f"{len(html):,} bytes"
    )
    if conflicts:
        print(f"note: {len(conflicts)} scheme/base contradiction(s) flagged in the page")
    return 0


if __name__ == "__main__":
    sys.exit(main())
