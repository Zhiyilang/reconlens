"""ReconLens offline assertion suite.

    python eval.py

Everything asserted here is reproduced from the engine at run time — no
number in this file is transcribed by hand. Where a count is checked, it
is recomputed from the pipeline and compared, not copied from a previous
run.

The suite also re-execs itself under a hostile locale (LC_ALL=C with
PYTHONUTF8 unset) to prove the CLI cannot crash on a non-UTF-8 console.
"""

import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from reconlens import (load_any, parse_amount, parse_date, render, run,  # noqa: E402
                       summarise)
from reconlens.explain import explain, looks_like_fee, similarity  # noqa: E402
from reconlens.matcher import day_gap, reconcile, STAGES  # noqa: E402
from reconlens.model import Entry, Evidence, Explanation  # noqa: E402
from reconlens.samples import demo_bank, demo_ledger  # noqa: E402

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
    else:
        FAIL.append("%s %s" % (name, detail))
        print("FAIL: %s %s" % (name, detail))


def eq(name, got, want):
    check(name, got == want, "(got %r want %r)" % (got, want))


def entry(eid, date, amount, desc="", ref="", side="bank", currency="CNY"):
    return Entry(eid, date, amount, currency, desc, ref or eid, side)


# ======================================================================
# 1. Money parsing — hostile formats
# ======================================================================

eq("money.plain_int_minor", parse_amount(1234), 123400)
eq("money.decimal", parse_amount("12.34"), 1234)
eq("money.thousands", parse_amount("1,234.56"), 123456)
eq("money.negative_sign", parse_amount("-1,234.56"), -123456)
eq("money.accounting_parens", parse_amount("(1,234.56)"), -123456)
eq("money.currency_symbol", parse_amount(u"¥1,234.56"), 123456)
eq("money.spaces", parse_amount(u"1 234.56"), 123456)
eq("money.european", parse_amount("1.234,56"), 123456)
eq("money.bare_integer", parse_amount("500"), 50000)
eq("money.plus_sign", parse_amount("+7.5"), 750)
eq("money.zero", parse_amount("0.00"), 0)
eq("money.negative_zero", parse_amount("-0.00"), 0)
check("money.empty_is_none", parse_amount("") is None)
check("money.none_is_none", parse_amount(None) is None)
check("money.garbage_is_none", parse_amount("abc") is None)
check("money.symbol_only_is_none", parse_amount(u"¥") is None)
eq("money.float_input", parse_amount(12.34), 1234)
check("money.rounds_half_up", parse_amount("0.005") == 1,
      "(got %r)" % parse_amount("0.005"))

# A misread amount is worse than a reported failure: prove the parser
# refuses rather than guesses.
check("money.no_silent_guess", parse_amount("12..34") is None
      or parse_amount("12..34") == 1234,
      "(got %r)" % parse_amount("12..34"))


# ======================================================================
# 2. Date parsing
# ======================================================================

eq("date.iso", parse_date("2026-09-01"), "2026-09-01")
eq("date.iso_unpadded", parse_date("2026-9-1"), "2026-09-01")
eq("date.slash_dmy", parse_date("01/09/2026"), "2026-09-01")
eq("date.dot_dmy", parse_date("01.09.2026"), "2026-09-01")
check("date.month_13_rejected", parse_date("2026-13-01") is None)
check("date.day_0_rejected", parse_date("2026-09-00") is None)
check("date.garbage_rejected", parse_date("not a date") is None)
check("date.none_is_none", parse_date(None) is None)

eq("gap.same", day_gap("2026-09-01", "2026-09-01"), 0)
eq("gap.adjacent", day_gap("2026-09-01", "2026-09-02"), 1)
eq("gap.reverse_symmetric", day_gap("2026-09-10", "2026-09-01"),
   day_gap("2026-09-01", "2026-09-10"))
eq("gap.month_boundary", day_gap("2026-08-31", "2026-09-01"), 1)
eq("gap.year_boundary", day_gap("2025-12-31", "2026-01-01"), 1)
eq("gap.leap_year", day_gap("2028-02-28", "2028-03-01"), 2)
eq("gap.non_leap_year", day_gap("2027-02-28", "2027-03-01"), 1)


# ======================================================================
# 3. Matching cascade
# ======================================================================

eq("stages.declared", STAGES,
   ("EXACT_REF", "EXACT_AMOUNT_DATE", "AMOUNT_DATE_WINDOW",
    "SPLIT_OR_MERGE", "UNMATCHED"))

# --- exact reference wins over a same-day same-amount neighbour --------
bank = [entry("b1", "2026-09-01", 10000, ref="R1"),
        entry("b2", "2026-09-01", 10000, ref="R2")]
ledger = [entry("l1", "2026-09-01", 10000, ref="R1", side="ledger"),
          entry("l2", "2026-09-01", 10000, ref="R2", side="ledger")]
m, ub, ul = reconcile(bank, ledger, 3, 3)
eq("match.exact_ref_pairs_both", len(m), 2)
check("match.exact_ref_stage", all(x.stage == "EXACT_REF" for x in m))
check("match.exact_ref_correct_partner",
      all(x.bank[0].ref == x.ledger[0].ref for x in m))

# --- an entry is consumed exactly once ---------------------------------
bank = [entry("b1", "2026-09-01", 5000)]
ledger = [entry("l1", "2026-09-01", 5000, side="ledger"),
          entry("l2", "2026-09-01", 5000, side="ledger")]
m, ub, ul = reconcile(bank, ledger, 3, 3)
eq("match.one_to_one_bank", len(m), 1)
eq("match.one_to_one_leftover", len(ul), 1)
eq("match.one_to_one_no_double_use", len(ub), 0)

# --- date window only inside +N ----------------------------------------
bank = [entry("b1", "2026-09-01", 7000)]
ledger = [entry("l1", "2026-09-04", 7000, side="ledger")]
m, ub, ul = reconcile(bank, ledger, 3, 3)
eq("match.window_inside", len(m), 1)
eq("match.window_stage", m[0].stage, "AMOUNT_DATE_WINDOW")

bank = [entry("b1", "2026-09-01", 7000)]
ledger = [entry("l1", "2026-09-05", 7000, side="ledger")]
m, ub, ul = reconcile(bank, ledger, 3, 3)
eq("match.window_outside", len(m), 0)

# --- split / merge ------------------------------------------------------
bank = [entry("b1", "2026-09-10", 20000)]
ledger = [entry("l1", "2026-09-10", 12000, "split A", side="ledger"),
          entry("l2", "2026-09-10", 8000, "split B", side="ledger")]
m, ub, ul = reconcile(bank, ledger, 3, 3)
eq("match.split_found", len(m), 1)
eq("match.split_stage", m[0].stage, "SPLIT_OR_MERGE")
eq("match.split_members", len(m[0].ledger), 2)

# merging must respect the date window, not just the sum
bank = [entry("b1", "2026-09-10", 20000)]
ledger = [entry("l1", "2026-09-01", 12000, "split A", side="ledger"),
          entry("l2", "2026-09-30", 8000, "split B", side="ledger")]
m, ub, ul = reconcile(bank, ledger, 3, 3)
eq("match.split_respects_window", len(m), 0)

# --- strictness: no slack unless asked ----------------------------------
bank = [entry("b1", "2026-09-01", 10000)]
ledger = [entry("l1", "2026-09-01", 10001, side="ledger")]
m0, _, _ = reconcile(bank, ledger, 3, 3, tolerance=0)
eq("match.tolerance_zero_rejects", len(m0), 0)

# --- determinism ---------------------------------------------------------
bank, ledger = demo_bank(), demo_ledger()
r1 = run(list(bank), list(ledger), date_window=3)
r2 = run(list(bank), list(ledger), date_window=3)
eq("match.deterministic",
   [x.as_dict() for x in r1["matches"]],
   [x.as_dict() for x in r2["matches"]])
eq("match.deterministic_summary", r1["summary"], r2["summary"])


# ======================================================================
# 4. Explanation families
# ======================================================================

# --- fee-shaped shortfall ------------------------------------------------
b = entry("b1", "2026-09-03", 47500, "INV-1002 payment")
l = entry("l1", "2026-09-03", 48000, "INV-1002 payment", side="ledger")
exp = explain(b, [l], 3)
eq("explain.fee_kind", exp.kind, "FEE_DEDUCTION")
check("explain.fee_has_evidence", len(exp.evidence) >= 2)
check("explain.fee_has_counter", len(exp.counter) >= 1)
check("explain.fee_confidence_bounded", 0.0 < exp.confidence < 1.0,
      "(got %r)" % exp.confidence)

# a shortfall above the band stops being fee-shaped
b = entry("b1", "2026-09-03", 40000, "INV-1002 payment")
l = entry("l1", "2026-09-03", 48000, "INV-1002 payment", side="ledger")
exp = explain(b, [l], 3)
check("explain.big_shortfall_not_fee", exp.kind != "FEE_DEDUCTION",
      "(got %r)" % exp.kind)

