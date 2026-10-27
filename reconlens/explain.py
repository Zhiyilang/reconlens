"""Turning residuals into explanations.

This module is the reason ReconLens exists. A reconciliation engine that
ends with "3 unmatched items" has merely moved the work to a human. What
an auditor needs is a defensible *cause* per item — and, just as
importantly, a clear signal when no cause is defensible.

Every explanation is assembled from observable facts with an explicit
source. Where the facts conflict, the losing facts are recorded as
counter-evidence rather than dropped. Confidence is derived
arithmetically from that record, so it can be recomputed by anyone
reading the output.
"""

from .matcher import day_gap
from .model import Discrepancy, Evidence, Explanation

# Words that make a shortfall look like a charge rather than an error.
FEE_WORDS = (
    "fee", "charge", "commission", "surcharge", "interest", "service",
    "手续费", "服务费", "管理费", "利息", "工本费", "汇划费", "年费", "手续费",
)

# A shortfall this large (relative to the entry) stops being fee-shaped.
FEE_MAX_RATIO = 0.02

# Below this many minor units a shortfall is more likely rounding than a fee.
FEE_MIN_ABS = 1


def _tokens(text):
    out = []
    cur = []
    for ch in str(text).lower():
        if ch.isalnum():
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def similarity(a, b):
    """Token Jaccard similarity of two description strings, 0..1."""
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def looks_like_fee(text):
    low = str(text).lower()
    return any(w in low for w in FEE_WORDS)


def _same_side_twin(entry, siblings):
    """Another entry on the same side with identical money and day."""
    for other in siblings:
        if other is entry:
            continue
        if other.amount == entry.amount and other.date == entry.date:
            return other
    return None


