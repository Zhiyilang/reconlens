"""Command line entry point.

    python -m reconlens --bank bank.csv --ledger ledger.csv
    python -m reconlens --demo --format markdown --out report.md
"""

import argparse
import io
import os
import sys

from . import load_any, render, run
from .samples import demo_bank, demo_ledger


def build_parser():
    p = argparse.ArgumentParser(
        prog="reconlens",
        description="Reconcile two books of record and explain every "
                    "residual difference.")
    p.add_argument("--bank", help="CSV or JSON file for the bank side")
    p.add_argument("--ledger", help="CSV or JSON file for the ledger side")
    p.add_argument("--demo", action="store_true",
                   help="run on the built-in worked example")
    p.add_argument("--date-window", type=int, default=3,
                   help="days of settlement lag tolerated (default 3)")
    p.add_argument("--merge-max", type=int, default=3,
                   help="largest split/merge group considered (default 3)")
    p.add_argument("--tolerance", type=int, default=0,
                   help="minor units of slack on exact stages (default 0)")
    p.add_argument("--currency", default="CNY",
                   help="currency assumed when a file omits it")
    p.add_argument("--format", default="text",
                   choices=("text", "markdown", "json"))
    p.add_argument("--no-evidence", action="store_true",
                   help="hide evidence chains (text format only)")
    p.add_argument("--out", help="write the report here instead of stdout")
    p.add_argument("--fail-on-unexplained", action="store_true",
                   help="exit non-zero when any residual has no cause")
    return p


def _load(p, bank_path, ledger_path):
    bank, probs_b = load_any(bank_path, "bank", p.currency)
    ledger, probs_l = load_any(ledger_path, "ledger", p.currency)
    for msg in probs_b + probs_l:
        sys.stderr.write("warning: %s\n" % msg)
    return bank, ledger


def _write(text):
    """Write a report without letting a narrow console codec crash the CLI.

    Reports contain box-drawing rules and em dashes. On a console pinned to
    ASCII (LC_ALL=C, PYTHONIOENCODING=ascii) ``sys.stdout.write`` raises
    UnicodeEncodeError, which would make the tool unusable on exactly the
    minimal CI images where it is most likely to be run. Degrade the
    glyphs; never fail the run.
    """
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
        return
    except UnicodeEncodeError:
        pass
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        enc = sys.stdout.encoding or "utf-8"
        buf.write(text.encode(enc, "replace"))
        buf.flush()
    else:
        sys.stdout.write(text.encode("ascii", "replace").decode("ascii"))
        sys.stdout.flush()


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)

    if args.demo:
        bank, ledger = demo_bank(), demo_ledger()
    elif args.bank and args.ledger:
        bank, ledger = _load(p=args, bank_path=args.bank,
                             ledger_path=args.ledger)
    else:
        p.error("either --demo or both --bank and --ledger are required")

    result = run(bank, ledger, date_window=args.date_window,
                 merge_max=args.merge_max, tolerance=args.tolerance)

    text = render(result, args.format,
                  show_evidence=not args.no_evidence)
    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.write(u"\n")
        sys.stderr.write("wrote %s\n" % os.path.basename(args.out))
    else:
        _write(text)
        _write(u"\n")

    if args.fail_on_unexplained and result["summary"]["unexplained"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
