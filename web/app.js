/* AR Dashboard UI. Reads data.json only; all data goes into the DOM as text nodes. */
'use strict';

let D = null;              // data.json
let CUST = {};             // id -> customer
const F = {};              // per-page filter state, survives re-render
const BUCKET_LABEL = { 'current': 'Current', '1-30': '1–30', '31-60': '31–60', '61-90': '61–90', '90+': '90+' };
const BUCKET_VAR = { 'current': '--b0', '1-30': '--b1', '31-60': '--b2', '61-90': '--b3', '90+': '--b4' };
const CAT_ORDER = ['subscription', 'data', 'hardware', 'adjustment'];
const CAT_VAR = { subscription: '--c1', data: '--c2', hardware: '--c3', adjustment: '--c4' };
// Revenue type = recognition timing (ASC 606 / IFRS 15). Two series -> categorical slots 1 and 2.
const TIMING_ORDER = ['over_time', 'point_in_time'];
const TIMING_LABEL = { over_time: 'Over time', point_in_time: 'Point in time' };
const TIMING_HINT = { over_time: 'ratably over the service period', point_in_time: 'on delivery' };
const TIMING_VAR = { over_time: '--c1', point_in_time: '--c2' };
const SYM = { USD: '$', EUR: '€', ILS: '₪' };

/* ---------- DOM helpers ---------- */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  append(el, kids);
  return el;
}
function s(tag, attrs, ...kids) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  setAttrs(el, attrs);
  append(el, kids);
  return el;
}
function setAttrs(el, attrs) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.setAttribute('class', v);
    else el.setAttribute(k, v === true ? '' : v);
  }
}
function append(el, kids) {
  for (const c of kids.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}
// Replace an element's children; flattens arrays and skips null/false.
function put(el, ...kids) { el.replaceChildren(); append(el, kids); return el; }
const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
// Text color that stays legible on a given fill (relative luminance threshold).
function inkOn(hex) {
  const n = parseInt(hex.replace('#', ''), 16), ch = [n >> 16, (n >> 8) & 255, n & 255].map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2] > 0.22 ? '#0b0b0b' : '#ffffff';
}

/* ---------- storage (per-viewer conveniences only) ---------- */
const store = {
  get(k, dflt) { try { const v = localStorage.getItem(k); return v == null ? dflt : JSON.parse(v); } catch (e) { return dflt; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
};

/* ---------- formatting ---------- */
function money(v, cur, dp = 2) {
  const n = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
  return (v < 0 ? '-' : '') + (SYM[cur] || cur + ' ') + n;
}
function compact(v, cur = 'USD') {
  const a = Math.abs(v);
  const str = a >= 1e6 ? (a / 1e6).toFixed(a >= 1e7 ? 1 : 2) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(a >= 1e5 ? 0 : 1) + 'K' : a.toFixed(0);
  return (v < 0 ? '-' : '') + (SYM[cur] || '') + str;
}
const usd = (v, cur) => cur === 'USD' ? v : v * (D.meta.fx_to_usd[cur] || 0);
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmtDate = iso => { if (!iso) return '—'; const [y, m, d] = iso.split('-'); return `${d} ${MON[+m - 1]} ${y.slice(2)}`; };
const ymLabel = ym => { const [y, m] = ym.split('-').map(Number); return new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }); };
const ymShort = ym => { const [y, m] = ym.split('-').map(Number); return new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'short' }) + ' ' + String(y).slice(2); };
const cap = t => t ? t[0].toUpperCase() + t.slice(1) : t;
const sum = (arr, f) => arr.reduce((a, x) => a + f(x), 0);
const uniq = arr => [...new Set(arr)];
const custName = id => (CUST[id] || {}).name || id;
const fxNote = () => 'USD equivalent at fixed rates: ' + Object.entries(D.meta.fx_to_usd).map(([c, r]) => `${c} ${r}`).join(', ');

function badge(status) {
  const icon = { paid: '✓', open: '○', partial: '◐', overdue: '!' }[status] || '';
  return h('span', { class: 'badge ' + status }, h('i', { 'aria-hidden': 'true' }, icon), cap(status));
}

/* ---------- generic table ---------- */
// cols: [{label, num?, get(row) -> string|Node}]
function table(cols, rows, opts = {}) {
  if (!rows.length) return h('div', { class: 'empty' }, opts.empty || 'No rows match the filters.');
  const thead = h('thead', {}, h('tr', {}, cols.map(c => h('th', { class: c.num ? 'num' : null }, c.label))));
  const body = h('tbody', {}, rows.map(r => h('tr', {
    class: opts.onRow ? 'click' : null,
    onclick: opts.onRow ? () => opts.onRow(r) : null,
  }, cols.map(c => h('td', { class: (c.num ? 'num ' : '') + (c.muted ? 'muted' : '') }, c.get(r))))));
  const foot = opts.totals ? h('tfoot', {}, opts.totals.map(t => h('tr', { class: 'total' }, cols.map((c, i) => h('td', { class: c.num ? 'num' : null }, t[i] ?? ''))))) : null;
  return h('div', { class: 'table-wrap' }, h('table', {}, thead, body, foot));
}

function select(id, options, onchange, label) {
  const sel = h('select', { 'aria-label': label || id, onchange: e => { F[id] = e.target.value; onchange(); } },
    options.map(([v, t]) => h('option', { value: v, selected: (F[id] ?? '') === v }, t)));
  return sel;
}
function search(id, placeholder, onchange) {
  return h('input', { type: 'search', placeholder, value: F[id] || '', 'aria-label': placeholder,
    oninput: e => { F[id] = e.target.value; onchange(); } });
}
const matches = (q, ...fields) => !q || fields.join(' ').toLowerCase().includes(q.toLowerCase());

/* ---------- tooltip ---------- */
const tip = () => document.getElementById('tip');
function showTip(evt, rows, title) {
  const t = tip();
  t.replaceChildren();
  append(t, [
    title ? h('div', { class: 'tl' }, title) : null,
    rows.map(r => r.key
      ? h('div', { class: 'row' }, h('span', { class: 'key', style: `background:${r.key}` }), h('span', { class: 'tl' }, r.label), h('b', {}, r.value))
      : h('div', {}, h('div', { class: 'tv' }, r.value), r.label ? h('div', { class: 'tl' }, r.label) : null))]);
  t.style.display = 'block';
  const rect = evt.target.getBoundingClientRect ? evt.target.getBoundingClientRect() : { left: 0, top: 0, width: 0 };
  const x = evt.clientX ?? rect.left + rect.width / 2, y = evt.clientY ?? rect.top;
  const w = t.offsetWidth, hgt = t.offsetHeight;
  t.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 12)) + 'px';
  t.style.top = Math.max(8, y - hgt - 12) + 'px';
}
const hideTip = () => { tip().style.display = 'none'; };
function hover(el, fn) {
  el.setAttribute('tabindex', '0');
  el.addEventListener('pointermove', e => fn(e));
  el.addEventListener('focus', e => fn(e));
  el.addEventListener('pointerleave', hideTip);
  el.addEventListener('blur', hideTip);
  return el;
}

