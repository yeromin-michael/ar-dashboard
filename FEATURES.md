# AR Dashboard — Feature Inventory

What the rebuild must do. It was taken from the structure of the previous dashboard and contains no data, names or branding from it.

## Global
- Sidebar navigation: overview pages, then a list of customers (each customer has its own page).
- Searchable customer picker.
- Version badge in the sidebar (`vN · date · author`), stamped by `release.sh`.
- Top bar: global search + status filter.
- Multi-entity (e.g. `Inc` = US, `Ltd` = IL) and multi-currency (USD, EUR, ILS).

## Pages

### 1. All Customers (overview)
- Table: Company, Customer (entity), Product, Contact Person, Contact Email, Budget Code.
- Filters: text search (customer / email / product), entity.
- Clicking a row opens that customer's page.

### 2. Invoice Summary (by month)
- Table: Invoice #, Customer, Month, Date, Description, Net, Tax, Recognized, Type.
- Filters: month, type (New / Deferred), customer search.
- Aging strip: Current, 1–30, 31–60, 61–90, >90, Total, Non-Current.

### 3. Receivables (open & overdue)
- AR pivot: rows = customer, columns = Current | 1–30 | 31–60 | 61–90 | >90 | Grand Total | Non-Current.
- Filters: search (customer or invoice), customer, currency, bucket.
- Totals per currency (USD and EUR summed separately, not converted).
- Export to PDF (print view with an "As of" date).

### 4. Collection (cash received)
- Table: Entity, Payment Date, Invoice Date, Customer, Product, Total Collected, Sales Tax, Net Collection, Invoice #.
- Filters: entity, product category (Data / Subscription / HW / Subscription+HW), month multi-select, search.
- Export to CSV.

### 5. Revenue Recognition (by customer)
- Filters: month, category (Subscription types, Data, Hardware, Adjustments), search.
- Recognized vs. invoiced, per customer per month.

### 6. Dunning (send reminders)
- Overdue invoices grouped by customer: Customer, Invoices, Max Days Overdue, Total Outstanding, Action.
- Filter: minimum days overdue (1+ / 30+ / 60+ / 90+).
- "Send reminder" opens a pre-filled email draft (greeting with the contact's first name, an aligned table of invoice / due date / amount, a total, and a sign-off).

### 7. What's Next (actions & digest)
- **Actions**: cards with customer, urgency (high/medium/low), title, body and tag (e.g. shipment, invoice to issue).
- **Digest**: account news and context cards.
- Per card: Save / Unsave / Dismiss (kept in browser storage in the old build).

### 8. Customer page (one per customer)
- Contract summary table: Record Type, Description, Key Fields.
- Invoice history: Invoice #, Invoice Date, Due Date, Amount, Status, Paid, with links to the invoice PDFs.
- Billing schedule by quarter: Quarter, Covers.
- That customer's AR aging.
- **Usage-based billing calculator** (one customer type): for each monthly batch, units × rate per unit + kit/base fee + sales tax = total invoice, with recognized revenue split HW/SW. Month selector.
- **Device/serial list import** (one customer type): paste or import serials, kept per customer, with a clear button.

## Problems in the old build that the rebuild fixes
| Old behavior | Effect | Rebuild |
|---|---|---|
| Overdue `days` hard-coded on each row, `TODAY` a constant | Aging goes stale unless edited by hand | Days are computed from the due date and the as-of date at build time |
| All data embedded in a 250KB HTML file | Every data update means editing code, which risks leaking data | Data comes from a connector and is written to `data.json`; the UI is code only |
| ~17 hand-written customer pages | Pages drift apart; each new customer means copying HTML | One customer-page template, with optional modules switched on per customer |
| Reminder email finds the contact by matching the first word of the customer name | The wrong customer's contact can be picked up | Contacts are linked by customer ID |
| Dates stored as `dd/mm/yy` strings | Fragile to parse and sort | ISO dates throughout |
| Card state and serials kept only in browser storage | Lost on another device; can't be shared | Same for now in the portfolio build; noted as a later backend job |
| No FX handling | No single total across currencies | Totals per currency plus an optional USD view using an FX table in config |