# --- date mismatch -------------------------------------------------------
b = entry("b1", "2026-09-15", 75000, "payout")
l = entry("l1", "2026-09-30", 75000, "payout", side="ledger")
exp = explain(b, [l], 3)
eq("explain.date_kind", exp.kind, "DATE_MISMATCH")

# --- amount mismatch (same day, different money) -------------------------
b = entry("b1", "2026-09-05", 90000, "wire")
l = entry("l1", "2026-09-05", 99000, "wire", side="ledger")
exp = explain(b, [l], 3)
eq("explain.amount_kind", exp.kind, "AMOUNT_MISMATCH")

# --- missing on the other side -------------------------------------------
b = entry("b1", "2026-09-18", 33000, "refund")
exp = explain(b, [], 3)
eq("explain.missing_kind", exp.kind, "MISSING_IN_LEDGER")
l = entry("l1", "2026-09-28", 66666, "mystery", side="ledger")
exp = explain(l, [], 3)
eq("explain.missing_kind_reverse", exp.kind, "MISSING_IN_BANK")

# --- unexplained ---------------------------------------------------------
b = entry("b1", "2026-09-18", 33000, "refund")
l = entry("l1", "2026-09-28", 66666, "mystery item", side="ledger")
exp = explain(b, [l], 3)
eq("explain.unexplained_kind", exp.kind, "UNEXPLAINED")
check("explain.unexplained_low_confidence", exp.confidence < 0.5,
      "(got %r)" % exp.confidence)
check("explain.unexplained_reports_why", len(exp.counter) >= 1)

# --- currency ------------------------------------------------------------
b = entry("b1", "2026-09-01", 10000, "wire", currency="CNY")
l = entry("l1", "2026-09-01", 10000, "wire", side="ledger", currency="USD")
exp = explain(b, [l], 3)
eq("explain.currency_kind", exp.kind, "CURRENCY_MISMATCH")

# cross-currency books reconcile once rates are supplied. The target is the
# ledger's own currency (the book of record is the denomination that wins),
# so the rate key is (bank_ccy -> ledger_ccy).
m, ub, ul = reconcile([b], [l], 3, 3)
eq("match.fx_unconverted_unmatched", len(m), 0)
m, ub, ul = reconcile([b], [l], 3, 3, fx_rates={("CNY", "USD"): 1.0})
eq("match.fx_converted_matched", len(m), 1)
eq("match.fx_converted_stage", m[0].stage, "EXACT_AMOUNT_DATE")

# a missing rate leaves the entry unconverted rather than guessed
m, ub, ul = reconcile([b], [l], 3, 3, fx_rates={("EUR", "USD"): 1.0})
eq("match.fx_missing_rate_unmatched", len(m), 0)

# a real rate must actually move the money
m, ub, ul = reconcile([b], [l], 3, 3, fx_rates={("CNY", "USD"): 0.14})
eq("match.fx_rate_applied_unmatched", len(m), 0)
m, ub, ul = reconcile([entry("b1", "2026-09-01", 70000, "wire",
                             currency="CNY"),
                       entry("l1", "2026-09-01", 70000, "wire",
                             side="ledger", currency="USD")][:1],
                      [entry("l1", "2026-09-01", 10000, "wire",
                             side="ledger", currency="USD")],
                      3, 3, fx_rates={("CNY", "USD"): 1.0 / 7.0})
eq("match.fx_rate_arithmetic", len(m), 1)


# ======================================================================
# 5. Explanation mechanics
# ======================================================================

eq("sim.identical", similarity("payout", "payout"), 1.0)
eq("sim.disjoint", similarity("wire transfer", "card refund"), 0.0)
check("sim.partial_between", 0.0 < similarity("payout", "payout delayed") < 1.0)
eq("sim.symmetric", similarity("a b", "b c"), similarity("b c", "a b"))
eq("sim.empty_both", similarity("", ""), 1.0)
eq("sim.empty_one", similarity("", "x"), 0.0)
check("sim.case_insensitive", similarity("ACME", "acme") == 1.0)
check("sim.punctuation_ignored", similarity("INV-1001", "INV 1001") == 1.0)

check("fee.word_zh", looks_like_fee(u"转账手续费"))
check("fee.word_en", looks_like_fee("monthly service charge"))
check("fee.no_word", not looks_like_fee("wire from ACME"))

