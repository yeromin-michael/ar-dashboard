"""Canonical AR data model. Every connector produces a Dataset of these records."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional

CURRENCIES = ("USD", "EUR", "ILS")
PAYMENT_KINDS = ("payment", "credit", "adjustment")
INVOICE_KINDS = ("new", "deferred")
URGENCIES = ("high", "medium", "low")
# Revenue type = ASC 606 / IFRS 15 recognition timing. Default per category;
# a connector may set timing explicitly per line to override it.
REVENUE_TIMINGS = ("over_time", "point_in_time")
TIMING_BY_CATEGORY = {
    "subscription": "over_time",
    "data": "over_time",
    "hardware": "point_in_time",
    "adjustment": "point_in_time",
}


@dataclass
class Customer:
    id: str
    name: str
    entity: str                      # billing entity, e.g. "Inc" or "Ltd"
    currency: str
    product: str = ""
    contact_name: str = ""
    contact_emails: list[str] = field(default_factory=list)
    budget_code: str = ""
    terms_days: int = 30
    modules: list[str] = field(default_factory=list)   # optional page modules: "usage_billing", "serials"


@dataclass
class Invoice:
    id: str
    customer_id: str
    entity: str
    issue_date: date
    due_date: date
    currency: str
    net: float
    tax: float = 0.0
    category: str = "subscription"   # subscription | data | hardware | adjustment
    kind: str = "new"                # new | deferred
    description: str = ""
    pdf_url: str = ""

    @property
    def total(self) -> float:
        return round(self.net + self.tax, 2)


@dataclass
class Payment:
    """Cash received or a credit. invoice_id=None means unapplied (on account)."""
    id: str
    customer_id: str
    date: date
    currency: str
    amount: float                    # positive = reduces what the customer owes
    kind: str = "payment"            # payment | credit | adjustment
    invoice_id: Optional[str] = None
    reference: str = ""


@dataclass
class RevenueLine:
    customer_id: str
    month: str                       # YYYY-MM
    category: str
    amount: float
    currency: str
    invoice_id: Optional[str] = None
    timing: str = ""                 # over_time | point_in_time; empty = derive from category

    def __post_init__(self):
        if not self.timing:
            self.timing = TIMING_BY_CATEGORY.get(self.category, "point_in_time")


@dataclass
class ContractTerm:
    customer_id: str
    record_type: str                 # e.g. "Master agreement", "Order form", "Price list"
    description: str
    key_fields: str = ""


@dataclass
class UsageBatch:
    """Usage-based billing: units x rate + base fee, plus tax."""
    customer_id: str
    month: str                       # YYYY-MM
    units: int
    rate_per_unit: float
    base_fee: float = 0.0
    tax_rate: float = 0.0
    hw_share: float = 0.0            # share of subtotal recognized as hardware

    @property
    def subtotal(self) -> float:
        return round(self.units * self.rate_per_unit + self.base_fee, 2)

    @property
    def tax(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.tax, 2)


@dataclass
class ActionItem:
    id: str
    customer_id: str
    kind: str                        # action | digest
    title: str
    body: str = ""
    urgency: str = "medium"
    tag: str = ""
    date: Optional[date] = None


@dataclass
class Dataset:
    customers: list[Customer] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
    revenue: list[RevenueLine] = field(default_factory=list)
    contracts: list[ContractTerm] = field(default_factory=list)
    usage: list[UsageBatch] = field(default_factory=list)
    actions: list[ActionItem] = field(default_factory=list)
    source: str = ""

    def validate(self) -> list[str]:
        """Return a list of integrity problems (empty = valid)."""
        errs: list[str] = []
        cust = {c.id: c for c in self.customers}
        if len(cust) != len(self.customers):
            errs.append("duplicate customer ids")
        inv_ids = [i.id for i in self.invoices]
        if len(set(inv_ids)) != len(inv_ids):
            errs.append("duplicate invoice ids")
        invs = {i.id: i for i in self.invoices}
        for c in self.customers:
            if c.currency not in CURRENCIES:
                errs.append(f"customer {c.id}: unknown currency {c.currency}")
        for i in self.invoices:
            if i.customer_id not in cust:
                errs.append(f"invoice {i.id}: unknown customer {i.customer_id}")
            if i.currency not in CURRENCIES:
                errs.append(f"invoice {i.id}: unknown currency {i.currency}")
            if i.due_date < i.issue_date:
                errs.append(f"invoice {i.id}: due before issue")
            if i.kind not in INVOICE_KINDS:
                errs.append(f"invoice {i.id}: unknown kind {i.kind}")
        for p in self.payments:
            if p.customer_id not in cust:
                errs.append(f"payment {p.id}: unknown customer {p.customer_id}")
            if p.kind not in PAYMENT_KINDS:
                errs.append(f"payment {p.id}: unknown kind {p.kind}")
            if p.amount <= 0:
                errs.append(f"payment {p.id}: amount must be positive (set \"negate\" in the mapping if the export shows receipts as negatives)")
            if p.invoice_id is not None:
                inv = invs.get(p.invoice_id)
                if inv is None:
                    errs.append(f"payment {p.id}: unknown invoice {p.invoice_id}")
                elif inv.currency != p.currency:
                    errs.append(f"payment {p.id}: currency differs from invoice {inv.id}")
                elif inv.customer_id != p.customer_id:
                    errs.append(f"payment {p.id}: customer differs from invoice {inv.id}")
        for r in self.revenue:
            if r.timing not in REVENUE_TIMINGS:
                errs.append(f"revenue {r.customer_id}/{r.month}: unknown revenue type {r.timing}")
        for a in self.actions:
            if a.urgency not in URGENCIES:
                errs.append(f"action {a.id}: unknown urgency {a.urgency}")
        return errs


def to_jsonable(obj):
    """Dataclass/date -> plain JSON types."""
    if hasattr(obj, "__dataclass_fields__"):
        obj = asdict(obj)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj
