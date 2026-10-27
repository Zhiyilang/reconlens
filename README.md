# ReconLens

**A reconciliation engine that explains the difference.**

Point ReconLens at two books of record. It pairs what agrees and, for every
residual, emits a *cause* with an auditable evidence chain. Where no cause
is supported it says `UNEXPLAINED` instead of guessing — because in an
audit context a confident wrong answer costs more than an admitted gap.

Built for the **2nd "Newtouch Cup" AI + Infinite Horizons Innovation
Competition** (`AI + 无限万象`). The full AI-assisted development record is
in [`AI_CODING_JOURNEY.md`](AI_CODING_JOURNEY.md) — that document is a
required, standalone submission artefact.

Zero dependencies. Standard library only. Runs anywhere Python runs.

---

## The problem

Every reconciliation tool on the market ends the same way: a list of
unmatched items. That is not a result, it is a to-do list — the expensive
part of reconciliation is not *finding* the difference, it is *explaining*
it, and today a human does that by hand, one line at a time.

ReconLens attacks the second half. For each residual it produces:

- a **cause** drawn from a fixed catalogue (never free text),
- an **evidence chain** — ordered, weighted facts with a source each,
- **counter-evidence** — the facts it chose to override, kept honestly,
- a **confidence** derived arithmetically from the above, recomputable
  by anyone reading the output.

A chain with no counter-evidence is a sign the analysis was too shallow,
not a sign the answer is certain.

---

## Quick start

```bash
python -m reconlens --demo                      # built-in worked example
python -m reconlens --bank bank.csv --ledger ledger.csv
python -m reconlens --bank examples/bank.csv --ledger examples/ledger.csv \
        --format markdown --out report.md
python eval.py                                  # 129 assertions
```

Input files are CSV or JSON. Column names are matched case-insensitively
against common aliases (`id`, `ref`, `date`, `amount`, `currency`,
`description`, plus Chinese aliases), so an untouched bank export usually
loads without editing.

---

## Matching cascade

Matching is a deterministic cascade. Each stage is strictly stricter than
the one after it, and an entry consumed by an earlier stage is never
reconsidered — so a looser stage can never steal a high-quality pair from a
tighter one, and the result is reproducible.

| Stage | Rule |
|---|---|
| `EXACT_REF` | reference **and** amount agree — the gold standard |
| `EXACT_AMOUNT_DATE` | amount and date agree |
| `AMOUNT_DATE_WINDOW` | amount agrees, date within ±N days (settlement lag) |
| `SPLIT_OR_MERGE` | ≤3 entries on one side sum to one entry on the other |
| `UNMATCHED` | residual — handed to the explainer |

Entries in different currencies are matched separately and never equated.
100 CNY is not 100 USD; supply `fx_rates` to reconcile across currencies.

---

## Causes

| Cause | Meaning |
|---|---|
| `FEE_DEDUCTION` | shortfall inside the fee-shaped band (≤ 2%) |
| `DATE_MISMATCH` | identical money, day beyond the window — settlement lag |
| `AMOUNT_MISMATCH` | same day, genuinely different money |
| `SPLIT_OR_MERGE` | one side split or merged what the other booked whole |
| `DUPLICATE` | same money twice on one side |
| `CURRENCY_MISMATCH` | agrees only after an FX conversion |
| `REF_MISMATCH` | everything agrees but the reference |
| `MISSING_IN_LEDGER` | on the bank, absent from the books |
| `MISSING_IN_BANK` | in the books, absent from the bank |
| `UNEXPLAINED` | no supported cause — left for a human on purpose |

---

## What the output looks like

```
[FEE_DEDUCTION] bank  conf=0.53
    b02  2026-09-03  475.00    INV-1002 payment
    delta: 5.00
    + shortfall of 500 minor units (1.053% of the entry)
    + shortfall is within the fee-shaped band (<= 2%)
    - a small shortfall can also be a data-entry or rounding error
    note: confirm against the fee schedule
```

Three renderings — text, Markdown and JSON — are produced from one shared
dictionary, so they cannot drift apart.

---

## Measured results

Reproduced by `python eval.py`; every number is recomputed at run time,
none is transcribed.

| Metric | Value |
|---|---|
| Assertions passing (`python eval.py`) | **129 / 129** |
| Demo: bank / ledger entries | 8 / 9 |
| Demo: matched pairs | 5 |
| Demo: discrepancies | 6 |
| Demo: explained / unexplained | 4 / 2 |
| Demo: explained rate | **66.7%** |
| Engine lines | 1,310 |
| Assertion-suite lines | 488 |

The demo set is engineered so a single run exercises all four matching
stages and five causes — it doubles as the readable specification.

The 2 unexplained residuals are deliberate. The engine refuses to claim a
cause it cannot support; inflating the rate would be trivially easy and
would defeat the point of the tool.

---

## Layout

```
reconlens/
  model.py      data model + evidence chains
  loader.py     hostile-format parsing (accounting negatives, ¥, D/M/YYYY)
  matcher.py    four-stage deterministic cascade
  explain.py    cause attribution with evidence/counter-evidence ledgers
  report.py     text / markdown / JSON rendering
  samples.py    worked example covering every stage and cause
  __main__.py   CLI
eval.py         offline assertion suite (129 assertions, incl. hostile locale)
AI_CODING_JOURNEY.md   standalone AI-development record (competition artefact)
examples/       bank.csv, ledger.csv
```

---

## Design decisions

**Money is integer minor units.** Floats cannot represent `0.1`. A half-cent
that vanishes is exactly the failure this library exists to prevent, so
parsing uses `Decimal` with `ROUND_HALF_UP` — `round()` would apply
banker's rounding and turn `0.005` into `0`.

**Deterministic cascade, not global optimisation.** A globally optimal
assignment cannot answer "why this pair?". The cascade can: every match
names the rule it satisfied.

**Confidence is derived, never tuned.** It is `pro / (pro + con + 1)` from
recorded weights. No per-case hand-setting means no result can be quietly
flattered.

**`UNEXPLAINED` is a first-class outcome**, with an assertion that its
confidence stays below 0.5.

**Conservation is enforced.** Matched entries plus residual entries must
equal the total, on both sides. A reconciliation engine's worst failure is
an entry silently disappearing.

---

## Verifying

```bash
python eval.py
```

Runs 129 assertions covering money and date parsing across hostile formats,
every matching stage, every cause, evidence mechanics, the end-to-end demo
contract, all three renderings, CSV round-trip, and — by re-executing the
CLI in a subprocess under `LC_ALL=C LANG=C` with `PYTHONUTF8` unset — proof
that a non-UTF-8 console cannot crash the tool.

---

## Author

Built by **Zhiyilang** — an RPA developer (影刀 / 来也 UiBot) moving into
agent engineering. The domain insight behind this tool comes from having
built reconciliation automations by hand: the matching was always the easy
part.

## Licence

MIT. See [LICENSE](LICENSE).
