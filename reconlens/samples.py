"""Built-in worked example.

The demo pair is engineered so a single run exercises every stage of the
cascade and every cause the explainer can emit. That is deliberate: the
demo doubles as the readable specification of the engine.

    bank 8 entries / ledger 9 entries
    EXACT_REF          b01 <-> l01   reference + money agree
    EXACT_AMOUNT_DATE  b03 <-> l03, b06 <-> l07
    AMOUNT_DATE_WINDOW b04 <-> l04   one day apart
    SPLIT_OR_MERGE     b05 <-> l05+l06
    FEE_DEDUCTION      b02 / l02     500-unit shortfall, fee-shaped
    DATE_MISMATCH      b07 / l08     same money, 15 days apart
    UNEXPLAINED        b08 / l09     nothing agrees
"""

from .model import Entry


def demo_bank():
    return [
        Entry("b01", "2026-09-01", 125000, "CNY", "INV-1001 payment",
              "INV-1001", "bank"),
        Entry("b02", "2026-09-03", 47500, "CNY", "INV-1002 payment",
              "INV-1002", "bank"),
        Entry("b03", "2026-09-05", 99000, "CNY", "wire from ACME", "",
              "bank"),
        Entry("b04", "2026-09-08", 50000, "CNY", "transfer", "", "bank"),
        Entry("b05", "2026-09-10", 200000, "CNY", "settlement", "", "bank"),
        Entry("b06", "2026-09-12", 120000, "CNY", "card settlement", "",
              "bank"),
        Entry("b07", "2026-09-15", 75000, "CNY", "payout", "", "bank"),
        Entry("b08", "2026-09-18", 33000, "CNY", "refund", "", "bank"),
    ]


def demo_ledger():
    return [
        Entry("l01", "2026-09-01", 125000, "CNY", "INV-1001 payment",
              "INV-1001", "ledger"),
        Entry("l02", "2026-09-03", 48000, "CNY", "INV-1002 payment",
              "INV-1002", "ledger"),
        Entry("l03", "2026-09-05", 99000, "CNY", "wire from ACME", "",
              "ledger"),
        Entry("l04", "2026-09-09", 50000, "CNY", "transfer", "", "ledger"),
        Entry("l05", "2026-09-10", 120000, "CNY", "settlement split A", "",
              "ledger"),
        Entry("l06", "2026-09-10", 80000, "CNY", "settlement split B", "",
              "ledger"),
        Entry("l07", "2026-09-12", 120000, "CNY", "card settlement", "",
              "ledger"),
        Entry("l08", "2026-09-30", 75000, "CNY", "payout", "", "ledger"),
        Entry("l09", "2026-09-28", 66666, "CNY", "mystery item", "",
              "ledger"),
    ]


def demo_bank_csv():
    return (
        "id,ref,date,amount,currency,description\n"
        "b01,INV-1001,2026-09-01,1250.00,CNY,INV-1001 payment\n"
        "b02,INV-1002,2026-09-03,475.00,CNY,INV-1002 payment\n"
        "b03,,2026-09-05,990.00,CNY,wire from ACME\n"
        "b04,,2026-09-08,500.00,CNY,transfer\n"
        "b05,,2026-09-10,2000.00,CNY,settlement\n"
        "b06,,2026-09-12,1200.00,CNY,card settlement\n"
        "b07,,2026-09-15,750.00,CNY,payout\n"
        "b08,,2026-09-18,330.00,CNY,refund\n"
    )


def demo_ledger_csv():
    return (
        "id,ref,date,amount,currency,description\n"
        "l01,INV-1001,2026-09-01,1250.00,CNY,INV-1001 payment\n"
        "l02,INV-1002,2026-09-03,480.00,CNY,INV-1002 payment\n"
        "l03,,2026-09-05,990.00,CNY,wire from ACME\n"
        "l04,,2026-09-09,500.00,CNY,transfer\n"
        "l05,,2026-09-10,1200.00,CNY,settlement split A\n"
        "l06,,2026-09-10,800.00,CNY,settlement split B\n"
        "l07,,2026-09-12,1200.00,CNY,card settlement\n"
        "l08,,2026-09-30,750.00,CNY,payout\n"
        "l09,,2026-09-28,666.66,CNY,mystery item\n"
    )
