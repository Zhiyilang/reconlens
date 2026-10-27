"""Multi-stage matching.

Matching runs as a deterministic cascade. Each stage is strictly stricter
than the one after it, and an entry consumed by an earlier stage is never
reconsidered. That ordering is the whole point: it makes the result
reproducible, and it means a later, looser stage can never steal a
high-quality pair from an earlier one.

Stages
------
``EXACT_REF``          same reference and same money  — the gold standard
``EXACT_AMOUNT_DATE``  same money, same day
``AMOUNT_DATE_WINDOW`` same money, day within ±N (settlement lag)
``SPLIT_OR_MERGE``     ≤3 entries on one side sum to one entry on the other
``UNMATCHED``          residual — becomes a discrepancy
"""

from .model import Match

STAGES = ("EXACT_REF", "EXACT_AMOUNT_DATE", "AMOUNT_DATE_WINDOW",
          "SPLIT_OR_MERGE", "UNMATCHED")


def _day_num(date):
    """``YYYY-MM-DD`` -> a comparable integer day index (no calendar import)."""
    y, m, d = (int(x) for x in date.split("-"))
    return _days_before_year(y) + _days_before_month(y, m) + d


def _is_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or y % 400 == 0


def _days_before_year(y):
    y -= 1
    return y * 365 + y // 4 - y // 100 + y // 400


