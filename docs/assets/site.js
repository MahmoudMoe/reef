/* Reef site. No dependencies. Everything here chooses what to show; nothing here is the only copy of a fact.
   The settings table, the hosts table and the version are read from the README (one home per fact); see
   docs/design/site-information-architecture.md. */
(function () {
  'use strict';
  const REPO = 'https://github.com/MahmoudMoe/reef';
  const BLOB = REPO + '/blob/main/';
  const README_URLS = ['README.md', '../README.md', 'https://raw.githubusercontent.com/MahmoudMoe/reef/main/README.md'];
  const TABLE_HEADINGS = { settings: 'Settings', hosts: 'Hosts' };

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

  /* ---------- the rain: a canvas behind the hero, in Reef's colours ---------- */
  function rain() {
    const cv = $('#rain'); const hero = cv && cv.parentElement; if (!cv) return;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) { cv.remove(); return; }
    const ctx = cv.getContext('2d'); const glyphs = '01REEF→✓✗§¶∞≥≤{}[]/\\|=+-*#@%$:;λΣΔΩ';
    let cols = [], size = 18, w = 0, h = 0, raf = 0, running = false;
    function resize() {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = hero.clientWidth; h = hero.clientHeight;
      cv.width = w * dpr; cv.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = '#0B1418'; ctx.fillRect(0, 0, w, h);
      const n = Math.ceil(w / size);
      cols = Array.from({ length: n }, (_, i) => ({ x: i * size, y: Math.random() * -h / size, v: 0.35 + Math.random() * 0.9, hue: Math.random() < 0.16 ? '#EF7A63' : (Math.random() < 0.08 ? '#D9A441' : '#4FB3B1') }));
      ctx.font = size + 'px "IBM Plex Mono", ui-monospace, Menlo, monospace';
    }
    function frame() {
      ctx.fillStyle = 'rgba(11,20,24,0.06)'; ctx.fillRect(0, 0, w, h);
      for (const c of cols) {
        const ch = glyphs[(Math.random() * glyphs.length) | 0]; const y = c.y * size;
        ctx.fillStyle = '#F6F2E9'; ctx.fillText(ch, c.x, y);
        ctx.fillStyle = c.hue; ctx.fillText(glyphs[(Math.random() * glyphs.length) | 0], c.x, y - size);
        c.y += c.v; if (y > h && Math.random() > 0.975) c.y = -2;
      }
      raf = requestAnimationFrame(frame);
    }
    function start() { if (!running) { running = true; raf = requestAnimationFrame(frame); } }
    function stop() { running = false; cancelAnimationFrame(raf); }
    resize(); start();
    addEventListener('resize', () => { resize(); });
    if ('IntersectionObserver' in window) new IntersectionObserver(e => e[0].isIntersecting ? start() : stop(), { threshold: 0 }).observe(hero);
    document.addEventListener('visibilitychange', () => document.hidden ? stop() : start());
  }
  rain();

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

  function renderHosts(table) {
    const host = $('#hosts-table'); if (!host) return;
    let html = `<table><thead><tr>${table.header.map(h => `<th>${inline(h)}</th>`).join('')}</tr></thead><tbody>`;
    table.body.forEach(r => { html += `<tr>${r.map((c, i) => `<td${i === 0 ? ' style="min-width:160px"' : ''}>${i === 0 ? '<strong>' + inline(c) + '</strong>' : inline(c)}</td>`).join('')}</tr>`; });
    host.innerHTML = html + '</tbody></table>';
  }

  async function fetchReadme() {
    for (const url of README_URLS) {
      try {
        const res = await fetch(url, { cache: 'no-cache' });
        if (res.ok) { const text = await res.text(); if (/badge\/version-\d/.test(text) && text.includes('## Settings')) return text; }
      } catch (e) { /* try the next */ }
    }
    return null;
  }

  async function loadReadmeTables() {
    const md = await fetchReadme();
    if (!md) return; // the sections keep their README links
    const settings = tableAfterHeading(md, TABLE_HEADINGS.settings);
    if (settings) renderSettings(settings);
    const hosts = tableAfterHeading(md, TABLE_HEADINGS.hosts);
    if (hosts) renderHosts(hosts);
    const v = md.match(/version-(\d+\.\d+\.\d+)/);
    if (v) $$('[data-version]').forEach(el => el.textContent = 'v' + v[1]);
  }
  loadReadmeTables();
})();