/* ---------- charts (plain SVG) ---------- */
const DRAW = [];
function chartBox(draw) {
  const box = h('div', { class: 'chart' });
  DRAW.push(() => { box.replaceChildren(); draw(box, Math.max(280, box.clientWidth)); });
  requestAnimationFrame(runDraws);   // charts built by a later repaint (filters) draw once attached
  return box;
}
function legend(items) {
  return h('div', { class: 'legend' }, items.map(i => h('span', {}, h('i', { style: `background:${i.color}` }), i.label)));
}
function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.2, 1.6, 2, 2.4, 3.2, 4, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}
function topRounded(x, y, w, hgt, r) {
  r = Math.min(r, w / 2, hgt);
  return `M${x},${y + hgt}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + hgt}Z`;
}
function rightRounded(x, y, w, hgt, r) {
  r = Math.min(r, hgt / 2, w);
  return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + hgt - r}Q${x + w},${y + hgt} ${x + w - r},${y + hgt}H${x}Z`;
}

// Stacked (or single) columns over categories. series: [{label, color, values[]}]
function columns(box, W, cats, series, fmt) {
  const H = 220, padL = 52, padB = 26, padT = 8, plotW = W - padL - 4, plotH = H - padB - padT;
  const totals = cats.map((_, i) => sum(series, sr => Math.max(0, sr.values[i])));
  const max = niceMax(Math.max(...totals, 0));
  const y = v => padT + plotH - (v / max) * plotH;
  const svgEl = s('svg', { width: W, height: H, role: 'img', 'aria-label': series.map(x => x.label).join(', ') });
  for (let t = 0; t <= 4; t++) {
    const v = max * t / 4, yy = y(v);
    svgEl.append(s('line', { class: t ? 'grid' : 'base', x1: padL, x2: W - 4, y1: yy, y2: yy }));
    svgEl.append(s('text', { x: padL - 8, y: yy + 4, 'text-anchor': 'end', class: 'axis-label' }, fmt(v)));
  }
  const band = plotW / cats.length, bw = Math.min(44, band * 0.62);
  cats.forEach((c, i) => {
    const x0 = padL + i * band + (band - bw) / 2;
    let acc = 0;
    const visible = series.filter(sr => sr.values[i] > 0);
    visible.forEach((sr, j) => {
      const v = sr.values[i], top = y(acc + v), bottom = y(acc);
      const gap = j > 0 ? 2 : 0;
      const hh = Math.max(0, bottom - top - gap);
      if (hh > 0) {
        svgEl.append(j === visible.length - 1
          ? s('path', { class: 'mark', d: topRounded(x0, top, bw, hh, 4), fill: sr.color })
          : s('rect', { class: 'mark', x: x0, y: top, width: bw, height: hh, fill: sr.color }));
      }
      acc += v;
    });
    svgEl.append(s('text', { x: padL + i * band + band / 2, y: H - 8, 'text-anchor': 'middle', class: 'axis-label' }, c));
    const hit = s('rect', { x: padL + i * band, y: padT, width: band, height: plotH, fill: 'transparent', 'aria-label': c });
    hover(hit, e => showTip(e, [
      ...(series.length > 1 ? series.map(sr => ({ key: sr.color, label: sr.label, value: fmt(sr.values[i], true) })) : []),
      { value: fmt(totals[i], true), label: series.length > 1 ? 'Total' : series[0].label },
    ], c));
    svgEl.append(hit);
  });
  box.append(svgEl);
  if (series.length > 1) box.append(legend(series));
}

// Horizontal ranked bars. items: [{label, value, title?}]
function hbars(box, W, items, fmt, color, onClick) {
  const rowH = 30, labelW = Math.min(190, W * 0.38), valW = 72, plotW = W - labelW - valW;
  const max = Math.max(...items.map(i => i.value), 1);
  const svgEl = s('svg', { width: W, height: items.length * rowH + 4, role: 'img' });
  items.forEach((it, i) => {
    const y0 = i * rowH + 4, bw = Math.max(2, it.value / max * plotW);
    const g = s('g', { style: onClick ? 'cursor:pointer' : null, onclick: onClick ? () => onClick(it) : null });
    g.append(s('text', { x: 0, y: y0 + 15 }, it.label.length > 26 ? it.label.slice(0, 25) + '…' : it.label));
    g.append(s('path', { class: 'mark', d: rightRounded(labelW, y0 + 3, bw, 16, 4), fill: color }));
    g.append(s('text', { x: labelW + bw + 6, y: y0 + 15 }, fmt(it.value)));
    const hit = s('rect', { x: 0, y: y0 - 2, width: W, height: rowH, fill: 'transparent' });
    hover(hit, e => showTip(e, [{ value: fmt(it.value, true), label: it.title || it.label }]));
    g.append(hit);
    svgEl.append(g);
  });
  box.append(svgEl);
}

// 100% stacked aging bars, one row per label. rows: [{label, cur, b: {bucket: value}}]
function agingBars(box, W, rows) {
  const labelW = 48, totW = 96, plotW = W - labelW - totW, rowH = 34;
  const svgEl = s('svg', { width: W, height: rows.length * rowH, role: 'img', 'aria-label': 'Aging composition' });
  rows.forEach((r, i) => {
    const y0 = i * rowH + 6, total = sum(D.meta.buckets, b => r.b[b] || 0);
    svgEl.append(s('text', { x: 0, y: y0 + 15 }, r.label));
    let x = labelW;
    const parts = D.meta.buckets.filter(b => (r.b[b] || 0) > 0);
    parts.forEach((b, j) => {
      const v = r.b[b], w = total ? v / total * plotW : 0, gap = j < parts.length - 1 ? 2 : 0;
      const ww = Math.max(1, w - gap);
      const first = j === 0, last = j === parts.length - 1;
      let d;
      if (first && last) d = `M${x + 4},${y0}H${x + ww - 4}Q${x + ww},${y0} ${x + ww},${y0 + 4}V${y0 + 16}Q${x + ww},${y0 + 20} ${x + ww - 4},${y0 + 20}H${x + 4}Q${x},${y0 + 20} ${x},${y0 + 16}V${y0 + 4}Q${x},${y0} ${x + 4},${y0}Z`;
      else if (last) d = rightRounded(x, y0, ww, 20, 4);
      else if (first) d = `M${x + ww},${y0}H${x + 4}Q${x},${y0} ${x},${y0 + 4}V${y0 + 16}Q${x},${y0 + 20} ${x + 4},${y0 + 20}H${x + ww}Z`;
      else d = `M${x},${y0}H${x + ww}V${y0 + 20}H${x}Z`;
      const seg = s('path', { class: 'mark', d, fill: cssVar(BUCKET_VAR[b]) });
      hover(seg, e => showTip(e, [{ value: money(v, r.cur, 0), label: `${BUCKET_LABEL[b]} · ${(v / total * 100).toFixed(0)}% of ${r.label}` }]));
      svgEl.append(seg);
      const pct = v / total * 100;
      if (ww > 40) svgEl.append(s('text', { x: x + ww / 2, y: y0 + 14, 'text-anchor': 'middle', style: `fill:${inkOn(cssVar(BUCKET_VAR[b]))};pointer-events:none` }, pct.toFixed(0) + '%'));
      x += w;
    });
    svgEl.append(s('text', { x: W, y: y0 + 15, 'text-anchor': 'end', style: 'fill:var(--text);font-weight:600' }, compact(total, r.cur)));
  });
  box.append(svgEl);
  box.append(legend(D.meta.buckets.map(b => ({ label: BUCKET_LABEL[b], color: cssVar(BUCKET_VAR[b]) }))));
}

// A card holding a chart with a table-view twin.
function chartCard(title, desc, drawFn, tableFn, extra) {
  const key = 'tv:' + title;
  const body = h('div');
  const toggle = h('button', { class: 'link-btn view-toggle', onclick: () => { F[key] = !F[key]; paint(); } });
  function paint() {
    toggle.textContent = F[key] ? 'Chart view' : 'Table view';
    put(body, F[key] ? tableFn() : chartBox(drawFn));
    if (!F[key]) runDraws();
  }
  const card = h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, title), extra, toggle), desc ? h('div', { class: 'desc' }, desc) : null, body);
  toggle.textContent = F[key] ? 'Chart view' : 'Table view';
  body.append(F[key] ? tableFn() : chartBox(drawFn));
  return card;
}
function runDraws() { while (DRAW.length) DRAW.shift()(); }

function tile(k, v, n) { return h('div', { class: 'tile' }, h('div', { class: 'k' }, k), h('div', { class: 'v' }, v), n ? h('div', { class: 'n' }, n) : null); }

/* ---------- derived data ---------- */
function openInvoices() { return D.invoices.filter(i => i.open > 0.005); }
function pastDueByCustomer() {
  const m = {};
  for (const g of D.aging) m[g.customer_id] = (m[g.customer_id] || 0) + usd(g.past_due, g.currency);
  return m;
}
function customerBalance(cid) {
  const rows = D.aging.filter(g => g.customer_id === cid);
  return rows;
}

/* ---------- pages ---------- */
const PAGES = {
  overview: { title: 'Overview', sub: 'AR health and all customers', nav: 'Overview', hint: 'KPIs & customers', render: pageOverview },
  invoices: { title: 'Invoice Summary', sub: 'Invoices by month', nav: 'Invoices', hint: 'By month', render: pageInvoices },
  ar: { title: 'Receivables', sub: 'Open & overdue, by aging bucket', nav: 'Receivables', hint: 'Aging', render: pageAR },
  collection: { title: 'Collection', sub: 'Cash received', nav: 'Collection', hint: 'Cash in', render: pageCollection },
  revrec: { title: 'Revenue Recognition', sub: 'Recognized revenue by customer and month', nav: 'Revenue Rec', hint: 'By customer', render: pageRevRec },
  dunning: { title: 'Dunning', sub: 'Overdue accounts and reminder drafts', nav: 'Dunning', hint: 'Reminders', render: pageDunning },
  next: { title: "What's Next", sub: 'Actions and account digest', nav: "What's Next", hint: 'Actions', render: pageNext },
};

function pageOverview() {
  const tot = D.kpis.totals_by_currency;
  const gross = sum(Object.entries(tot), ([c, t]) => usd(t.gross, c));
  const past = sum(Object.entries(tot), ([c, t]) => usd(t.past_due, c));
  const credits = sum(Object.entries(tot), ([c, t]) => usd(t.credits, c));
  const pd = pastDueByCustomer();
  const top = Object.entries(pd).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 8)
    .map(([id, v]) => ({ id, label: custName(id), value: v }));
  const months = uniq(D.collections.map(c => c.date.slice(0, 7))).sort().slice(-10);
  const cash = months.map(m => sum(D.collections.filter(c => c.date.startsWith(m)), c => usd(c.amount, c.currency)));
  const usdFmt = (v, full) => full ? money(v, 'USD', 0) : compact(v);

  const custTable = h('div');
  const paintCust = () => put(custTable, table([
    { label: 'Company', get: c => c.name },
    { label: 'Entity', get: c => c.entity },
    { label: 'Product', get: c => c.product },
    { label: 'Contact', get: c => c.contact_name },
    { label: 'Email', get: c => c.contact_emails[0] || '' },
    { label: 'Budget code', get: c => c.budget_code, muted: true },
    { label: 'Terms', get: c => 'Net ' + c.terms_days, muted: true },
    { label: 'Open', num: true, get: c => customerBalance(c.id).map(g => money(g.gross, g.currency, 0)).join(' · ') || '—' },
    { label: 'Past due', num: true, get: c => customerBalance(c.id).filter(g => g.past_due > 0).map(g => money(g.past_due, g.currency, 0)).join(' · ') || '—' },
  ], D.customers.filter(c => (!F['ov-entity'] || c.entity === F['ov-entity']) && matches(F['ov-q'], c.name, c.contact_name, c.contact_emails.join(' '), c.product)),
  { onRow: c => go('c/' + c.id) }));
  paintCust();

  return [
    h('div', { class: 'tiles' },
      tile('Total AR', compact(gross), 'USD equivalent, all currencies'),
      tile('Past due', compact(past), gross ? `${(past / gross * 100).toFixed(0)}% of AR` : ''),
      tile('DSO', D.kpis.dso_days == null ? '—' : D.kpis.dso_days.toFixed(0) + ' days', '90-day window'),
      tile('Overdue invoices', String(D.kpis.overdue_invoices), `of ${D.kpis.open_invoices} open`),
      tile('Unapplied credits', compact(credits), 'Payments & credits on account')),
    h('div', { class: 'grid2' },
      chartCard('Aging by currency', 'Share of open AR in each bucket, native currency',
        (box, W) => agingBars(box, W, Object.entries(tot).map(([c, t]) => ({ label: c, cur: c, b: t }))),
        () => table([{ label: 'Currency', get: r => r[0] }, ...D.meta.buckets.map(b => ({ label: BUCKET_LABEL[b], num: true, get: r => money(r[1][b], r[0], 0) })),
          { label: 'Total', num: true, get: r => money(r[1].gross, r[0], 0) }], Object.entries(tot))),
      chartCard('Top past-due customers', 'USD equivalent · click a bar to open the customer',
        (box, W) => top.length ? hbars(box, W, top, usdFmt, cssVar('--c1'), it => go('c/' + it.id)) : box.append(h('div', { class: 'empty' }, 'Nothing past due.')),
        () => table([{ label: 'Customer', get: r => r.label }, { label: 'Past due (USD eq.)', num: true, get: r => money(r.value, 'USD', 0) }], top))),
    chartCard('Cash collected by month', fxNote(),
      (box, W) => columns(box, W, months.map(ymShort), [{ label: 'Collected', color: cssVar('--c1'), values: cash }], usdFmt),
      () => table([{ label: 'Month', get: r => ymLabel(r[0]) }, { label: 'Collected (USD eq.)', num: true, get: r => money(r[1], 'USD', 0) }], months.map((m, i) => [m, cash[i]]))),
    h('section', { class: 'card' },
      h('div', { class: 'card-head' }, h('h2', {}, 'All customers'), h('span', { class: 'note' }, `${D.customers.length} accounts`)),
      h('div', { class: 'filters', style: 'margin-top:10px' },
        search('ov-q', 'Search customer, email, product…', paintCust),
        select('ov-entity', [['', 'All entities'], ...uniq(D.customers.map(c => c.entity)).map(e => [e, e])], paintCust, 'Entity')),
      custTable),
  ];
}

function pageInvoices() {
  const months = uniq(D.invoices.map(i => i.month)).sort().reverse();
  const out = h('div');
  const paint = () => {
    const rows = D.invoices.filter(i =>
      (!F['inv-month'] || i.month === F['inv-month']) &&
      (!F['inv-kind'] || i.kind === F['inv-kind']) &&
      (!F['inv-status'] || i.status === F['inv-status']) &&
      matches(F['inv-q'], custName(i.customer_id), i.id, i.description))
      .sort((a, b) => b.issue_date.localeCompare(a.issue_date) || a.id.localeCompare(b.id));
    const curs = uniq(rows.map(r => r.currency)).sort();
    const strip = table([{ label: 'Open by bucket', get: c => c },
      ...D.meta.buckets.map(b => ({ label: BUCKET_LABEL[b], num: true, get: c => money(sum(rows.filter(r => r.currency === c && r.bucket === b), r => r.open), c, 0) })),
      { label: 'Total open', num: true, get: c => money(sum(rows.filter(r => r.currency === c), r => r.open), c, 0) },
      { label: 'Past due', num: true, get: c => money(sum(rows.filter(r => r.currency === c && r.bucket && r.bucket !== 'current'), r => r.open), c, 0) }], curs);
    put(out, 
      h('section', { class: 'card' }, strip),
      h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, `${rows.length} invoices`)), table([
        { label: 'Invoice #', get: i => i.id },
        { label: 'Customer', get: i => h('a', { href: '#/c/' + i.customer_id }, custName(i.customer_id)) },
        { label: 'Month', get: i => ymShort(i.month), muted: true },
        { label: 'Issued', get: i => fmtDate(i.issue_date) },
        { label: 'Due', get: i => fmtDate(i.due_date) },
        { label: 'Description', get: i => i.description },
        { label: 'Net', num: true, get: i => money(i.net, i.currency) },
        { label: 'Tax', num: true, get: i => money(i.tax, i.currency) },
        { label: 'Total', num: true, get: i => money(i.total, i.currency) },
        { label: 'Recognized', num: true, get: i => money(i.recognized, i.currency) },
        { label: 'Type', get: i => cap(i.kind) },
        { label: 'Status', get: i => badge(i.status) },
        { label: 'Open', num: true, get: i => i.open > 0 ? money(i.open, i.currency) : '—' },
      ], rows)));
  };
  paint();
  return [h('div', { class: 'filters' },
    select('inv-month', [['', 'All months'], ...months.map(m => [m, ymLabel(m)])], paint, 'Month'),
    select('inv-kind', [['', 'All types'], ['new', 'New'], ['deferred', 'Deferred']], paint, 'Type'),
    select('inv-status', [['', 'All statuses'], ['overdue', 'Overdue'], ['open', 'Open'], ['partial', 'Partial'], ['paid', 'Paid']], paint, 'Status'),
    search('inv-q', 'Search customer, invoice, description…', paint)), out];
}

function pageAR() {
  const out = h('div');
  const paint = () => {
    const q = F['ar-q'], cid = F['ar-cust'], cur = F['ar-cur'], bk = F['ar-bucket'];
    const items = openInvoices().filter(i => (!cid || i.customer_id === cid) && (!cur || i.currency === cur) &&
      (!bk || i.bucket === bk) && matches(q, custName(i.customer_id), i.id));
    const credits = bk ? [] : D.credits.filter(c => (!cid || c.customer_id === cid) && (!cur || c.currency === cur) && matches(q, custName(c.customer_id)));
    const groups = {};
    for (const i of items) {
      const k = i.customer_id + '|' + i.currency;
      const g = groups[k] || (groups[k] = { customer_id: i.customer_id, currency: i.currency, credits: 0, ...Object.fromEntries(D.meta.buckets.map(b => [b, 0])) });
      g[i.bucket] += i.open;
    }
    for (const c of credits) {
      const k = c.customer_id + '|' + c.currency;
      if (groups[k]) groups[k].credits += c.amount;
    }
    const rows = Object.values(groups).map(g => ({ ...g, gross: sum(D.meta.buckets, b => g[b]), past_due: sum(D.meta.buckets.slice(1), b => g[b]) }))
      .sort((a, b) => a.currency.localeCompare(b.currency) || b.gross - a.gross);
    const curs = uniq(rows.map(r => r.currency)).sort();
    const cols = [
      { label: 'Customer', get: g => h('a', { href: '#/c/' + g.customer_id }, custName(g.customer_id)) },
      { label: 'Cur', get: g => g.currency, muted: true },
      ...D.meta.buckets.map(b => ({ label: BUCKET_LABEL[b], num: true, get: g => g[b] ? money(g[b], g.currency, 0) : '—' })),
      { label: 'Total', num: true, get: g => money(g.gross, g.currency, 0) },
      { label: 'Past due', num: true, get: g => g.past_due ? money(g.past_due, g.currency, 0) : '—' },
      { label: 'Credits', num: true, get: g => g.credits ? money(-g.credits, g.currency, 0) : '—' },
      { label: 'Net', num: true, get: g => money(g.gross - g.credits, g.currency, 0) },
    ];
    const totals = curs.map(c => {
      const rs = rows.filter(r => r.currency === c);
      const t = k => sum(rs, r => r[k]);
      return [`Total ${c}`, '', ...D.meta.buckets.map(b => money(t(b), c, 0)), money(t('gross'), c, 0), money(t('past_due'), c, 0), money(-t('credits'), c, 0), money(t('gross') - t('credits'), c, 0)];
    });
    const unappliedOnly = credits.filter(c => !groups[c.customer_id + '|' + c.currency]);
    put(out, 
      h('div', { class: 'print-only' }, h('h2', {}, 'Accounts receivable aging'), h('div', { class: 'note' }, 'As of ' + D.meta.as_of)),
      h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Aging by customer'), h('span', { class: 'note' }, 'Native currency; totals never mix currencies')),
        table(cols, rows, { totals })),
      unappliedOnly.length ? h('section', { class: 'card' }, h('h2', {}, 'Credits with no open balance'),
        h('div', { class: 'desc' }, 'Unapplied payments or credit notes on accounts with nothing open'),
        table([{ label: 'Customer', get: c => custName(c.customer_id) }, { label: 'Credit', num: true, get: c => money(c.amount, c.currency) }], unappliedOnly)) : null,
      h('section', { class: 'card' }, h('h2', {}, `Open invoices (${items.length})`), table([
        { label: 'Invoice #', get: i => i.id },
        { label: 'Customer', get: i => custName(i.customer_id) },
        { label: 'Due', get: i => fmtDate(i.due_date) },
        { label: 'Days overdue', num: true, get: i => i.days_overdue || '—' },
        { label: 'Bucket', get: i => BUCKET_LABEL[i.bucket] },
        { label: 'Total', num: true, get: i => money(i.total, i.currency) },
        { label: 'Paid', num: true, get: i => i.paid ? money(i.paid, i.currency) : '—' },
        { label: 'Open', num: true, get: i => money(i.open, i.currency) },
      ], items.sort((a, b) => b.days_overdue - a.days_overdue))));
  };
  paint();
  const custOpts = uniq(openInvoices().map(i => i.customer_id)).sort((a, b) => custName(a).localeCompare(custName(b)));
  return [h('div', { class: 'filters' },
    search('ar-q', 'Search customer or invoice…', paint),
    select('ar-cust', [['', 'All customers'], ...custOpts.map(id => [id, custName(id)])], paint, 'Customer'),
    select('ar-cur', [['', 'All currencies'], ...uniq(D.invoices.map(i => i.currency)).sort().map(c => [c, c])], paint, 'Currency'),
    select('ar-bucket', [['', 'All buckets'], ...D.meta.buckets.map(b => [b, BUCKET_LABEL[b] + (b === 'current' ? '' : ' days')])], paint, 'Bucket'),
    h('button', { class: 'btn', onclick: () => { ['ar-q', 'ar-cust', 'ar-cur', 'ar-bucket'].forEach(k => delete F[k]); render(); } }, 'Clear'),
    h('button', { class: 'btn primary right', onclick: () => window.print() }, 'Export PDF')), out];
}

function pageCollection() {
  const months = uniq(D.collections.map(c => c.date.slice(0, 7))).sort();
  const out = h('div');
  let rows = [];
  const filtered = () => D.collections.filter(c =>
    (!F['col-ent'] || c.entity === F['col-ent']) &&
    (!F['col-cat'] || c.category === F['col-cat']) &&
    (!F['col-from'] || c.date.slice(0, 7) >= F['col-from']) &&
    (!F['col-to'] || c.date.slice(0, 7) <= F['col-to']) &&
    matches(F['col-q'], custName(c.customer_id), c.invoice_id || '', c.reference));
  const paint = () => {
    rows = filtered();
    const curs = uniq(rows.map(r => r.currency)).sort();
    put(out, 
      h('div', { class: 'tiles' }, curs.map(c => tile(`Collected ${c}`, compact(sum(rows.filter(r => r.currency === c), r => r.amount), c),
        `${rows.filter(r => r.currency === c).length} payments · net of tax ${compact(sum(rows.filter(r => r.currency === c), r => r.net), c)}`))),
      h('section', { class: 'card' }, table([
        { label: 'Entity', get: c => c.entity },
        { label: 'Payment date', get: c => fmtDate(c.date) },
        { label: 'Invoice date', get: c => fmtDate(c.invoice_date) },
        { label: 'Customer', get: c => h('a', { href: '#/c/' + c.customer_id }, custName(c.customer_id)) },
        { label: 'Product', get: c => cap(c.category) },
        { label: 'Total collected', num: true, get: c => money(c.amount, c.currency) },
        { label: 'Sales tax', num: true, get: c => money(c.tax, c.currency) },
        { label: 'Net collection', num: true, get: c => money(c.net, c.currency) },
        { label: 'Invoice #', get: c => c.invoice_id || 'Unapplied' },
        { label: 'Reference', get: c => c.reference, muted: true },
      ], rows)));
  };
  const exportCSV = () => {
    const esc = v => { const t = String(v ?? ''); return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; };
    const head = ['Entity', 'Payment Date', 'Invoice Date', 'Customer', 'Product', 'Currency', 'Total Collected', 'Sales Tax', 'Net Collection', 'Invoice #', 'Reference'];
    const lines = [head.join(',')].concat(rows.map(c => [c.entity, c.date, c.invoice_date, custName(c.customer_id), c.category, c.currency, c.amount.toFixed(2), c.tax.toFixed(2), c.net.toFixed(2), c.invoice_id, c.reference].map(esc).join(',')));
    const a = h('a', { href: URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' })), download: `collections_${D.meta.as_of}.csv` });
    document.body.append(a); a.click(); a.remove();
  };
  paint();
  return [h('div', { class: 'filters' },
    select('col-ent', [['', 'All entities'], ...uniq(D.collections.map(c => c.entity)).sort().map(e => [e, e])], paint, 'Entity'),
    select('col-cat', [['', 'All products'], ...uniq(D.collections.map(c => c.category)).sort().map(c => [c, cap(c)])], paint, 'Product'),
    select('col-from', [['', 'From: first month'], ...months.map(m => [m, 'From ' + ymLabel(m)])], paint, 'From month'),
    select('col-to', [['', 'To: last month'], ...months.map(m => [m, 'To ' + ymLabel(m)])], paint, 'To month'),
    search('col-q', 'Search customer, invoice, reference…', paint),
    h('button', { class: 'btn primary right', onclick: exportCSV }, 'Export CSV')), out];
}

function pageRevRec() {
  const months = uniq(D.revenue.map(r => r.month)).sort();
  const out = h('div');
  const paint = () => {
    const rows = D.revenue.filter(r => (!F['rr-cat'] || r.category === F['rr-cat']) &&
      (!F['rr-type'] || r.timing === F['rr-type']) && matches(F['rr-q'], custName(r.customer_id)));
    const shown = F['rr-month'] ? [F['rr-month']] : months;
    const byType = F['rr-group'] === 'type';
    const groups = byType
      ? TIMING_ORDER.filter(t => rows.some(r => r.timing === t)).map(t => ({ key: t, label: TIMING_LABEL[t], color: cssVar(TIMING_VAR[t]), test: r => r.timing === t }))
      : CAT_ORDER.filter(c => rows.some(r => r.category === c)).map(c => ({ key: c, label: cap(c), color: cssVar(CAT_VAR[c]), test: r => r.category === c }));
    const byCust = {};
    for (const r of rows) {
      const k = r.customer_id;
      (byCust[k] = byCust[k] || { customer_id: k, currency: r.currency, m: {} }).m[r.month] = (byCust[k].m[r.month] || 0) + r.amount;
    }
    const custRows = Object.values(byCust).map(c => ({ ...c, total: sum(shown, m => c.m[m] || 0) })).filter(c => c.total > 0)
      .sort((a, b) => usd(b.total, b.currency) - usd(a.total, a.currency));
    const usdFmt = (v, full) => full ? money(v, 'USD', 0) : compact(v);
    const inShown = rows.filter(r => shown.includes(r.month));
    const totalUsd = sum(inShown, r => usd(r.amount, r.currency));
    const typeTile = t => {
      const v = sum(inShown.filter(r => r.timing === t), r => usd(r.amount, r.currency));
      return tile(TIMING_LABEL[t], compact(v), (totalUsd ? `${(v / totalUsd * 100).toFixed(0)}% of recognized` : '—') + ' · ' + TIMING_HINT[t]);
    };
    const period = F['rr-month'] ? ymLabel(F['rr-month']) : `${ymLabel(months[0])} – ${ymLabel(months[months.length - 1])}`;
    put(out,
      h('div', { class: 'tiles' },
        tile('Recognized revenue', compact(totalUsd), period + ' · USD equivalent'),
        TIMING_ORDER.map(typeTile)),
      chartCard(byType ? 'Recognized revenue by revenue type' : 'Recognized revenue by category', fxNote(),
        (box, W) => columns(box, W, months.map(ymShort), groups.map(g => ({ label: g.label, color: g.color,
          values: months.map(m => sum(rows.filter(r => r.month === m && g.test(r)), r => usd(r.amount, r.currency))) })), usdFmt),
        () => table([{ label: 'Month', get: m => ymLabel(m) }, ...groups.map(g => ({ label: g.label, num: true,
          get: m => money(sum(rows.filter(r => r.month === m && g.test(r)), r => usd(r.amount, r.currency)), 'USD', 0) }))], months),
        h('label', { class: 'note' }, 'Group by ', select('rr-group', [['', 'Category'], ['type', 'Revenue type']], paint, 'Group chart by'))),
      h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'By customer'), h('span', { class: 'note' }, 'Native currency')),
        table([
          { label: 'Customer', get: c => h('a', { href: '#/c/' + c.customer_id }, custName(c.customer_id)) },
          ...shown.map(m => ({ label: ymShort(m), num: true, get: c => c.m[m] ? money(c.m[m], c.currency, 0) : '—' })),
          ...(shown.length > 1 ? [{ label: 'Total', num: true, get: c => money(c.total, c.currency, 0) }] : []),
        ], custRows)));
  };
  paint();
  return [h('div', { class: 'filters' },
    select('rr-month', [['', 'All months'], ...months.map(m => [m, ymLabel(m)])], paint, 'Month'),
    select('rr-cat', [['', 'All categories'], ...CAT_ORDER.map(c => [c, cap(c)])], paint, 'Category'),
    select('rr-type', [['', 'All revenue types'], ...TIMING_ORDER.map(t => [t, TIMING_LABEL[t]])], paint, 'Revenue type'),
    search('rr-q', 'Search customer…', paint),
    h('button', { class: 'btn', onclick: () => { ['rr-month', 'rr-cat', 'rr-type', 'rr-group', 'rr-q'].forEach(k => delete F[k]); render(); } }, 'Clear')), out];
}

function reminderText(g) {
  const c = CUST[g.customer_id] || {};
  const first = (c.contact_name || '').split(' ')[0] || 'there';
  const w1 = Math.max(11, ...g.invoices.map(r => r.invoice_id.length)), w2 = 12;
  const pad = (t, w) => String(t).padEnd(w);
  const lines = g.invoices.map(r => pad(r.invoice_id, w1) + '  ' + pad(fmtDate(r.due_date), w2) + money(r.open, g.currency));
  const rule = '-'.repeat(w1 + w2 + 16);
  const body = [
    `Hello ${first},`, '',
    'This is a friendly reminder that your account has past-due balance' + (g.invoices.length > 1 ? 's' : '') + '. ' +
    'We would appreciate your help settling the following invoice' + (g.invoices.length > 1 ? 's' : '') + ':', '',
    pad('Invoice No.', w1) + '  ' + pad('Due Date', w2) + 'Amount', rule, ...lines, rule,
    pad('TOTAL', w1 + w2 + 2) + money(g.total, g.currency), '',
    'If payment has already been sent, please reply with the remittance details so we can apply it.', '',
    'Thank you,', 'Accounts Receivable',
  ].join('\n');
  return { to: (c.contact_emails || []).join(','), subject: `Past-due invoices - ${c.name || g.customer_id}`, body };
}

function openReminder(g) {
  const m = reminderText(g);
  const to = h('input', { value: m.to }), subj = h('input', { value: m.subject }), body = h('textarea', {});
  body.value = m.body;
  const close = () => bg.remove();
  const copyBtn = h('button', { class: 'btn', onclick: async () => {
    try { await navigator.clipboard.writeText(body.value); copyBtn.textContent = 'Copied'; } catch (e) { body.select(); copyBtn.textContent = 'Press ⌘C'; }
  } }, 'Copy text');
  const bg = h('div', { class: 'modal-bg', onclick: e => { if (e.target === bg) close(); } },
    h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Reminder draft' },
      h('h2', {}, 'Reminder draft - ' + custName(g.customer_id)),
      h('label', {}, 'To'), to, h('label', {}, 'Subject'), subj, h('label', {}, 'Message'), body,
      h('div', { class: 'acts' }, h('button', { class: 'btn', onclick: close }, 'Close'), copyBtn,
        h('button', { class: 'btn primary', onclick: () => {
          location.href = 'mailto:' + encodeURIComponent(to.value).replace(/%2C/g, ',') + '?subject=' + encodeURIComponent(subj.value) + '&body=' + encodeURIComponent(body.value);
        } }, 'Open in mail app'))));
  document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); } });
  document.body.append(bg);
  body.focus();
}

function pageDunning() {
  const out = h('div');
  const paint = () => {
    const min = Number(F['dun-min'] || 1);
    const groups = D.dunning.map(g => {
      const inv = g.invoices.filter(r => r.days_overdue >= min);
      return { ...g, invoices: inv, total: sum(inv, r => r.open), max_days: Math.max(0, ...inv.map(r => r.days_overdue)) };
    }).filter(g => g.invoices.length);
    put(out, h('section', { class: 'card' }, table([
      { label: 'Customer', get: g => h('a', { href: '#/c/' + g.customer_id, onclick: e => e.stopPropagation() }, custName(g.customer_id)) },
      { label: 'Contact', get: g => (CUST[g.customer_id] || {}).contact_name || '', muted: true },
      { label: 'Invoices', num: true, get: g => g.invoices.length },
      { label: 'Max days overdue', num: true, get: g => g.max_days },
      { label: 'Total outstanding', num: true, get: g => money(g.total, g.currency) },
      { label: 'Action', get: g => h('button', { class: 'btn primary', onclick: e => { e.stopPropagation(); openReminder(g); } }, 'Draft reminder') },
    ], groups, { empty: 'No accounts overdue at this threshold.' })));
  };
  paint();
  return [h('div', { class: 'filters' },
    h('span', { class: 'note' }, 'Min days overdue:'),
    select('dun-min', [['1', '1+ days'], ['30', '30+ days'], ['60', '60+ days'], ['90', '90+ days']], paint, 'Minimum days overdue')), out];
}

function pageNext() {
  const out = h('div');
  const paint = () => {
    const saved = new Set(store.get('ar.wn.saved', [])), dismissed = new Set(store.get('ar.wn.dismissed', []));
    const showDismissed = !!F['wn-show'];
    const toggle = (key, set, id) => { set.has(id) ? set.delete(id) : set.add(id); store.set(key, [...set]); paint(); };
    const rank = { high: 0, medium: 1, low: 2 };
    const card = a => h('article', { class: 'wn' + (saved.has(a.id) ? ' saved' : '') + (dismissed.has(a.id) ? ' dismissed' : '') },
      h('div', { class: 'meta' }, a.kind === 'action' ? h('span', { class: 'urg ' + a.urgency }, a.urgency) : null,
        h('a', { href: '#/c/' + a.customer_id }, custName(a.customer_id)), a.tag ? h('span', { class: 'pill' }, a.tag) : null, a.date ? h('span', {}, fmtDate(a.date)) : null),
      h('h3', {}, a.title), h('p', {}, a.body),
      h('div', { class: 'acts' },
        h('button', { class: 'btn', onclick: () => toggle('ar.wn.saved', saved, a.id) }, saved.has(a.id) ? 'Unsave' : 'Save'),
        h('button', { class: 'btn', onclick: () => toggle('ar.wn.dismissed', dismissed, a.id) }, dismissed.has(a.id) ? 'Restore' : 'Dismiss')));
    const list = kind => D.actions.filter(a => a.kind === kind && (showDismissed || !dismissed.has(a.id)))
      .sort((a, b) => (saved.has(b.id) - saved.has(a.id)) || (rank[a.urgency] - rank[b.urgency]) || (b.date || '').localeCompare(a.date || ''));
    const acts = list('action'), dig = list('digest');
    put(out, h('div', { class: 'grid2' },
      h('section', {}, h('h2', { style: 'font-size:14px;margin-bottom:8px' }, `Actions (${acts.length})`), acts.length ? acts.map(card) : h('div', { class: 'empty' }, 'Nothing to do.')),
      h('section', {}, h('h2', { style: 'font-size:14px;margin-bottom:8px' }, `Digest (${dig.length})`), dig.length ? dig.map(card) : h('div', { class: 'empty' }, 'No news.'))));
  };
  paint();
  return [h('div', { class: 'filters' },
    h('label', { class: 'note' }, h('input', { type: 'checkbox', checked: !!F['wn-show'], onchange: e => { F['wn-show'] = e.target.checked; paint(); } }), ' Show dismissed'),
    h('span', { class: 'note' }, 'Saved and dismissed state is kept in this browser only.')), out];
}

function quarterOf(iso) { const [y, m] = iso.split('-').map(Number); return `Q${Math.ceil(m / 3)} ${y}`; }

function pageCustomer(cid) {
  const c = CUST[cid];
  if (!c) return [h('div', { class: 'empty' }, 'Unknown customer.')];
  const invs = D.invoices.filter(i => i.customer_id === cid).sort((a, b) => b.issue_date.localeCompare(a.issue_date));
  const bal = customerBalance(cid);
  const pays = D.payments.filter(p => p.customer_id === cid).sort((a, b) => b.date.localeCompare(a.date));
  const open = invs.filter(i => i.open > 0.005);
  const maxDays = Math.max(0, ...open.map(i => i.days_overdue));
  const quarters = {};
  for (const i of invs.slice().reverse()) {
    const q = quarterOf(i.issue_date);
    const g = quarters[q] || (quarters[q] = { q, n: 0, total: 0, months: new Set(), cats: new Set() });
    g.n++; g.total += i.total; g.months.add(i.month); g.cats.add(i.category);
  }
  const blocks = [
    h('div', { class: 'tiles' },
      bal.map(g => tile(`Open ${g.currency}`, money(g.gross, g.currency, 0), `Past due ${money(g.past_due, g.currency, 0)}`)),
      bal.some(g => g.credits) ? tile('Credits on account', bal.filter(g => g.credits).map(g => money(g.credits, g.currency, 0)).join(' · '), 'Unapplied') : null,
      tile('Oldest overdue', maxDays ? maxDays + ' days' : '—', `${open.length} open invoice${open.length === 1 ? '' : 's'}`),
      tile('Terms', 'Net ' + c.terms_days, c.entity + ' · ' + c.currency)),
    h('div', { class: 'grid2' },
      h('section', { class: 'card' }, h('h2', {}, 'Account'), h('dl', { class: 'kv', style: 'margin-top:10px' },
        h('dt', {}, 'Product'), h('dd', {}, c.product), h('dt', {}, 'Contact'), h('dd', {}, c.contact_name),
        h('dt', {}, 'Email'), h('dd', {}, c.contact_emails.map((e, i) => [i ? ', ' : '', h('a', { href: 'mailto:' + e }, e)])),
        h('dt', {}, 'Budget code'), h('dd', {}, c.budget_code), h('dt', {}, 'Entity'), h('dd', {}, c.entity))),
      bal.length ? chartCard('Aging', 'Open balance by bucket',
        (box, W) => agingBars(box, W, bal.map(g => ({ label: g.currency, cur: g.currency, b: g }))),
        () => table([{ label: 'Bucket', get: b => BUCKET_LABEL[b] }, ...bal.map(g => ({ label: g.currency, num: true, get: b => money(g[b], g.currency, 0) }))], D.meta.buckets))
        : h('section', { class: 'card' }, h('h2', {}, 'Aging'), h('div', { class: 'empty' }, 'Nothing open.'))),
    h('section', { class: 'card' }, h('h2', {}, 'Contract'), h('div', { class: 'desc' }, 'Key commercial terms'),
      table([{ label: 'Record type', get: t => t.record_type }, { label: 'Description', get: t => t.description }, { label: 'Key fields', get: t => t.key_fields }],
        D.contracts.filter(t => t.customer_id === cid))),
  ];
  if (c.modules.includes('usage_billing')) blocks.push(usageModule(cid));
  if (c.modules.includes('serials')) blocks.push(serialsModule(cid));
  blocks.push(
    h('section', { class: 'card' }, h('h2', {}, 'Billing by quarter'), table([
      { label: 'Quarter', get: g => g.q }, { label: 'Covers', get: g => [...g.months].map(ymShort).join(', ') },
      { label: 'Categories', get: g => [...g.cats].map(cap).join(', '), muted: true },
      { label: 'Invoices', num: true, get: g => g.n }, { label: 'Billed', num: true, get: g => money(g.total, c.currency, 0) },
    ], Object.values(quarters).reverse())),
    h('section', { class: 'card' }, h('h2', {}, `Invoices (${invs.length})`), table([
      { label: 'Invoice #', get: i => i.pdf_url ? h('a', { href: i.pdf_url, target: '_blank', rel: 'noopener' }, i.id) : i.id },
      { label: 'Issued', get: i => fmtDate(i.issue_date) }, { label: 'Due', get: i => fmtDate(i.due_date) },
      { label: 'Description', get: i => i.description },
      { label: 'Amount', num: true, get: i => money(i.total, i.currency) },
      { label: 'Status', get: i => badge(i.status) },
      { label: 'Paid', num: true, get: i => i.paid ? money(i.paid, i.currency) : '—' },
      { label: 'Open', num: true, get: i => i.open > 0 ? money(i.open, i.currency) : '—' },
    ], invs)),
    h('section', { class: 'card' }, h('h2', {}, `Payments & credits (${pays.length})`), table([
      { label: 'Date', get: p => fmtDate(p.date) }, { label: 'Kind', get: p => cap(p.kind) },
      { label: 'Applied to', get: p => p.invoice_id || 'Unapplied' }, { label: 'Reference', get: p => p.reference, muted: true },
      { label: 'Amount', num: true, get: p => money(p.amount, p.currency) },
    ], pays)));
  return blocks;
}

function usageModule(cid) {
  const batches = D.usage.filter(u => u.customer_id === cid).sort((a, b) => a.month.localeCompare(b.month));
  if (!batches.length) return null;
  const key = 'usage-' + cid;
  if (!F[key]) F[key] = batches[batches.length - 1].month;
  const calc = h('div');
  const paint = () => {
    const b = batches.find(x => x.month === F[key]) || batches[batches.length - 1];
    const units = h('input', { type: 'number', min: '0', value: b.units, style: 'width:100px' });
    const rate = h('input', { type: 'number', min: '0', step: '0.01', value: b.rate_per_unit, style: 'width:100px' });
    const res = h('div');
    const cur = CUST[cid].currency;
    const recompute = () => {
      const u = Number(units.value) || 0, r = Number(rate.value) || 0;
      const sub = Math.round((u * r + b.base_fee) * 100) / 100, tax = Math.round(sub * b.tax_rate * 100) / 100;
      put(res, table([{ label: 'Line', get: x => x[0] }, { label: 'Amount', num: true, get: x => x[1] }], [
        ['Units × rate', money(u * r, cur)], ['Base / kit fee', money(b.base_fee, cur)], ['Subtotal', money(sub, cur)],
        [`Tax (${(b.tax_rate * 100).toFixed(3).replace(/\.?0+$/, '')}%)`, money(tax, cur)], ['Total invoice', money(sub + tax, cur)],
        [`Revenue - hardware (${Math.round(b.hw_share * 100)}%)`, money(sub * b.hw_share, cur)], ['Revenue - software', money(sub * (1 - b.hw_share), cur)],
      ]));
    };
    units.addEventListener('input', recompute); rate.addEventListener('input', recompute);
    recompute();
    put(calc, h('div', { class: 'filters' },
      select(key, batches.map(x => [x.month, ymLabel(x.month)]), paint, 'Batch month'),
      h('label', { class: 'note' }, 'Units ', units), h('label', { class: 'note' }, 'Rate ', rate),
      h('span', { class: 'note' }, 'Edit to model a what-if; stored batch is unchanged.')), res);
  };
  paint();
  return h('div', { class: 'grid2' },
    h('section', { class: 'card' }, h('h2', {}, 'Usage billing calculator'), h('div', { class: 'desc' }, 'Units × rate + base fee, plus tax'), calc),
    h('section', { class: 'card' }, h('h2', {}, 'Monthly batches'), table([
      { label: 'Month', get: u => ymShort(u.month) }, { label: 'Units', num: true, get: u => u.units.toLocaleString() },
      { label: 'Subtotal', num: true, get: u => money(u.subtotal, CUST[cid].currency, 0) },
      { label: 'Total', num: true, get: u => money(u.total, CUST[cid].currency, 0) },
    ], batches.slice().reverse())));
}

function serialsModule(cid) {
  const key = 'ar.serials.' + cid;
  const box = h('div');
  const paint = () => {
    const list = store.get(key, []);
    const ta = h('textarea', { class: 'serials', placeholder: 'Paste device serials, one per line or comma-separated' });
    let armed = false;
    const clearBtn = h('button', { class: 'btn', onclick: () => {
      if (!armed) { armed = true; clearBtn.textContent = 'Click again to clear all'; return; }
      store.set(key, []); paint();
    } }, 'Clear');
    put(box, ta, h('div', { class: 'filters', style: 'margin:8px 0' },
      h('button', { class: 'btn primary', onclick: () => {
        const add = ta.value.split(/[\s,;]+/).map(x => x.trim()).filter(Boolean);
        store.set(key, uniq([...list, ...add]).sort()); paint();
      } }, 'Import'), list.length ? clearBtn : null,
      h('span', { class: 'note' }, `${list.length} serial${list.length === 1 ? '' : 's'} · kept in this browser only`)),
      list.length ? h('div', { class: 'note', style: 'font-family:ui-monospace,Menlo,monospace;max-height:160px;overflow:auto' }, list.join(', ')) : null);
  };
  paint();
  return h('section', { class: 'card' }, h('h2', {}, 'Device serials'), h('div', { class: 'desc' }, 'Serial list for this account'), box);
}

/* ---------- shell ---------- */
function go(route) { location.hash = '#/' + route; }
function currentRoute() { return (location.hash.replace(/^#\/?/, '') || 'overview'); }

function renderNav() {
  const route = currentRoute();
  put(document.getElementById('nav'), Object.entries(PAGES).map(([k, p]) =>
    h('a', { href: '#/' + k, class: route === k ? 'active' : null }, p.nav, h('small', {}, p.hint))));
  const q = (document.getElementById('cust-search').value || '').toLowerCase();
  const pd = pastDueByCustomer();
  put(document.getElementById('cust-list'), D.customers
    .filter(c => c.name.toLowerCase().includes(q))
    .sort((a, b) => a.name.localeCompare(b.name))
    .map(c => h('a', { href: '#/c/' + c.id, class: route === 'c/' + c.id ? 'active' : null, title: pd[c.id] > 0 ? 'Has past-due balance' : null },
      c.name, pd[c.id] > 0 ? h('span', { class: 'dot', 'aria-label': 'past due' }) : null)));
}

function render() {
  hideTip();
  DRAW.length = 0;
  const route = currentRoute();
  let title, sub, blocks;
  if (route.startsWith('c/')) {
    const c = CUST[route.slice(2)];
    title = c ? c.name : 'Customer'; sub = c ? `${c.entity} · ${c.product} · ${c.currency}` : '';
    blocks = pageCustomer(route.slice(2));
  } else {
    const p = PAGES[route] || PAGES.overview;
    title = p.title; sub = p.sub; blocks = p.render();
  }
  document.getElementById('page-title').textContent = title;
  document.getElementById('page-sub').textContent = sub;
  document.title = title + ' - AR Dashboard';
  const content = document.getElementById('content');
  content.replaceChildren();
  append(content, [blocks]);
  renderNav();
  runDraws();
}

function applyTheme(t) {
  if (t) document.documentElement.setAttribute('data-theme', t); else document.documentElement.removeAttribute('data-theme');
}

async function boot() {
  applyTheme(store.get('ar.theme', null));
  document.getElementById('theme-btn').addEventListener('click', () => {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark' ||
      (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
    const t = dark ? 'light' : 'dark';
    applyTheme(t); store.set('ar.theme', t); render();
  });
  try {
    const res = await fetch('data.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
    D = await res.json();
  } catch (e) {
    put(document.getElementById('content'), h('div', { class: 'empty' },
      'Could not load data.json (' + e.message + '). Run "python3 build.py" and serve the dist/ folder over HTTP.'));
    return;
  }
  CUST = Object.fromEntries(D.customers.map(c => [c.id, c]));
  document.getElementById('source-label').textContent = 'Source: ' + D.meta.source;
  document.getElementById('asof-pill').textContent = 'As of ' + fmtDate(D.meta.as_of);
  document.getElementById('version').textContent = `v${D.meta.version} · built ${D.meta.generated_at.slice(0, 10)}`;
  document.getElementById('cust-search').addEventListener('input', renderNav);
  window.addEventListener('hashchange', () => { render(); window.scrollTo(0, 0); });
  let t;
  window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(render, 150); });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', render);
  render();
}
boot();