def _days_before_month(y, m):
    lengths = (31, 28 + _is_leap(y), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return sum(lengths[:m - 1])


def day_gap(date_a, date_b):
    """Absolute day difference between two ``YYYY-MM-DD`` strings."""
    return abs(_day_num(date_a) - _day_num(date_b))


def _index(entries):
    """amount -> list[Entry], preserving input order inside each bucket."""
    idx = {}
    for e in entries:
        idx.setdefault(e.amount, []).append(e)
    return idx


def _take(pool, entry):
    """Remove an entry from a pool (identity based)."""
    for i, e in enumerate(pool):
        if e is entry:
            pool.pop(i)
            return True
    return False


def reconcile(bank, ledger, date_window=3, merge_max=3, tolerance=0,
              fx_rates=None):
    """Match two sides of a reconciliation.

    Parameters
    ----------
    bank, ledger : list[Entry]
    date_window : int
        Days of settlement lag tolerated by ``AMOUNT_DATE_WINDOW``.
    merge_max : int
        Largest group size considered by ``SPLIT_OR_MERGE``.
    tolerance : int
        Minor units of slack allowed by ``AMOUNT_DATE_WINDOW`` only. The
        ``EXACT_*`` stages stay strict: for money, an unexplained slack is
        a discrepancy, not a match.
    fx_rates : dict[(from, to) -> float], optional
        Applied before matching when the two sides are in different
        currencies, so cross-currency books can still be reconciled.
        Without it, entries in different currencies never match — 100 CNY
        is not 100 USD, and silently equating them is how a reconciliation
        engine ends up certifying a wrong balance.

    Returns
    -------
    (matches, unmatched_bank, unmatched_ledger)
    """
    if fx_rates:
        bank = _convert(bank, fx_rates, _target_of(ledger))
        ledger = _convert(ledger, fx_rates, _target_of(ledger))

    # Match inside each currency, in first-seen order, so the result does
    # not depend on dict iteration order.
    currencies = []
    for e in list(bank) + list(ledger):
        if e.currency not in currencies:
            currencies.append(e.currency)

    pool_b = list(bank)
    pool_l = list(ledger)
    matches = []
    for ccy in currencies:
        sub_b = [e for e in pool_b if e.currency == ccy]
        sub_l = [e for e in pool_l if e.currency == ccy]
        if not sub_b or not sub_l:
            continue
        found, rb, rl = _cascade(sub_b, sub_l, date_window, merge_max,
                                 tolerance)
        matches.extend(found)
        keep_b = set(id(e) for e in rb)
        keep_l = set(id(e) for e in rl)
        pool_b = [e for e in pool_b
                  if e.currency != ccy or id(e) in keep_b]
        pool_l = [e for e in pool_l
                  if e.currency != ccy or id(e) in keep_l]
    return matches, pool_b, pool_l


def _cascade(pool_b, pool_l, date_window, merge_max, tolerance):
    """Run the four matching stages over one currency's entries."""
    matches = []

    # --- Stage 1: reference + money -------------------------------------
    l_by_ref = {}
    for e in pool_l:
        l_by_ref.setdefault((e.ref, e.amount), []).append(e)
    for b in list(pool_b):
        key = (b.ref, b.amount)
        if b.ref and key in l_by_ref and l_by_ref[key]:
            l = l_by_ref[key][0]
            l_by_ref[key].remove(l)
            _take(pool_l, l)
            _take(pool_b, b)
            matches.append(Match("EXACT_REF", [b], [l]))

    # --- Stage 2: same money, same day ----------------------------------
    _match_by_key(pool_b, pool_l, matches,
                  lambda e: (e.amount, e.date), "EXACT_AMOUNT_DATE")

    # --- Stage 3: same money (within tolerance), nearby day --------------
    for b in list(pool_b):
        for l in pool_l:
            if abs(l.amount - b.amount) > tolerance:
                continue
            if day_gap(b.date, l.date) <= date_window:
                _take(pool_l, l)
                _take(pool_b, b)
                matches.append(Match("AMOUNT_DATE_WINDOW", [b], [l]))
                break

    # --- Stage 4: split / merge -----------------------------------------
    matches.extend(_match_groups(pool_b, pool_l, "bank", merge_max,
                                 date_window))
    matches.extend(_match_groups(pool_l, pool_b, "ledger", merge_max,
                                 date_window, flip=True))

    return matches, pool_b, pool_l


def _match_by_key(pool_b, pool_l, matches, keyfn, stage):
    buckets = {}
    for l in pool_l:
        buckets.setdefault(keyfn(l), []).append(l)
    for b in list(pool_b):
        k = keyfn(b)
        if k in buckets and buckets[k]:
            l = buckets[k].pop(0)
            _take(pool_l, l)
            _take(pool_b, b)
            matches.append(Match(stage, [b], [l]))


def _match_groups(singles, group_side, single_side_name, merge_max,
                  date_window, flip=False):
    """Match one entry against a small group of entries on the other side.

    ``singles`` is the side that stays single; ``group_side`` supplies the
    members whose sum must equal it. Searching combinations up to
    ``merge_max`` keeps this exact rather than approximate — a greedy
    subset-sum would silently miss real splits.
    """
    found = []
    group_pool = list(group_side)
    for s in list(singles):
        target = s.amount
        combo = _find_combo(group_pool, target, merge_max, s.date,
                            date_window)
        if combo is None:
            continue
        for c in combo:
            _take(group_pool, c)
        _take(singles, s)
        if flip:
            found.append(Match("SPLIT_OR_MERGE", combo, [s]))
        else:
            found.append(Match("SPLIT_OR_MERGE", [s], combo))
    # reflect removals back into the caller's list
    for e in list(group_side):
        if not any(e is g for g in group_pool):
            group_side.remove(e)
    return found


def _find_combo(pool, target, max_size, anchor_date, date_window):
    """First (smallest) combination of ``pool`` summing to ``target``."""
    for size in range(2, max_size + 1):
        for combo in _combinations(pool, size):
            if sum(c.amount for c in combo) != target:
                continue
            if all(day_gap(c.date, anchor_date) <= date_window
                   for c in combo):
                return list(combo)
    return None


def _combinations(items, k):
    if k == 0:
        yield []
        return
    for i in range(len(items)):
        for rest in _combinations(items[i + 1:], k - 1):
            yield [items[i]] + rest


def _target_of(entries):
    for e in entries:
        if getattr(e, "currency", None):
            return e.currency
    return None


def _convert(entries, fx_rates, target):
    if target is None:
        return entries
    out = []
    for e in entries:
        if e.currency == target:
            out.append(e)
            continue
        rate = fx_rates.get((e.currency, target))
        if rate is None:
            out.append(e)
            continue
        out.append(type(e)(e.eid, e.date, int(round(e.amount * rate)),
                           target, e.description, e.ref, e.side))
    return out
