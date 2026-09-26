#!/usr/bin/env python3
"""Heading counts of the documents the site pulls, held to a record.

  python3 tools/check-pulled-headings.py           # show the counts
  python3 tools/check-pulled-headings.py --check   # for check-all.sh
  python3 tools/check-pulled-headings.py --update  # after you have told them

WHY THIS EXISTS. The site keeps a Japanese translation of every
document it pulls, at docs/ja/nes/<SLUG>.md in ITS repository, and its
deploy REFUSES when the two disagree on heading count. Prose may
change freely; a heading added, renamed away or removed stops somebody
else's build.

Nothing here can check the other side: the files it is held to are in
another repository and a fresh checkout has no sight of them. What
this repository CAN know is when one of its own pulled documents
changed heading count, which is exactly the moment somebody has to say
so. So that is what this measures.

IT COST TWO BROKEN DEPLOYS TO LEARN. On 2026-09-25 docs/parts.md
gained "## pad-ble-p4" and stopped their build. A note went into the
README naming parts.md. Hours later docs/pad-ble-build.md gained six
headings and stopped it again, because the note had named the instance
and not the rule. A note that has to be remembered is not a gate.

THE SLUG IS THEIRS, NOT OURS. The shadow is named after the site's
slug, not our filename, so pad-ble-build.md is held against pad-ble.md
over there. The mapping is recorded here so a reader can find the file
that will break.

THE LIST IS THEIRS TOO, AND IT GROWS. The authority is DOCS in
their web/scripts/pull-nesdocs.mjs, which covers several repositories
and not only this one; the 22 below are this repository's rows of it,
copied 2026-09-25. They have put a comment at that list saying a new
nes-bench entry, or a Japanese shadow appearing for one, is news for
here.
A document of ours that they start pulling will not appear here by
itself, so this catches changes to what they pull TODAY, which is the
common case, and not a newly pulled file.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORD = ROOT / "tools" / "pulled-docs.json"


def counts(docs):
    out = {}
    for name in docs:
        p = ROOT / "docs" / name
        out[name] = None if not p.exists() else sum(
            1 for line in p.read_text().splitlines() if line.startswith("#"))
    return out


def main():
    rec = json.loads(RECORD.read_text())
    docs = rec["docs"]
    now = counts(docs)

    if "--update" in sys.argv:
        for name, n in now.items():
            if n is not None:
                docs[name]["headings"] = n
        RECORD.write_text(json.dumps(rec, indent=1) + "\n")
        print(f"check-pulled-headings: recorded {len(docs)} document(s)")
        return 0

    bad = []
    for name, spec in sorted(docs.items()):
        n = now[name]
        if n is None:
            bad.append(f"{name} is gone, and the site pulls it as {spec['slug']}")
        elif n != spec["headings"]:
            d = n - spec["headings"]
            bad.append(f"{name}: {spec['headings']} headings recorded, {n} now ({d:+d}); "
                       f"the site holds it against {spec['slug']}"
                       + ("" if spec.get("shadow", True) else ", which has no shadow yet"))

    if "--check" in sys.argv:
        for b in bad:
            print("  " + b)
        if bad:
            print("  TELL THE SITE SESSION, then run --update to record it.")
            print("check-pulled-headings: a pulled document changed heading count")
            return 1
        print(f"check-pulled-headings: {len(docs)} pulled documents unchanged")
        return 0

    print(f"{'document':<42} {'slug':<26} headings")
    for name, spec in sorted(docs.items()):
        n = now[name]
        mark = "" if n == spec["headings"] else f"  CHANGED from {spec['headings']}"
        shadow = "" if spec.get("shadow", True) else "  (no shadow yet)"
        print(f"{name:<42} {spec['slug']:<26} {n}{mark}{shadow}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
