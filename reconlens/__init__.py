"""ReconLens — a reconciliation engine that explains the difference.

ReconLens diffs two books of record and, for every residual, emits a
cause with an auditable evidence chain. It is deliberately conservative:
where no cause is supported it says ``UNEXPLAINED`` rather than guessing,
because in an audit context a confident wrong answer costs more than an
admitted gap.

Zero dependencies: standard library only.
"""

from .explain import build_discrepancies, explain, similarity, looks_like_fee
from .loader import load_any, load_csv, load_json, parse_amount, parse_date
from .matcher import reconcile, day_gap, STAGES
from .model import (Discrepancy, Entry, Evidence, Explanation, Match)
from .report import (render, render_markdown, render_text, summarise,
                     to_dict)

__version__ = "1.0.0"

__all__ = [
    "run", "reconcile", "explain", "build_discrepancies", "similarity",
    "looks_like_fee", "load_any", "load_csv", "load_json", "parse_amount",
    "parse_date", "day_gap", "STAGES", "Discrepancy", "Entry", "Evidence",
    "Explanation", "Match", "render", "render_markdown", "render_text",
    "summarise", "to_dict", "__version__",
]


def run(bank_entries, ledger_entries, date_window=3, merge_max=3,
        tolerance=0, fx_rates=None):
    """Match, explain, summarise — the whole pipeline in one call.

    Returns the result dictionary consumed by :func:`render`.
    """
    matches, ub, ul = reconcile(bank_entries, ledger_entries,
                                date_window=date_window,
                                merge_max=merge_max,
                                tolerance=tolerance,
                                fx_rates=fx_rates)
    discrepancies = build_discrepancies(ub, ul, date_window)
    summary = summarise(matches, discrepancies, bank_entries, ledger_entries)
    return {"matches": matches, "discrepancies": discrepancies,
            "unmatched_bank": ub, "unmatched_ledger": ul,
            "summary": summary}
