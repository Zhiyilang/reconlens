"""Reporting.

Three renderings of the same result — text for a terminal, Markdown for a
ticket, JSON for a pipeline. They are produced from one shared dictionary
so they cannot drift apart: if two renderings disagree, that is a bug in
this file, not three separate opinions.
"""

from .model import Explanation


def summarise(matches, discrepancies, bank, ledger):
    """Aggregate counts. Everything here is derived, nothing is asserted."""
    by_kind = {}
    for d in discrepancies:
        by_kind[d.kind] = by_kind.get(d.kind, 0) + 1

    by_stage = {}
    for m in matches:
        by_stage[m.stage] = by_stage.get(m.stage, 0) + 1

    explained = sum(1 for d in discrepancies
                    if d.explanation.kind != "UNEXPLAINED")

    return {
        "bank_entries": len(bank),
        "ledger_entries": len(ledger),
        "matched_pairs": len(matches),
        "matches_by_stage": by_stage,
        "discrepancies": len(discrepancies),
        "discrepancies_by_kind": by_kind,
        "explained": explained,
        "unexplained": len(discrepancies) - explained,
        "explained_rate": (round(explained / float(len(discrepancies)), 3)
                           if discrepancies else 1.0),
    }


def to_dict(result):
    return {
        "summary": result["summary"],
        "matches": [m.as_dict() for m in result["matches"]],
        "discrepancies": [d.as_dict() for d in result["discrepancies"]],
    }


def _money(minor):
    sign = "-" if minor < 0 else ""
    v = abs(minor)
    return "%s%d.%02d" % (sign, v // 100, v % 100)


def render_text(result, show_evidence=True):
    s = result["summary"]
    lines = []
    lines.append("=" * 64)
    lines.append("ReconLens reconciliation report")
    lines.append("=" * 64)
    lines.append("bank entries   : %d" % s["bank_entries"])
    lines.append("ledger entries : %d" % s["ledger_entries"])
    lines.append("matched pairs  : %d" % s["matched_pairs"])
    for stage in sorted(s["matches_by_stage"]):
        lines.append("    %-20s %d" % (stage, s["matches_by_stage"][stage]))
    lines.append("discrepancies  : %d  (explained %d, unexplained %d, "
                 "rate %.1f%%)"
                 % (s["discrepancies"], s["explained"], s["unexplained"],
                    s["explained_rate"] * 100))
    lines.append("")

    if not result["discrepancies"]:
        lines.append("No residual differences.")
        return "\n".join(lines)

    order = sorted(result["discrepancies"],
                   key=lambda d: (-d.explanation.confidence, d.kind))
    for d in order:
        e = d.explanation
        side = "bank" if d.bank else "ledger"
        entries = d.bank or d.ledger
        head = "[%s] %s  conf=%.2f" % (e.kind, side, e.confidence)
        lines.append(head)
        for en in entries:
            lines.append("    %s  %s  %-9s %s"
                         % (en.eid, en.date, _money(en.amount),
                            en.description))
        if d.amount_delta:
            lines.append("    delta: %s" % _money(d.amount_delta))
        if show_evidence:
            for ev in e.evidence:
                lines.append("    + %s" % ev.fact)
            for ce in e.counter:
                lines.append("    - %s" % ce.fact)
        if e.note:
            lines.append("    note: %s" % e.note)
        lines.append("")
    return "\n".join(lines)


_MD_ESCAPE = {"|": "\\|"}


def _md(text):
    out = str(text)
    for k, v in _MD_ESCAPE.items():
        out = out.replace(k, v)
    return out


def render_markdown(result):
    s = result["summary"]
    lines = ["# Reconciliation report", ""]
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append("| Bank entries | %d |" % s["bank_entries"])
    lines.append("| Ledger entries | %d |" % s["ledger_entries"])
    lines.append("| Matched pairs | %d |" % s["matched_pairs"])
    lines.append("| Discrepancies | %d |" % s["discrepancies"])
    lines.append("| Explained | %d (%.1f%%) |"
                 % (s["explained"], s["explained_rate"] * 100))
    lines.append("| Unexplained | %d |" % s["unexplained"])
    lines.append("")

    if s["discrepancies_by_kind"]:
        lines.append("## Discrepancies by cause")
        lines.append("")
        lines.append("| Cause | Count |")
        lines.append("|---|---|")
        for k in sorted(s["discrepancies_by_kind"]):
            lines.append("| %s | %d |" % (k, s["discrepancies_by_kind"][k]))
        lines.append("")

    if result["discrepancies"]:
        lines.append("## Detail")
        lines.append("")
        for d in sorted(result["discrepancies"],
                        key=lambda d: (-d.explanation.confidence, d.kind)):
            e = d.explanation
            side = "bank" if d.bank else "ledger"
            lines.append("### %s (`%s`, confidence %.2f)"
                         % (_md(e.kind), side, e.confidence))
            for en in (d.bank or d.ledger):
                lines.append("- `%s` %s %s — %s"
                             % (_md(en.eid), en.date, _money(en.amount),
                                _md(en.description)))
            lines.append("")
            lines.append("**Evidence**")
            lines.append("")
            for ev in e.evidence:
                lines.append("- %s  _(%s, w=%.1f)_"
                             % (_md(ev.fact), ev.source, ev.weight))
            if e.counter:
                lines.append("")
                lines.append("**Counter-evidence**")
                lines.append("")
                for ce in e.counter:
                    lines.append("- %s  _(%s, w=%.1f)_"
                                 % (_md(ce.fact), ce.source, ce.weight))
            if e.note:
                lines.append("")
                lines.append("> %s" % _md(e.note))
            lines.append("")
    return "\n".join(lines)


def render(result, fmt="text", show_evidence=True):
    if fmt == "json":
        import json
        return json.dumps(to_dict(result), indent=2, ensure_ascii=False)
    if fmt == "markdown":
        return render_markdown(result)
    if fmt == "text":
        return render_text(result, show_evidence)
    raise ValueError("unknown format %r" % (fmt,))


def render_kinds_catalogue():
    """Documentation aid: list every cause the engine can emit."""
    return list(Explanation.KINDS)
