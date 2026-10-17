/* Reef site. No dependencies. Everything here chooses what to show; nothing here is the only copy of a fact.
   The ledger and the settings table are read from the README (one home per fact); see
   docs/design/site-information-architecture.md. */
(function () {
  'use strict';
  const REPO = 'https://github.com/MahmoudMoe/reef';
  const BLOB = REPO + '/blob/main/';
  const README_URLS = ['README.md', '../README.md', 'https://raw.githubusercontent.com/MahmoudMoe/reef/main/README.md'];
  const TABLE_HEADINGS = { ledger: 'What is enforced, and how', settings: 'Settings' };

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* ---------- theme ---------- */
  const themeBtn = $('#theme');
  if (themeBtn) themeBtn.addEventListener('click', () => {
    const root = document.documentElement;
    const dark = root.getAttribute('data-theme') === 'dark' ||
      (!root.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
    const next = dark ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('reef-theme', next); } catch (e) { /* private window */ }
  });

  /* ---------- copy buttons ---------- */
  $$('[data-copy]').forEach(btn => btn.addEventListener('click', async () => {
    const pre = btn.parentElement.querySelector('pre');
    const text = pre ? pre.textContent : '';
    try { await navigator.clipboard.writeText(text); } catch (e) {
      const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (e2) { /* nothing */ } ta.remove();
    }
    const label = btn.querySelector('span'); const old = label.textContent;
    btn.classList.add('done'); label.textContent = 'Copied';
    setTimeout(() => { btn.classList.remove('done'); label.textContent = old; }, 1600);
  }));

  /* ---------- generic tabs (situation chooser, pipeline) ---------- */
  function tablist(root) {
    const tabs = $$('[role="tab"]', root);
    const panels = tabs.map(t => document.getElementById(t.getAttribute('aria-controls')));
    function select(i, focus) {
      tabs.forEach((t, j) => { t.setAttribute('aria-selected', String(i === j)); t.tabIndex = i === j ? 0 : -1; });
      panels.forEach((p, j) => { if (p) p.hidden = i !== j; });
      if (focus) tabs[i].focus();
    }
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => select(i));
      t.addEventListener('keydown', e => {
        const n = tabs.length;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); select((i + 1) % n, true); }
        if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); select((i - 1 + n) % n, true); }
        if (e.key === 'Home') { e.preventDefault(); select(0, true); }
        if (e.key === 'End') { e.preventDefault(); select(n - 1, true); }
      });
    });
    const initial = Math.max(0, tabs.findIndex(t => t.getAttribute('aria-selected') === 'true'));
    select(initial);
  }
  $$('[role="tablist"]').forEach(tablist);

  /* ---------- scroll spy ---------- */
  const navLinks = $$('.nav a');
  const sections = navLinks.map(a => document.getElementById(a.getAttribute('href').slice(1))).filter(Boolean);
  if ('IntersectionObserver' in window && sections.length) {
    const visible = new Map();
    const io = new IntersectionObserver(entries => {
      entries.forEach(e => visible.set(e.target.id, e.isIntersecting ? e.intersectionRatio : 0));
      let best = null, bestRatio = 0;
      sections.forEach(s => { const r = visible.get(s.id) || 0; if (r > bestRatio) { best = s.id; bestRatio = r; } });
      navLinks.forEach(a => a.classList.toggle('active', best !== null && a.getAttribute('href') === '#' + best));
    }, { rootMargin: '-64px 0px -55% 0px', threshold: [0, .1, .25, .5] });
    sections.forEach(s => io.observe(s));
  }

  /* ---------- layout tree ---------- */
  const tree = $('.tree');
  if (tree) {
    const open = $('#tree-open'), close = $('#tree-close');
    if (open) open.addEventListener('click', () => $$('details', tree).forEach(d => d.open = true));
    if (close) close.addEventListener('click', () => $$('details', tree).forEach(d => d.open = false));
  }

  /* ---------- growth chart (single series, bars, hover tooltip) ---------- */
  function growthChart() {
    const host = $('#growth-chart'); const rows = $$('#growth-table tr');
    if (!host || !rows.length) return;
    const data = rows.map(r => ({
      label: r.dataset.label, growth: +r.dataset.growth, max: +r.dataset.max, alt: r.dataset.alt === '1', note: r.dataset.note || ''
    }));
    const W = 920, left = 196, right = 70, top = 10, band = 36, barH = 20, H = top + data.length * band + 34;
    const maxV = 120; const x = v => left + (v / maxV) * (W - left - right);
    const ticks = [0, 25, 50, 75, 100];
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Orchestrator context growth per session, in thousands of tokens">`;
    ticks.forEach(t => {
      svg += `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${top + data.length * band}"/>`;
      svg += `<text class="axis" x="${x(t)}" y="${top + data.length * band + 20}" text-anchor="middle">${t === 0 ? '0' : t + 'K'}</text>`;
    });
    data.forEach((d, i) => {
      const y = top + i * band + (band - barH) / 2;
      const w = Math.max(4, x(d.growth) - x(0));
      const r = 4;
      // square at the baseline, 4px rounded data-end
      const path = `M${x(0)} ${y} H${x(0) + w - r} a${r} ${r} 0 0 1 ${r} ${r} V${y + barH - r} a${r} ${r} 0 0 1 -${r} ${r} H${x(0)} Z`;
      svg += `<text class="cat" x="${left - 12}" y="${y + barH / 2 + 4}" text-anchor="end">${esc(d.label)}</text>`;
      svg += `<rect class="hit" x="${x(0)}" y="${top + i * band}" width="${W - left - right}" height="${band}" tabindex="0" data-i="${i}" aria-label="${esc(d.label)}: grew ${d.growth}k, maximum context ${d.max}k"/>`;
      svg += `<path class="bar${d.alt ? ' alt' : ''}" d="${path}" data-i="${i}"/>`;
      svg += `<text class="lbl" x="${x(0) + w + 8}" y="${y + barH / 2 + 4}">${d.growth}k</text>`;
    });
    svg += '</svg><div class="tip" role="tooltip" id="growth-tip"></div>';
    host.innerHTML = svg;
    const tip = $('#growth-tip');
    function show(i, el) {
      const d = data[i]; const box = host.getBoundingClientRect(); const b = el.getBoundingClientRect();
      tip.innerHTML = `<b>${esc(d.label)}</b><br>growth ${d.growth}k · max context ${d.max}k${d.note ? '<br>' + esc(d.note) : ''}`;
      tip.style.left = (b.left - box.left + b.width / 2) + 'px';
      tip.style.top = (b.top - box.top) + 'px';
      tip.classList.add('show');
    }
    $$('.hit', host).forEach(h => {
      const bar = () => $(`.bar[data-i="${h.dataset.i}"]`, host);
      h.addEventListener('mouseenter', () => show(+h.dataset.i, bar()));
      h.addEventListener('focus', () => show(+h.dataset.i, bar()));
      h.addEventListener('mouseleave', () => tip.classList.remove('show'));
      h.addEventListener('blur', () => tip.classList.remove('show'));
    });
  }
  growthChart();

  /* ---------- README tables: fetch, parse, render ---------- */
  function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }

  // Markdown inline → HTML. Code spans first (so * and [ inside them are literal), then links and bold.
  function inline(md) {
    const codes = [];
    let s = md.replace(/`([^`]+)`/g, (m, c) => { codes.push(c); return '\u0000' + (codes.length - 1) + '\u0000'; });
    s = esc(s);
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, t, u) => {
      const href = /^https?:/.test(u) ? u : BLOB + u.replace(/^\.?\//, '');
      return `<a href="${esc(href)}">${t}</a>`;
    });
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\u0000(\d+)\u0000/g, (m, i) => `<code>${esc(codes[+i])}</code>`);
    return s;
  }

  // Split a table row on unescaped pipes; `\|` is a literal pipe, and so is a pipe inside a code span.
  function cells(line) {
    const out = []; let cur = ''; let inCode = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '`') inCode = !inCode;
      if (c === '\\' && line[i + 1] === '|') { cur += '|'; i++; continue; }
      if (c === '|' && !inCode) { out.push(cur); cur = ''; continue; }
      cur += c;
    }
    out.push(cur);
    if (out.length && out[0].trim() === '') out.shift();
    if (out.length && out[out.length - 1].trim() === '') out.pop();
    return out.map(c => c.trim());
  }

  function tableAfterHeading(md, headingText) {
    const lines = md.split('\n');
    let i = lines.findIndex(l => /^##\s/.test(l) && l.includes(headingText));
    if (i < 0) return null;
    for (i++; i < lines.length && !lines[i].startsWith('|'); i++) if (/^##\s/.test(lines[i])) return null;
    const rows = [];
    for (; i < lines.length && lines[i].startsWith('|'); i++) rows.push(cells(lines[i]));
    if (rows.length < 2) return null;
    const header = rows[0];
    const body = rows.slice(1).filter(r => !r.every(c => /^:?-+:?$/.test(c)));
    return { header, body };
  }

  function classesOf(layerCell) {
    const t = layerCell.toLowerCase(); const out = [];
    if (/\bcode\b/.test(t)) out.push('code');
    if (t.includes('tripwire')) out.push('tripwire');
    if (t.includes('prose')) out.push('prose');
    if (t.includes('ci is the wall')) out.push('ci');
    return out;
  }

  function renderLedger(table) {
    const host = $('#ledger'); if (!host) return;
    const li = table.header.findIndex(h => /layer/i.test(h));
    const rows = table.body.map(r => {
      const layer = li >= 0 ? (r[li] || '') : (r[2] || '');
      const cls = classesOf(layer); // a row whose layer cell is blank gets no badge: the page asserts nothing the README does not
      return { rule: r[0] || '', by: r[1] || '', layer, cls };
    });
    let html = '<table class="stack"><thead><tr><th style="width:44%">Rule</th><th>Enforced by</th><th style="width:18%">Layer</th></tr></thead><tbody>';
    rows.forEach((r, i) => {
      const badges = r.cls.map(c => `<span class="badge ${c}">${c === 'ci' ? 'CI is the wall' : c}</span>`).join('');
      // The gloss is whatever the layer cell says beyond the class words themselves ("code (at turn end)").
      const plain = r.layer.replace(/\*\*/g, '');
      const rest = plain.replace(/\b(code|tripwire|prose)\b|CI is the wall/gi, '').replace(/[\s+·—-]+/g, ' ').trim();
      const gloss = rest ? `<div class="muted" style="font-size:.82rem;margin-top:4px">${inline(plain)}</div>` : '';
      html += `<tr data-i="${i}" data-cls="${r.cls.join(' ')}"><td>${inline(r.rule)}</td><td>${inline(r.by)}</td><td>${badges}${gloss}</td></tr>`;
    });
    html += '</tbody></table>';
    host.innerHTML = html;

    const trs = $$('tbody tr', host); const chips = $$('#ledger-chips .chip'); const search = $('#ledger-search'); const count = $('#ledger-count');
    const counts = { all: rows.length, code: 0, tripwire: 0, prose: 0, ci: 0 };
    rows.forEach(r => r.cls.forEach(c => counts[c]++));
    chips.forEach(ch => { const n = $('.n', ch); if (n) n.textContent = counts[ch.dataset.class]; });
    $$('[data-ledger-n]').forEach(el => el.textContent = rows.length);
    let cls = 'all';
    function apply() {
      const q = (search.value || '').trim().toLowerCase(); let shown = 0;
      trs.forEach(tr => {
        const okC = cls === 'all' || tr.dataset.cls.split(' ').includes(cls);
        const okQ = !q || tr.textContent.toLowerCase().includes(q);
        tr.hidden = !(okC && okQ); if (!tr.hidden) shown++;
      });
      count.textContent = shown === rows.length ? `${rows.length} rules` : `${shown} of ${rows.length}`;
    }
    chips.forEach(ch => ch.addEventListener('click', () => { cls = ch.dataset.class; chips.forEach(c => c.setAttribute('aria-pressed', String(c === ch))); apply(); }));
    search.addEventListener('input', apply);
    apply();
  }

  function renderSettings(table) {
    const host = $('#settings-table'); if (!host) return;
    let html = `<table><thead><tr>${table.header.map(h => `<th>${inline(h)}</th>`).join('')}</tr></thead><tbody>`;
    table.body.forEach(r => { html += `<tr>${r.map((c, i) => `<td${i === 0 ? ' style="min-width:220px"' : ''}>${inline(c)}</td>`).join('')}</tr>`; });
    html += '</tbody></table>';
    host.innerHTML = html;
    const trs = $$('tbody tr', host); const search = $('#settings-search'); const count = $('#settings-count');
    function apply() {
      const q = (search.value || '').trim().toLowerCase(); let shown = 0;
      trs.forEach(tr => { tr.hidden = !!q && !tr.textContent.toLowerCase().includes(q); if (!tr.hidden) shown++; });
      count.textContent = shown === trs.length ? `${trs.length} keys` : `${shown} of ${trs.length}`;
    }
    search.addEventListener('input', apply); apply();
  }

  async function fetchReadme() {
    for (const url of README_URLS) {
      try {
        const res = await fetch(url, { cache: 'no-cache' });
        if (res.ok) { const text = await res.text(); if (text.includes('# Reef')) return text; }
      } catch (e) { /* try the next */ }
    }
    return null;
  }

  async function loadReadmeTables() {
    const md = await fetchReadme();
    if (!md) return; // the sections keep their README links
    const ledger = tableAfterHeading(md, TABLE_HEADINGS.ledger);
    const settings = tableAfterHeading(md, TABLE_HEADINGS.settings);
    if (ledger) renderLedger(ledger);
    if (settings) renderSettings(settings);
    const v = md.match(/version-(\d+\.\d+\.\d+)/);
    if (v) $$('[data-version]').forEach(el => el.textContent = 'v' + v[1]);
    const n = md.match(/(\d+)\s+sabotage and contract tests/);
    if (n) $$('.proofs .n').forEach(el => { if (el.textContent.trim() === '440') el.textContent = n[1]; });
  }
  loadReadmeTables();
})();