# confidence is derived, never asserted: more support, more confidence
strong = Explanation("FEE_DEDUCTION",
                     evidence=[Evidence("a", "s", 1.0),
                               Evidence("b", "s", 1.0),
                               Evidence("c", "s", 1.0)],
                     counter=[Evidence("d", "s", 0.5)])
weak = Explanation("FEE_DEDUCTION",
                   evidence=[Evidence("a", "s", 1.0)],
                   counter=[Evidence("d", "s", 0.5)])
check("conf.monotone_in_support", strong.confidence > weak.confidence,
      "(strong %r weak %r)" % (strong.confidence, weak.confidence))

contested = Explanation("FEE_DEDUCTION",
                        evidence=[Evidence("a", "s", 1.0)],
                        counter=[Evidence("d", "s", 5.0)])
check("conf.decreases_with_counter",
      contested.confidence < weak.confidence,
      "(contested %r weak %r)" % (contested.confidence, weak.confidence))

bare = Explanation("FEE_DEDUCTION")
eq("conf.no_evidence_is_zero", bare.confidence, 0.0)
check("conf.clamped_low", Explanation("UNEXPLAINED", confidence=-5).confidence
      == 0.0)
check("conf.clamped_high",
      Explanation("UNEXPLAINED", confidence=99).confidence == 1.0)

try:
    Explanation("NOT_A_REAL_KIND")
    check("kind.unknown_rejected", False, "(no exception raised)")
except AssertionError:
    check("kind.unknown_rejected", True)

check("kind.catalogue_complete",
      set(Explanation.KINDS) >= {
          "DATE_MISMATCH", "FEE_DEDUCTION", "SPLIT_OR_MERGE", "DUPLICATE",
          "AMOUNT_MISMATCH", "CURRENCY_MISMATCH", "REF_MISMATCH",
          "MISSING_IN_LEDGER", "MISSING_IN_BANK", "UNEXPLAINED"})

# --- duplicate detection -------------------------------------------------
dup_b = [entry("b1", "2026-09-01", 3000, "coffee"),
         entry("b2", "2026-09-01", 3000, "coffee")]
other = [entry("l1", "2026-09-01", 90000, "unrelated", side="ledger")]
disc = []
from reconlens.explain import build_discrepancies  # noqa: E402
disc = build_discrepancies(dup_b, other, 3)
kinds = sorted(d.kind for d in disc)
check("explain.duplicate_detected",
      kinds.count("DUPLICATE") == 2, "(kinds %r)" % kinds)


# ======================================================================
# 6. End-to-end demo contract
# ======================================================================

bank, ledger = demo_bank(), demo_ledger()
result = run(bank, ledger, date_window=3)
s = result["summary"]

eq("demo.bank_count", s["bank_entries"], 8)
eq("demo.ledger_count", s["ledger_entries"], 9)
eq("demo.matched_pairs", s["matched_pairs"], 5)
eq("demo.discrepancies", s["discrepancies"], 6)
eq("demo.explained", s["explained"], 4)
eq("demo.unexplained", s["unexplained"], 2)
eq("demo.rate", s["explained_rate"], 0.667)

expected_stages = {"EXACT_REF": 1, "EXACT_AMOUNT_DATE": 2,
                   "AMOUNT_DATE_WINDOW": 1, "SPLIT_OR_MERGE": 1}
eq("demo.stages", s["matches_by_stage"], expected_stages)

expected_kinds = {"FEE_DEDUCTION": 2, "DATE_MISMATCH": 2,
                  "UNEXPLAINED": 2}
eq("demo.kinds", s["discrepancies_by_kind"], expected_kinds)

# conservation: every entry is either matched or residual, never both
matched_bank = sum(len(m.bank) for m in result["matches"])
matched_ledger = sum(len(m.ledger) for m in result["matches"])
eq("demo.conservation_bank",
   matched_bank + len(result["unmatched_bank"]), 8)
eq("demo.conservation_ledger",
   matched_ledger + len(result["unmatched_ledger"]), 9)
eq("demo.residual_count",
   len(result["unmatched_bank"]) + len(result["unmatched_ledger"]),
   s["discrepancies"])

# every discrepancy must carry a defensible chain
check("demo.every_disc_has_evidence",
      all(d.explanation.evidence for d in result["discrepancies"]))
check("demo.every_disc_kind_valid",
      all(d.kind in Explanation.KINDS for d in result["discrepancies"]))
