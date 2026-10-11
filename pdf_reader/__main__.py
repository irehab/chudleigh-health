"""Run on a PDF from the command line:  python -m pdf_reader report.pdf   (add --json for the full result)"""
import json
import sys

from . import read_pdf


def main(argv):
    if len(argv) < 2:
        print("usage: python -m pdf_reader file.pdf [--json]")
        return 2
    with open(argv[1], "rb") as f:
        res = read_pdf(f.read())
    if "--json" in argv:
        print(json.dumps(res.to_dict(), indent=1, ensure_ascii=False))
        return 0
    print(f"{res.device_label or 'Unknown device'}: status {res.status}")
    for k, v in res.values.items():
        print(f"  {k:46} {v.text}" + ("   (calculated)" if v.source == "calculated" else ""))
    for c in res.checks:
        print(f"  {'PASS' if c.ok else ('NOTE' if c.severity == 'note' else 'FAIL')}  {c.name}: {c.detail}")
    for st in res.statements:
        print(f"  device statement ({st['kind']}): {st['text']}   [{st['caution']}]")
    for line in res.printed_ranges:
        print(f"  printed range: {line}")
    for n in res.notes:
        print(f"  note: {n}")
    return 0


sys.exit(main(sys.argv))
