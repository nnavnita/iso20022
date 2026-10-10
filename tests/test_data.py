#!/usr/bin/env python3
"""Data integrity checks for the ISO 20022 explorer.

Run: python3 tests/test_data.py
Exits non-zero and prints every failure. No dependencies.
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"

VALID_DOMAINS = {"pain", "pacs", "camt", "remt", "head"}
VALID_USAGE = {"mandatory", "forbidden", "restricted", "optional"}
VALID_KINDS = {"internal", "external"}
VALID_TYPES = {
    "group", "text", "code", "amount", "date", "datetime",
    "decimal", "indicator", "rate", "bic", "iban",
}
CARD = re.compile(r"^\[\d+\.\.(\d+|n)\]$")
MSG_ID = re.compile(r"^[a-z]{4}\.\d{3}\.\d{3}\.\d{2}$")
SHORT = re.compile(r"^[a-z]{4}\.\d{3}$")

failures = []
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def load():
    codelists = json.loads((DATA / "codelists.json").read_text(encoding="utf-8"))
    schemes = json.loads((DATA / "schemes.json").read_text(encoding="utf-8"))
    mapping = json.loads((DATA / "mt-mapping.json").read_text(encoding="utf-8"))
    messages = {}
    for path in sorted((DATA / "messages").glob("*.json")):
        msg = json.loads(path.read_text(encoding="utf-8"))
        messages[msg["short"]] = msg
        check(
            path.stem == msg["short"],
            f"{path.name}: filename does not match short name {msg['short']!r}",
        )
    return codelists, schemes, mapping, messages


def test_codelists(codelists):
    for name, cl in codelists.items():
        check("name" in cl, f"codelist {name}: missing name")
        check(cl.get("kind") in VALID_KINDS, f"codelist {name}: kind must be internal or external")
        check(bool(cl.get("codes")), f"codelist {name}: no codes")
        for code, desc in cl.get("codes", {}).items():
            check(
                code == code.upper() and " " not in code,
                f"codelist {name}: code {code!r} should be uppercase with no spaces",
            )
            check(bool(desc.strip()), f"codelist {name}/{code}: empty description")


def test_messages(messages, codelists):
    check(bool(messages), "no message files found")
    for short, msg in messages.items():
        check(SHORT.match(short), f"{short}: short name is not domain.nnn")
        check(MSG_ID.match(msg["id"]), f"{short}: id {msg['id']!r} is not domain.nnn.nnn.nn")
        check(msg["id"].startswith(short), f"{short}: id does not start with the short name")
        check(msg["domain"] in VALID_DOMAINS, f"{short}: unknown domain {msg['domain']!r}")
        check(msg["domain"] == short.split(".")[0], f"{short}: domain does not match the short name")
        check(len(msg["summary"]) > 40, f"{short}: summary is too thin to be useful")
        check(bool(msg["fields"]), f"{short}: no fields")

        paths = set()
        for field in msg["fields"]:
            path = field["path"]
            label = f"{short}/{path}"
            check(path not in paths, f"{label}: duplicate path")
            paths.add(path)
            check(CARD.match(field["card"]), f"{label}: bad cardinality {field['card']!r}")
            check(field["type"] in VALID_TYPES, f"{label}: unknown type {field['type']!r}")
            check(field.get("tier", 2) in (1, 2, 3), f"{label}: tier must be 1, 2 or 3")
            check(bool(field["name"].strip()), f"{label}: empty name")

            ref = field.get("codelist")
            if ref:
                check(ref in codelists, f"{label}: unknown codelist {ref!r}")
                check(
                    field["type"] == "code",
                    f"{label}: has a codelist but type is {field['type']!r}, expected 'code'",
                )

        # The UI derives the tree by splitting on dots, so an orphan path is
        # a field the reader can never see.
        for path in sorted(paths):
            if "." in path:
                parent = path.rsplit(".", 1)[0]
                check(parent in paths, f"{short}/{path}: parent {parent!r} is missing")

        # A group has children; a leaf does not. Mixing these up renders wrongly.
        for field in msg["fields"]:
            prefix = field["path"] + "."
            has_children = any(p.startswith(prefix) for p in paths)
            if has_children:
                check(
                    field["type"] == "group",
                    f"{short}/{field['path']}: has children but type is {field['type']!r}",
                )

        for ref in msg.get("related", []):
            check(SHORT.match(ref), f"{short}: related entry {ref!r} is not a message short name")
            check(ref != short, f"{short}: lists itself as related")


def test_samples(messages):
    for short, msg in messages.items():
        sample = msg.get("sample")
        check(bool(sample), f"{short}: no sample document")
        if not sample:
            continue

        text = "\n".join(sample) if isinstance(sample, list) else sample

        # Well-formedness. Unbalanced tags are invisible to the eye and fatal
        # to anyone copying the sample as a starting point.
        try:
            ET.fromstring(text)
        except ET.ParseError as exc:
            failures.append(f"{short}: sample XML is not well-formed: {exc}")
        checks_bump()

        # The namespace must name this exact message version, or the sample
        # teaches the wrong thing.
        check(
            msg["id"] in text,
            f"{short}: sample does not carry its own message id {msg['id']!r} in the namespace",
        )


def checks_bump():
    global checks
    checks += 1


def test_schemes(schemes, messages):
    for name, scheme in schemes.items():
        check("label" in scheme, f"scheme {name}: missing label")
        check("scope" in scheme, f"scheme {name}: missing scope")
        check("caveat" in scheme, f"scheme {name}: missing caveat — every scheme needs its accuracy note")

        overlays = 0
        for key, body in scheme.items():
            if key in ("label", "scope", "caveat"):
                continue
            check(key in messages, f"scheme {name}: overlays unknown message {key!r}")
            if key not in messages:
                continue
            paths = {f["path"]: f for f in messages[key]["fields"]}
            for path, rule in body.items():
                overlays += 1
                label = f"scheme {name}/{key}/{path}"
                check(path in paths, f"{label}: unknown field path")
                check(rule.get("usage") in VALID_USAGE, f"{label}: bad usage {rule.get('usage')!r}")
                if rule.get("allowed"):
                    field = paths.get(path)
                    if field and field.get("codelist"):
                        known = set(json.loads(
                            (DATA / "codelists.json").read_text(encoding="utf-8")
                        )[field["codelist"]]["codes"])
                        unknown = set(rule["allowed"]) - known
                        check(
                            not unknown,
                            f"{label}: allowed codes not in codelist "
                            f"{field['codelist']}: {sorted(unknown)}",
                        )
        check(overlays > 0, f"scheme {name}: defines no overlays, so selecting it does nothing")


def test_mt_mapping(mapping, messages):
    for mt, body in mapping.items():
        check("name" in body, f"MT {mt}: missing name")
        check(bool(body.get("mx")), f"MT {mt}: missing mx target")
        short = (body.get("mx") or "").split()[0] if body.get("mx") else ""
        check(short in messages, f"MT {mt}: targets unknown message {short!r}")
        check(bool(body.get("fields")), f"MT {mt}: no field pairs")

        targets = [short] + list(body.get("alsoMx", []))
        for other in body.get("alsoMx", []):
            check(other in messages, f"MT {mt}: alsoMx names unknown message {other!r}")

        paths = set()
        for t in targets:
            if t in messages:
                paths |= {f["path"] for f in messages[t]["fields"]}
        for pair in body.get("fields", []):
            label = f"MT {mt}/{pair.get('mt') or 'no-mt'}"
            check("mtName" in pair, f"{label}: missing mtName")
            check(
                pair.get("mt") or pair.get("mx"),
                f"{label}: a pair with neither an MT field nor an MX path says nothing",
            )
            check(
                not (pair.get("mt") is None and pair.get("mx") is None),
                f"{label}: both sides null",
            )
            # A gap in either direction must carry a note explaining it,
            # otherwise the table looks like missing data rather than a real gap.
            if pair.get("mt") is None or pair.get("mx") is None:
                check(bool(pair.get("note")), f"{label}: a mapping gap must explain itself")

            mx = pair.get("mx")
            if mx and "+" not in mx and "[" not in mx and " " not in mx and not mx.startswith("head."):
                check(mx in paths, f"{label}: mx path {mx!r} is not a field of {'/'.join(targets)}")


def test_cross_references(messages):
    # Every message that claims an MT equivalent should be reachable from the
    # mapping file, or the MT tab will be empty while the header promises one.
    mapping = json.loads((DATA / "mt-mapping.json").read_text(encoding="utf-8"))
    targets = set()
    for body in mapping.values():
        targets.add((body["mx"] or "").split()[0])
        targets |= set(body.get("alsoMx", []))

    for short, msg in messages.items():
        if msg.get("mtEquivalent"):
            check(
                short in targets,
                f"{short}: claims MT equivalents {msg['mtEquivalent']} but no mapping targets it",
            )
        else:
            # Claiming nothing is fine, but it has to say why, or the MT tab is
            # just blank and the reader cannot tell absence from omission.
            check(
                bool(msg.get("mtNote")),
                f"{short}: has no MT equivalent and no mtNote explaining the absence",
            )


def main():
    codelists, schemes, mapping, messages = load()
    test_codelists(codelists)
    test_messages(messages, codelists)
    test_samples(messages)
    test_schemes(schemes, messages)
    test_mt_mapping(mapping, messages)
    test_cross_references(messages)

    if failures:
        print(f"FAILED — {len(failures)} problem(s) across {checks} checks:\n")
        for f in failures:
            print(f"  · {f}")
        return 1

    print(
        f"ok — {checks} checks passed: {len(messages)} messages, "
        f"{sum(len(m['fields']) for m in messages.values())} fields, "
        f"{len(codelists)} codelists, {len(schemes)} schemes, {len(mapping)} MT types"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