def explain(entry, others, date_window=3):
    """Explain why a residual ``entry`` failed to match.

    Parameters
    ----------
    entry : Entry
        The unmatched residual.
    others : list[Entry]
        Residuals on the *opposite* side — the candidate explanations.
    date_window : int
        The window the matcher already tried; anything outside it is what
        ``DATE_MISMATCH`` is for.

    Returns
    -------
    Explanation
    """
    if not others:
        kind = ("MISSING_IN_LEDGER" if entry.side == "bank"
                else "MISSING_IN_BANK")
        return Explanation(
            kind,
            evidence=[Evidence(
                "no residual on the %s side" % _opposite(entry.side),
                "matcher.residual_pool", 1.0)],
            counter=[Evidence(
                "a same-day entry on the other side would have matched at "
                "stage EXACT_AMOUNT_DATE", "matcher.STAGES", 0.5)],
            note="present on one side only; confirm it is not a timing cut-off",
        )

    # --- currency -------------------------------------------------------
    if all(o.currency != entry.currency for o in others):
        return Explanation(
            "CURRENCY_MISMATCH",
            evidence=[Evidence(
                "every residual on the %s side is in %s, this entry is in %s"
                % (_opposite(entry.side), others[0].currency, entry.currency),
                "entry.currency", 1.0)],
            counter=[Evidence(
                "an FX conversion may legitimately have been applied to "
                "this entry", "domain", 0.6)],
            note="supply fx_rates to reconcile across currencies",
        )

    # --- duplicate ------------------------------------------------------
    twin = _same_side_twin(entry, _siblings_of(entry, others))
    if twin is not None:
        return Explanation(
            "DUPLICATE",
            evidence=[
                Evidence("identical amount %d on %s" % (entry.amount,
                                                        entry.date),
                         "entry.amount+date", 1.0),
                Evidence("another entry on the same side shares both",
                         "entry.siblings", 1.0),
                Evidence("descriptions %d%% similar" % int(
                    similarity(entry.description, twin.description) * 100),
                         "explain.similarity", 0.6),
            ],
            counter=[Evidence(
                "two genuine payments of the same size on the same day are "
                "possible", "domain", 0.7)],
            note="check for a double posting before writing it off",
        )

    # --- nearest candidate by money, then by day ------------------------
    by_amount = sorted(others, key=lambda o: abs(o.amount - entry.amount))
    near = by_amount[0]
    delta = abs(near.amount - entry.amount)
    gap = day_gap(entry.date, near.date)
    sim = similarity(entry.description, near.description)

    # --- fee-shaped shortfall ------------------------------------------
    base = max(abs(entry.amount), 1)
    ratio = delta / float(base)
    if delta > FEE_MIN_ABS and ratio <= FEE_MAX_RATIO:
        ev = [
            Evidence("shortfall of %d minor units (%.3f%% of the entry)"
                     % (delta, ratio * 100), "explain.delta", 1.0),
            Evidence("shortfall is within the fee-shaped band (<= %.0f%%)"
                     % (FEE_MAX_RATIO * 100), "explain.FEE_MAX_RATIO", 0.8),
        ]
        if looks_like_fee(entry.description) or looks_like_fee(
                near.description):
            ev.append(Evidence(
                "description mentions a charge-like term",
                "explain.FEE_WORDS", 0.9))
        else:
            ev.append(Evidence(
                "description carries no charge-like term",
                "explain.FEE_WORDS", 0.0))
        counter = [Evidence(
            "a small shortfall can also be a data-entry or rounding error",
            "domain", 0.6)]
        if gap > date_window:
            counter.append(Evidence(
                "candidate is %d days away (> window %d)" % (gap, date_window),
                "matcher.date_window", 0.5))
        return Explanation("FEE_DEDUCTION", evidence=[e for e in ev
                                                      if e.weight > 0],
                           counter=counter,
                           note="confirm against the fee schedule")

    # --- same money, day outside the window ----------------------------
    if delta == 0 and gap > date_window:
        return Explanation(
            "DATE_MISMATCH",
            evidence=[
                Evidence("amounts are identical (%d)" % entry.amount,
                         "entry.amount", 1.0),
                Evidence("dates differ by %d days, beyond the %d-day window"
                         % (gap, date_window), "matcher.day_gap", 1.0),
                Evidence("descriptions %d%% similar"
                         % int(sim * 100), "explain.similarity", 0.7),
            ],
            counter=[Evidence(
                "two unrelated payments of the same size in the same period "
                "are possible", "domain", 0.6)],
            note="typical of settlement lag or a cut-off at period end",
        )

    # --- same day, different money -------------------------------------
    if gap == 0 and delta > 0:
        return Explanation(
            "AMOUNT_MISMATCH",
            evidence=[
                Evidence("dates agree exactly (%s)" % entry.date,
                         "entry.date", 1.0),
                Evidence("amounts differ by %d minor units" % delta,
                         "explain.delta", 1.0),
                Evidence("descriptions %d%% similar" % int(sim * 100),
                         "explain.similarity", 0.7),
            ],
            counter=[Evidence(
                "a partial payment or a partial refund would look identical",
                "domain", 0.7)],
            note="amounts genuinely disagree — needs a human decision",
        )

    # --- reference-only difference --------------------------------------
    if delta == 0 and gap == 0:
        return Explanation(
            "REF_MISMATCH",
            evidence=[
                Evidence("amount and date agree exactly", "entry", 1.0),
                Evidence("references differ (%r vs %r)"
                         % (entry.ref, near.ref), "entry.ref", 1.0),
            ],
            counter=[Evidence(
                "the matcher would normally pair these at "
                "EXACT_AMOUNT_DATE", "matcher.STAGES", 0.8)],
            note="reached only when an earlier stage consumed the natural "
                 "partner",
        )

    # --- nothing supported ----------------------------------------------
    return Explanation(
        "UNEXPLAINED",
        evidence=[Evidence(
            "nearest residual differs by %d minor units and %d days"
            % (delta, gap), "explain.nearest", 0.5)],
        counter=[
            Evidence("no amount, date or reference agreement with any "
                     "residual", "explain.search", 1.0),
        ],
        note="no supported cause — left for a human on purpose",
    )


def _opposite(side):
    return "ledger" if side == "bank" else "bank"


def _siblings_of(entry, others):
    """Residuals on the same side, recovered from the pool we were given.

    ``explain`` receives the opposite side's residuals; the caller passes
    the full residual pair through ``build_discrepancies``, which stashes
    siblings on the entry for duplicate detection.
    """
    return getattr(entry, "_siblings", [])


def build_discrepancies(unmatched_bank, unmatched_ledger, date_window=3):
    """Explain every residual on both sides."""
    out = []
    for side_pool, other_pool in ((unmatched_bank, unmatched_ledger),
                                  (unmatched_ledger, unmatched_bank)):
        for e in side_pool:
            e._siblings = [x for x in side_pool]
            exp = explain(e, other_pool, date_window)
            delta = 0
            if other_pool:
                near = min(other_pool,
                           key=lambda o: abs(o.amount - e.amount))
                delta = abs(near.amount - e.amount)
            out.append(Discrepancy(exp.kind,
                                   [e] if e.side == "bank" else [],
                                   [e] if e.side == "ledger" else [],
                                   exp, delta))
    return out