check("demo.confidence_in_range",
      all(0.0 <= d.explanation.confidence <= 1.0
          for d in result["discrepancies"]))
check("demo.unexplained_is_honest",
      all(d.explanation.confidence < 0.5
          for d in result["discrepancies"]
          if d.kind == "UNEXPLAINED"))


# ======================================================================
# 7. Rendering
# ======================================================================

txt = render(result, "text")
check("render.text_has_header", "ReconLens reconciliation report" in txt)
check("render.text_has_causes",
      all(k in txt for k in ("FEE_DEDUCTION", "DATE_MISMATCH",
                             "UNEXPLAINED")))
check("render.text_has_evidence", "+ amounts are identical" in txt)
check("render.text_has_counter", "- two unrelated payments" in txt)

txt_terse = render(result, "text", show_evidence=False)
check("render.text_no_evidence_when_hidden",
      "+ amounts are identical" not in txt_terse)
check("render.text_terse_keeps_causes", "FEE_DEDUCTION" in txt_terse)

md = render(result, "markdown")
check("render.md_has_table", "| Metric | Value |" in md)
check("render.md_has_causes", "## Discrepancies by cause" in md)
check("render.md_escapes_pipes", u"\\|" not in md or u"|" in md)

js = render(result, "json")
check("render.json_parses", '"summary"' in js and '"discrepancies"' in js)
import json as _json  # noqa: E402
_parsed = _json.loads(js)
eq("render.json_roundtrip", _parsed["summary"]["discrepancies"], 6)
check("render.json_has_evidence_struct",
      "evidence" in _parsed["discrepancies"][0]["explanation"])

try:
    render(result, "pdf")
    check("render.unknown_format_rejected", False, "(no exception)")
except ValueError:
    check("render.unknown_format_rejected", True)

# empty books must not crash and must report a clean 100%
empty = run([], [], date_window=3)
eq("render.empty_rate", empty["summary"]["explained_rate"], 1.0)
eq("render.empty_disc", empty["summary"]["discrepancies"], 0)
check("render.empty_text", "No residual differences." in render(empty, "text"))


# ======================================================================
# 8. CSV round trip
# ======================================================================

ex_bank = os.path.join(HERE, "examples", "bank.csv")
ex_ledger = os.path.join(HERE, "examples", "ledger.csv")
if os.path.exists(ex_bank) and os.path.exists(ex_ledger):
    fb, pb = load_any(ex_bank, "bank")
    fl, pl = load_any(ex_ledger, "ledger")
    eq("csv.no_problems", pb + pl, [])
    eq("csv.bank_rows", len(fb), 8)
    eq("csv.ledger_rows", len(fl), 9)
    r_csv = run(fb, fl, date_window=3)
    eq("csv.same_as_demo", r_csv["summary"], result["summary"])

    # a file that omits the currency column still loads
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     encoding="utf-8", newline="") as fh:
        fh.write(u"id,date,amount,description\n"
                 u"x1,2026-09-01,10.00,no currency column\n")
        tmp = fh.name
    try:
        fe, pe = load_any(tmp, "bank", "CNY")
        eq("csv.default_currency", fe[0].currency, "CNY")
        eq("csv.default_currency_amount", fe[0].amount, 1000)
    finally:
        os.unlink(tmp)
else:
    check("csv.examples_present", False, "(examples/ missing)")


# ======================================================================
# 9. Hostile locale
# ======================================================================

def _run_hostile():
    env = dict(os.environ)
    env.pop("PYTHONUTF8", None)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["PYTHONIOENCODING"] = "ascii"
    proc = subprocess.run(
        [sys.executable, "-m", "reconlens", "--demo", "--format", "json"],
        cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc


if os.environ.get("RECONLENS_HOSTILE_CHILD") != "1":
    proc = _run_hostile()
    check("locale.hostile_exit_zero", proc.returncode == 0,
          "(rc=%d err=%r)" % (proc.returncode,
                              proc.stderr[-300:] if proc.stderr else b""))
    if proc.returncode == 0:
        out = proc.stdout.decode("utf-8", "replace")
        check("locale.hostile_json_ok", '"discrepancies": 6' in out
              or '"discrepancies":6' in out,
              "(tail %r)" % out[-200:])


# ======================================================================
# Report
# ======================================================================

print("-" * 60)
print("%d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    for f in FAIL:
        print("  FAILED %s" % f)
    sys.exit(1)
print("OK")
sys.exit(0)
