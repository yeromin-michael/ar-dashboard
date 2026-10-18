"""Deterministic synthetic data. All companies, people and figures are fictional.

Dates are generated relative to the as-of month, so the demo always looks current
while staying reproducible for a given (seed, as_of).
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from ..model import (ActionItem, ContractTerm, Customer, Dataset, Invoice,
                     Payment, RevenueLine, UsageBatch)

# name, entity, currency, product, payer profile, terms, modules
CUSTOMERS = [
    ("Acme Logistics", "Inc", "USD", "Subscription+HW", "slow", 30, ["usage_billing"]),
    ("Borealis Freight", "Ltd", "EUR", "Subscription", "good", 45, []),
    ("Cobalt Mobility", "Inc", "USD", "Data", "good", 30, []),
    ("Driftwood Insurance", "Inc", "USD", "Data", "chronic", 60, []),
    ("Ember Fleet Services", "Inc", "USD", "Subscription+HW", "good", 30, ["serials"]),
    ("Fjordline Transit", "Ltd", "EUR", "Subscription", "slow", 30, []),
    ("Granite Rail Partners", "Inc", "USD", "HW", "good", 30, []),
    ("Harbor & Hale Couriers", "Inc", "USD", "Subscription", "chronic", 30, []),
    ("Ionic Delivery Co", "Ltd", "ILS", "Subscription", "good", 30, []),
    ("Juniper Cargo", "Ltd", "EUR", "Subscription+HW", "disputed", 45, []),
    ("Kestrel Robotics", "Inc", "USD", "Data", "slow", 45, []),
    ("Lumen Telematics", "Ltd", "ILS", "Subscription", "good", 30, []),
    ("Meridian Municipal Fleet", "Inc", "USD", "Subscription+HW", "slow", 60, []),
    ("Orchid Assurance", "Inc", "USD", "Data", "good", 30, []),
    ("Pinecrest Motors", "Inc", "USD", "HW", "chronic", 30, []),
    ("Quillstone Data Labs", "Ltd", "EUR", "Data", "good", 30, []),
]

FIRST = ["Dana", "Avery", "Jordan", "Riley", "Morgan", "Casey", "Taylor", "Quinn",
         "Rowan", "Skyler", "Emerson", "Hayden", "Parker", "Reese", "Sasha", "Noa"]
LAST = ["Levin", "Okafor", "Marsh", "Castillo", "Brandt", "Nakamura", "Ferreira", "Holm",
        "Adler", "Kovacs", "Moreau", "Santos", "Lindqvist", "Peretz", "Byrne", "Ito"]

# (days late mean, probability an invoice is still unpaid if older than 30 days)
PROFILES = {
    "good": (2, 0.00),
    "slow": (20, 0.04),
    "chronic": (40, 0.18),
    "disputed": (10, 0.12),
}
TAX = {"Inc": 0.0, "Ltd": 0.17}   # simplified: IL VAT on Ltd, US Inc mostly exempt B2B
SALES_TAX_INC = 0.08875           # applied to hardware for Inc
CURRENCY_SCALE = {"USD": 1.0, "EUR": 0.92, "ILS": 3.7}   # keep amounts comparable across currencies


def _month_start(d: date, offset: int) -> date:
    m = d.month - 1 + offset
    return date(d.year + m // 12, m % 12 + 1, 1)


def _month_end(d: date) -> date:
    return _month_start(d, 1) - timedelta(days=1)


def _slug(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())[:10]


def load(options: dict, as_of: date) -> Dataset:
    rng = random.Random(options.get("seed", 7))
    months = int(options.get("months", 10))
    ds = Dataset(source="sample (fictional)")
    inv_seq = 0

    def next_inv(entity: str, d: date) -> str:
        nonlocal inv_seq
        inv_seq += 1
        return f"{'US' if entity == 'Inc' else 'IL'}-{d.year % 100:02d}{inv_seq:05d}"

    for idx, (name, entity, cur, product, profile, terms, modules) in enumerate(CUSTOMERS):
        cid = _slug(name)
        contact = f"{FIRST[idx]} {LAST[idx]}"
        domain = "".join(ch for ch in name.lower() if ch.isalnum()) + ".example"
        ds.customers.append(Customer(
            id=cid, name=name, entity=entity, currency=cur, product=product,
            contact_name=contact,
            contact_emails=[f"{FIRST[idx].lower()}@{domain}", f"ap@{domain}"],
            budget_code=f"BC-{1000 + idx * 17}", terms_days=terms, modules=modules,
        ))
        scale = rng.choice([1.0, 1.6, 2.5, 4.0, 7.0]) * CURRENCY_SCALE[cur]
        late_mean, unpaid_p = PROFILES[profile]
        start = _month_start(as_of, -(months - 1))

        # annual prepaid deal for some data customers -> deferred revenue
        if product == "Data" and rng.random() < 0.6:
            d = _month_start(start, rng.randint(0, 2))
            amount = round(rng.choice([36000, 60000, 90000]) * scale / 2, -2)
            inv = Invoice(next_inv(entity, d), cid, entity, d, d + timedelta(days=terms), cur,
                          amount, round(amount * TAX[entity], 2), "data", "deferred",
                          "Annual data license (12 months, billed upfront)")
            ds.invoices.append(inv)
            for k in range(12):
                m = _month_start(d, k)
                if m <= as_of:
                    ds.revenue.append(RevenueLine(cid, m.strftime("%Y-%m"), "data",
                                                  round(amount / 12, 2), cur, inv.id))

        for k in range(months):
            m = _month_start(start, k)
            issue = _month_end(m)
            if issue > as_of:
                continue
            lines = []
            if "usage_billing" in modules:
                # invoice is derived from the usage batch, so calculator and billing agree
                batch = UsageBatch(cid, m.strftime("%Y-%m"), units=150 + k * rng.randint(8, 25),
                                   rate_per_unit=24.0, base_fee=1500.0, tax_rate=0.0, hw_share=0.25)
                ds.usage.append(batch)
                lines.append(("subscription", batch.subtotal,
                              f"Usage billing - {batch.units} units - {m:%b %Y}"))
            elif "Subscription" in product:
                units = int(40 * scale + k * rng.randint(0, 6))
                lines.append(("subscription", round(units * rng.choice([18, 22, 25]), 2),
                              f"Platform subscription - {units} units - {m:%b %Y}"))
            if "HW" in product and k % (2 if product == "HW" else 3) == 0 and rng.random() < 0.8:
                qty = int(rng.choice([20, 50, 120, 300]) * min(scale, 2.5 * CURRENCY_SCALE[cur]))
                lines.append(("hardware", round(qty * rng.choice([95, 140, 189]), 2),
                              f"Hardware shipment - {qty} devices"))
            if product == "Data" and rng.random() < 0.5:
                lines.append(("data", round(rng.choice([2500, 4800, 7500]) * scale, 2),
                              f"Data usage - {m:%b %Y}"))
            for cat, net, desc in lines:
                tax_rate = TAX[entity] or (SALES_TAX_INC if cat == "hardware" else 0.0)
                inv = Invoice(next_inv(entity, issue), cid, entity, issue,
                              issue + timedelta(days=terms), cur, net,
                              round(net * tax_rate, 2), cat, "new", desc)
                ds.invoices.append(inv)
                ds.revenue.append(RevenueLine(cid, m.strftime("%Y-%m"), cat, net, cur, inv.id))

        # payments
        pay_seq = 0
        for inv in [i for i in ds.invoices if i.customer_id == cid]:
            age = (as_of - inv.due_date).days
            if age > 30 and rng.random() < unpaid_p:
                continue
            paid_on = inv.due_date + timedelta(days=max(-5, int(rng.gauss(late_mean, late_mean / 2 + 3))))
            if paid_on > as_of:
                continue
            pay_seq += 1
            amount = inv.total
            if profile in ("disputed", "chronic") and rng.random() < 0.3:
                amount = round(inv.total * rng.choice([0.3, 0.5, 0.7]), 2)
            ds.payments.append(Payment(f"{cid}-p{pay_seq}", cid, paid_on, cur, amount,
                                       "payment", inv.id, f"WIRE-{rng.randint(100000, 999999)}"))
        if profile in ("disputed", "slow") and rng.random() < 0.7:
            d = as_of - timedelta(days=rng.randint(5, 60))
            ds.payments.append(Payment(f"{cid}-cr1", cid, d, cur, round(rng.choice([500, 1200, 2500]) * scale, 2),
                                       "credit", None, "Credit note - service credit"))
        if profile == "chronic" and rng.random() < 0.6:
            d = as_of - timedelta(days=rng.randint(10, 40))
            ds.payments.append(Payment(f"{cid}-pa1", cid, d, cur, round(rng.choice([2000, 5000]) * scale, 2),
                                       "payment", None, "Payment on account (unapplied)"))

        ds.contracts += [
            ContractTerm(cid, "Master agreement", f"{product} services agreement",
                         f"Term 24 months · Net {terms} · auto-renew"),
            ContractTerm(cid, "Price list", "Unit pricing",
                         "Subscription per unit / month · HW per device · volume tiers"),
        ]
        if profile == "disputed":
            ds.contracts.append(ContractTerm(cid, "Amendment", "SLA credit clause",
                                             "Service credits up to 10% of monthly fee"))


    _actions(ds, as_of, rng)
    return ds


SYMBOL = {"USD": "$", "EUR": "€", "ILS": "₪"}


def _money(amount: float, cur: str) -> str:
    return f"{SYMBOL.get(cur, cur + ' ')}{amount:,.0f}"


def _actions(ds: Dataset, as_of: date, rng: random.Random) -> None:
    """Up Next items. The first three are derived from the data, so their
    figures always match Receivables and Dunning; the rest are fictional context."""
    from ..aging import dunning, open_items

    cid = {c.name.split()[0]: c.id for c in ds.customers}
    items = open_items(ds, as_of)
    overdue = {(g["customer_id"], g["currency"]): g for g in dunning(ds, items)}
    disputed = {cid["Juniper"]}
    out: list[tuple] = []   # (kind, customer_id, urgency, title, body, tag)

    # 1. Escalate the largest overdue exposure that is 60+ days late (disputes are handled separately).
    worst = max((g for g in overdue.values() if g["max_days"] >= 60 and g["customer_id"] not in disputed),
                key=lambda g: g["total"], default=None)
    if worst:
        n = len(worst["invoices"])
        out.append(("action", worst["customer_id"], "high",
                    f"Escalate {_money(worst['total'], worst['currency'])} overdue",
                    f"{n} invoice{'s' if n > 1 else ''}, oldest {worst['max_days']} days late. Send a final notice, "
                    "copy the account owner, and put new orders on credit hold until a payment date is agreed.",
                    "Escalation"))

    # 2. Unapplied cash on an account that also has overdue invoices: match before chasing.
    cash = [p for p in ds.payments if p.invoice_id is None and p.kind == "payment" and p.date <= as_of
            and (p.customer_id, p.currency) in overdue]
    if cash:
        p = max(cash, key=lambda x: x.amount)
        g = overdue[(p.customer_id, p.currency)]
        rest = max(g["total"] - p.amount, 0)
        out.append(("action", p.customer_id, "high",
                    f"Apply {_money(p.amount, p.currency)} unapplied payment",
                    f"Received {p.date.day} {p.date:%b} with no remittance advice while {_money(g['total'], p.currency)} is overdue. "
                    f"Ask AP which invoices it covers; applying it cuts past due to {_money(rest, p.currency)} "
                    "before anyone sends a reminder.",
                    "Cash application"))

    # 3. Annual license renewing within ~5 months: quote and invoice ahead of the new term.
    renewals = []
    for inv in ds.invoices:
        if inv.kind == "deferred":
            end = date(inv.issue_date.year + 1, inv.issue_date.month, min(inv.issue_date.day, 28))
            if 0 <= (end - as_of).days <= 150:
                renewals.append((end, inv))
    if renewals:
        end, inv = min(renewals, key=lambda x: x[0])
        out.append(("action", inv.customer_id, "medium",
                    f"Renewal due {end.day} {end:%b %Y}: {_money(inv.total, inv.currency)} license",
                    f"Annual data license ends in {(end - as_of).days} days. Send the renewal quote now and issue the "
                    "invoice 30 days before the new term, so payment falls due as the new term starts.",
                    "Renewal"))

    # Fictional context: actions without figures, then digest.
    pay_run = as_of + timedelta(days=3)
    out += [
        ("action", cid["Juniper"], "medium", "Close the SLA credit dispute",
         "Customer is short-paying invoices against the SLA clause. Agree the credit amount with the account owner, "
         "issue one credit note, and ask for the remaining balance in the same email.", "Dispute"),
        ("action", cid["Harbor"], "medium", f"Confirm promised payment on {pay_run.day} {pay_run:%b}",
         "AP promised to include the oldest invoices in their next payment run. Check receipts that day; "
         "if nothing arrives, call rather than email.", "Promise to pay"),
        ("action", cid["Meridian"], "low", "Resubmit invoice through the supplier portal",
         "The city's portal rejected the latest invoice for a missing PO number. Resubmit with the PO; "
         "their 60-day payment clock only starts on acceptance.", "Portal rejection"),
        ("digest", cid["Cobalt"], "low", "Switched to ACH auto-debit",
         "Payments now settle on the due date automatically. Expect this account to drop out of dunning.", "Payment method"),
        ("digest", cid["Ember"], "medium", "Fleet expansion next quarter",
         "Adding roughly 40% more units. Usage invoices will grow; check the credit limit before the first larger invoice.",
         "Growth"),
        ("digest", cid["Quillstone"], "low", "Year-end AP freeze from 15 Dec",
         "Their fiscal year closes 31 Dec and AP stops paying mid-December. Issue December invoices early.", "Year-end"),
        ("digest", cid["Kestrel"], "low", "New controller, new approval workflow",
         "Invoice approvals move to a new AP system next month. Confirm the new billing contact before the next reminder.",
         "Contact change"),
    ]
    for kind, customer, urg, title, body, tag in out:
        # stable id per customer + topic, so saved/dismissed state in the browser follows the item
        item_id = "wn-" + customer + "-" + "".join(ch for ch in tag.lower() if ch.isalnum())
        ds.actions.append(ActionItem(item_id, customer, kind, title, body, urg, tag,
                                     as_of - timedelta(days=rng.randint(0, 10))))
