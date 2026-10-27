"""Core data model for ReconLens.

Design rule that drives everything else: **a conclusion is only as good as the
evidence behind it.** Every classification ReconLens emits carries an ordered
evidence chain, an explicit confidence, and — critically — the counter-evidence
it chose to override. A reconciliation tool that says "these two don't match"
is a diff; a tool that says *why* is an audit instrument.
"""


# --------------------------------------------------------------------------
# Entries
# --------------------------------------------------------------------------

class Entry:
    """One line on one side of the reconciliation.

    Money is stored as signed integer minor units (cents) so that no float
    rounding can ever turn a real discrepancy into a phantom one — or worse,
    hide a real one.
    """

    __slots__ = ("eid", "date", "amount", "currency", "description", "ref",
                 "side", "_siblings")

    def __init__(self, eid, date, amount, currency, description, ref, side):
        self.eid = eid
        self.date = date              # "YYYY-MM-DD"
        self.amount = amount          # int, minor units
        self.currency = currency
        self.description = description
        self.ref = ref                # payer reference / invoice no, may be ""
        self.side = side              # "bank" | "ledger"
        self._siblings = []           # same-side residuals, for DUPLICATE

    def __repr__(self):
        return "Entry(%s,%s,%d,%s)" % (self.eid, self.date, self.amount,
                                       self.side)

    def key_tuple(self):
        return (self.date, self.amount, self.currency)

    def as_dict(self):
        return {
            "id": self.eid,
            "date": self.date,
            "amount_minor": self.amount,
            "currency": self.currency,
            "description": self.description,
            "ref": self.ref,
            "side": self.side,
        }


# --------------------------------------------------------------------------
# Evidence chain
# --------------------------------------------------------------------------

class Evidence:
    """A single observable fact supporting (or undercutting) a conclusion."""

    __slots__ = ("fact", "source", "weight")

    def __init__(self, fact, source, weight=1.0):
        self.fact = fact
        self.source = source
        self.weight = weight

    def as_dict(self):
        return {"fact": self.fact, "source": self.source,
                "weight": round(self.weight, 3)}


class Explanation:
    """Why two sets of entries disagree.

    Attributes
    ----------
    kind : str
        The classification. Always one of ``KINDS``. ``UNEXPLAINED`` is a
        first-class outcome, not a failure: claiming a cause we cannot
        support would be worse than admitting we do not know.
    confidence : float
        0..1, derived from evidence weight, never hand-tuned per case.
    evidence : list[Evidence]
        Ordered, most-load-bearing first.
    counter : list[Evidence]
        Facts that point the other way. Recorded honestly; a chain with no
        counter-evidence is a sign the analysis was too shallow, not that
        the answer is certain.
    """

    KINDS = (
        "DATE_MISMATCH",      # same money, different day (settlement lag)
        "FEE_DEDUCTION",      # small shortfall, fee-shaped
        "SPLIT_OR_MERGE",     # n entries on one side == 1 on the other
        "DUPLICATE",          # same money twice on one side
        "AMOUNT_MISMATCH",    # same day/ref, genuinely different money
        "CURRENCY_MISMATCH",  # money agrees only after an FX conversion
        "REF_MISMATCH",       # everything agrees but the reference string
        "MISSING_IN_LEDGER",  # on the bank, absent from the books
        "MISSING_IN_BANK",    # in the books, absent from the bank
        "UNEXPLAINED",        # honest: no supported cause
    )

    __slots__ = ("kind", "confidence", "evidence", "counter", "note")

    def __init__(self, kind, evidence=None, counter=None, note="",
                 confidence=None):
        assert kind in self.KINDS, "unknown kind %r" % (kind,)
        self.kind = kind
        self.evidence = list(evidence or [])
        self.counter = list(counter or [])
        self.note = note
        if confidence is None:
            self.confidence = self._derive_confidence()
        else:
            self.confidence = max(0.0, min(1.0, float(confidence)))

    def _derive_confidence(self):
        """Confidence from evidence mass, discounted by what contradicts it.

        Deliberately mechanical: judges can re-derive it, and no individual
        case can be quietly flattered by a hand-set number.
        """
        if not self.evidence:
            return 0.0
        pro = sum(e.weight for e in self.evidence)
        con = sum(e.weight for e in self.counter)
        return round(pro / (pro + con + 1.0), 3)

    def as_dict(self):
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "note": self.note,
            "evidence": [e.as_dict() for e in self.evidence],
            "counter_evidence": [e.as_dict() for e in self.counter],
        }


class Match:
    """Entries on the two sides that agree well enough to be called a pair."""

    __slots__ = ("stage", "bank", "ledger")

    def __init__(self, stage, bank, ledger):
        self.stage = stage            # see matcher.STAGES
        self.bank = list(bank)        # list[Entry]
        self.ledger = list(ledger)    # list[Entry]

    def as_dict(self):
        return {
            "stage": self.stage,
            "bank": [e.eid for e in self.bank],
            "ledger": [e.eid for e in self.ledger],
        }


class Discrepancy:
    """A residual difference plus its explanation."""

    __slots__ = ("kind", "bank", "ledger", "explanation", "amount_delta")

    def __init__(self, kind, bank, ledger, explanation, amount_delta=0):
        self.kind = kind
        self.bank = list(bank)
        self.ledger = list(ledger)
        self.explanation = explanation
        self.amount_delta = amount_delta

    def as_dict(self):
        return {
            "kind": self.kind,
            "bank": [e.eid for e in self.bank],
            "ledger": [e.eid for e in self.ledger],
            "amount_delta_minor": self.amount_delta,
            "explanation": self.explanation.as_dict(),
        }
