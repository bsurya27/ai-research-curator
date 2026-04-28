// Three-level flow:
//   L0: short story + birds-eye diagram (CA, RA, you, briefing).
//   L1: data-flow overview with numbered steps.
//   L2: zoom into a connection; cycle arrows are clickable for dimmed focus,
//       technical notes, and a GitHub link to the exact call site (line anchor).
// Canvas supports pan (drag) and zoom (wheel) via d3.zoom.

(function () {
  const svg = d3.select('#canvas');
  const mainEl = document.getElementById('main');
  const canvasWrap = document.getElementById('canvas-wrap');
  const l0View = document.getElementById('l0-view');
  const l0DiagramHost = document.getElementById('l0-diagram-host');
  const panel = document.getElementById('panel-content');
  const breadcrumb = document.getElementById('breadcrumb');
  const resetBtn = document.getElementById('reset-view');
  const ctaL0 = document.getElementById('l0-cta');
  const elLegendL0 = document.getElementById('legend-l0');
  const elLegendL1 = document.getElementById('legend-l1');
  const canvasNode = svg.node();

  const VBW = 1600;
  const VBH = 900;

  svg.attr('viewBox', `0 0 ${VBW} ${VBH}`)
     .attr('preserveAspectRatio', 'xMidYMid meet');

  // ─── DEFS ────────────────────────────────────────────────────────────────
  const defs = svg.append('defs');

  const gradients = {
    agent:    ['#ff6b9d', '#c06cf2'],
    service:  ['#00d4ff', '#5b7fff'],
    external: ['#52e2a0', '#2fb37a'],
    storage:  ['#8888a0', '#4a4a5a'],
    briefing: ['#ffd787', '#ff9e5e'],
    user:     ['#ffa96e', '#ff6b4e'],
    data:     ['#7a7a95', '#45455a'],
  };

  Object.entries(gradients).forEach(([cat, [c1, c2]]) => {
    const g = defs.append('linearGradient')
      .attr('id', `grad-${cat}`)
      .attr('x1', '0%').attr('y1', '0%')
      .attr('x2', '100%').attr('y2', '100%');
    g.append('stop').attr('offset', '0%').attr('stop-color', c1);
    g.append('stop').attr('offset', '100%').attr('stop-color', c2);
  });

  const glow = defs.append('filter')
    .attr('id', 'glow').attr('x', '-50%').attr('y', '-50%')
    .attr('width', '200%').attr('height', '200%');
  glow.append('feGaussianBlur').attr('stdDeviation', '5').attr('result', 'blur');
  const gm = glow.append('feMerge');
  gm.append('feMergeNode').attr('in', 'blur');
  gm.append('feMergeNode').attr('in', 'SourceGraphic');

  // Drop shadow under L2 cards for visual depth
  const shadow = defs.append('filter')
    .attr('id', 'card-shadow')
    .attr('x', '-20%').attr('y', '-20%')
    .attr('width', '140%').attr('height', '140%');
  shadow.append('feDropShadow')
    .attr('dx', 0).attr('dy', 6)
    .attr('stdDeviation', 12)
    .attr('flood-color', '#000')
    .attr('flood-opacity', 0.55);

  // Inner top→bottom gradient overlay for "lit from above" depth
  const innerGrad = defs.append('linearGradient')
    .attr('id', 'card-inner').attr('x1', '0%').attr('y1', '0%')
    .attr('x2', '0%').attr('y2', '100%');
  innerGrad.append('stop').attr('offset', '0%').attr('stop-color', 'rgba(255, 255, 255, 0.05)');
  innerGrad.append('stop').attr('offset', '60%').attr('stop-color', 'rgba(255, 255, 255, 0)');
  innerGrad.append('stop').attr('offset', '100%').attr('stop-color', 'rgba(0, 0, 0, 0.18)');

  // Subtle dot-grid pattern for box backgrounds
  const dotPat = defs.append('pattern')
    .attr('id', 'dot-grid')
    .attr('width', 16).attr('height', 16)
    .attr('patternUnits', 'userSpaceOnUse');
  dotPat.append('circle')
    .attr('cx', 1).attr('cy', 1).attr('r', 0.7)
    .attr('fill', 'rgba(255, 255, 255, 0.04)');

  function mkArrow(id, refX, fill) {
    defs.append('marker')
      .attr('id', id).attr('viewBox', '0 -5 10 10')
      .attr('refX', refX).attr('refY', 0)
      .attr('markerWidth', 7).attr('markerHeight', 7)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M0,-4 L8,0 L0,4').attr('fill', fill);
  }
  mkArrow('arrow',      8, 'rgba(255, 255, 255, 0.5)');
  mkArrow('arrow-pref', 6, '#ff6b9d');
  defs.append('marker')
    .attr('id', 'arrow-bi-start').attr('viewBox', '0 -5 10 10')
    .attr('refX', 2).attr('refY', 0)
    .attr('markerWidth', 7).attr('markerHeight', 7)
    .attr('orient', 'auto-start-reverse')
    .append('path').attr('d', 'M0,-4 L8,0 L0,4').attr('fill', 'rgba(255, 255, 255, 0.5)');

  // ─── PAN / ZOOM ──────────────────────────────────────────────────────────
  const viewport = svg.append('g').attr('class', 'viewport');
  const sceneRoot = viewport.append('g').attr('class', 'scene');

  const zoom = d3.zoom()
    .scaleExtent([0.4, 3])
    .on('zoom', (event) => {
      viewport.attr('transform', event.transform);
    });

  svg.call(zoom).on('dblclick.zoom', null);

  function resetView() {
    svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity);
  }
  resetBtn.addEventListener('click', resetView);

  // ─── STATE / NAV ─────────────────────────────────────────────────────────
  const state = { level: 'L0', number: null, focusId: null };
  let navSeq = 0;

  function getConn(n) { return CONNECTIONS.find(c => c.number === n); }

  /** Next/prev connection (1-based), wrapping 7→1 and skipping entries that share the same l2 scene object. */
  function adjacentL2Connection(fromNum, delta) {
    const len = CONNECTIONS.length;
    if (len < 1 || fromNum == null) return null;
    const cur = getConn(fromNum);
    if (!cur) return null;
    const startL2 = cur.l2;
    let n = fromNum;
    for (let i = 0; i < len; i++) {
      n = ((n - 1 + delta + len) % len) + 1;
      if (getConn(n).l2 !== startL2) return n;
    }
    return null;
  }

  // JS-driven chase for L2 cycle scenes — single setInterval ticks a `.lit`
  // class across the arrow groups so every element (arrow, ring, num, caption)
  // flips state on the exact same frame.
  let cycleTimerId = null;
  function clearCycleChase() {
    if (cycleTimerId !== null) {
      clearInterval(cycleTimerId);
      cycleTimerId = null;
    }
  }

  function githubLineUrl(relPath, line) {
    const base = REPO_BASE.endsWith('/') ? REPO_BASE : `${REPO_BASE}/`;
    return `${base}${relPath}#L${line}`;
  }

  function refreshL2Dimming() {
    sceneRoot.classed('l2-dim', !!state.focusId);
    sceneRoot.selectAll('.cycle-arrow-group').each(function () {
      const g = d3.select(this);
      const id = g.attr('data-arrow-id');
      g.classed('dimmed', !!state.focusId && id !== state.focusId)
        .classed('focused', !!state.focusId && id === state.focusId);
    });
  }

  function startCycleChaseFromDom() {
    clearCycleChase();
    if (state.level !== 'L2' || state.focusId) return;
    const c = getConn(state.number);
    if (!c || !c.l2 || c.l2.type !== 'cycle') return;
    const nodes = sceneRoot.selectAll('.cycle-arrow-group').nodes();
    if (!nodes.length) return;
    const PER_STEP_MS = 1000;
    let active = 0;
    const tick = () => {
      nodes.forEach((node, i) => { d3.select(node).classed('lit', i === active); });
      active = (active + 1) % nodes.length;
    };
    tick();
    cycleTimerId = setInterval(tick, PER_STEP_MS);
  }

  function clearL2Focus() {
    if (!state.focusId) return;
    state.focusId = null;
    refreshL2Dimming();
    updatePanel();
    startCycleChaseFromDom();
  }

  function setL2Focus(arrowId) {
    state.focusId = arrowId;
    clearCycleChase();
    sceneRoot.selectAll('.cycle-arrow-group').classed('lit', false);
    refreshL2Dimming();
    updatePanel();
  }

  sceneRoot.on('click.l2clear', (event) => {
    if (state.level !== 'L2' || !state.focusId) return;
    if (event.target === sceneRoot.node()) clearL2Focus();
  });

  function setHashForState() {
    const h = state.level === 'L0' ? '#L0'
      : state.level === 'L1' ? '#L1'
      : '#L2-' + state.number;
    if (location.hash !== h) {
      try { history.replaceState(null, '', h); } catch (e) { /* e.g. file:// */ }
    }
  }

  function fillL0Copy() {
    if (typeof L0 === 'undefined' || !L0) return;
    document.getElementById('l0-title').textContent = L0.title;
    document.getElementById('l0-story').textContent = L0.story;
    document.getElementById('l0-foot').textContent = L0.footnote;
    ctaL0.textContent = L0.cta;
    ctaL0.onclick = () => goTo('L1');
  }

  function syncLayoutToLevel() {
    document.body.dataset.vizLevel = state.level;
    if (state.level === 'L0') {
      mainEl.classList.add('l0');
      fillL0Copy();
      l0View.removeAttribute('hidden');
      l0DiagramHost.appendChild(canvasNode);
    } else {
      mainEl.classList.remove('l0');
      l0View.setAttribute('hidden', '');
      const controls = canvasWrap.querySelector('.canvas-controls');
      if (canvasNode.parentNode !== canvasWrap) {
        canvasWrap.insertBefore(canvasNode, controls);
      }
    }
    const is0 = state.level === 'L0';
    if (elLegendL0) elLegendL0.hidden = !is0;
    if (elLegendL1) elLegendL1.hidden = is0;
  }

  function goTo(level, number) {
    navSeq++;
    const mySeq = navSeq;

    clearCycleChase();
    state.focusId = null;

    // Fade-out then clear then redraw
    const prev = sceneRoot.selectAll('*');
    prev.transition().duration(180).style('opacity', 0).remove();

    state.level = level;
    state.number = number ?? null;

    syncLayoutToLevel();

    setTimeout(() => {
      if (mySeq !== navSeq) return;
      sceneRoot.attr('opacity', 0);
      if (state.level === 'L0') renderL0();
      else if (state.level === 'L1') renderL1();
      else if (state.level === 'L2') renderL2(getConn(state.number));
      sceneRoot.transition().duration(240).attr('opacity', 1);
      resetView();
    }, 180);

    updateBreadcrumb();
    updatePanel();
    setHashForState();
  }

  function updateBreadcrumb() {
    breadcrumb.innerHTML = '';
    const add = (label, onclick, active) => {
      const b = document.createElement('button');
      b.className = 'crumb' + (active ? ' active' : '');
      b.textContent = label;
      if (onclick) b.onclick = onclick;
      breadcrumb.appendChild(b);
    };
    const sep = () => {
      const s = document.createElement('span');
      s.className = 'sep'; s.textContent = '›';
      breadcrumb.appendChild(s);
    };

    add('Intro', () => goTo('L0'), state.level === 'L0');
    sep();
    add('Overview', () => goTo('L1'), state.level === 'L1');
    if (state.level === 'L2') {
      sep();
      const c = getConn(state.number);
      const crumb = (c.l2 && c.l2.type === 'cycle') ? c.l2.title : c.title;
      add(crumb, null, true);
    }
  }

  function updatePanel() {
    if (state.level === 'L0') {
      panel.innerHTML = '';
      return;
    }
    if (state.level === 'L1') {
      panel.innerHTML = `
        <div class="kicker">L1 · The daily loop</div>
        <h2>${escapeHtml(L1_OVERVIEW.title)}</h2>
        <p>${escapeHtml(L1_OVERVIEW.paragraph)}</p>
        <h3>The 10 steps</h3>
        <ul class="step-list">
          ${STEPS.map(s => `
            <li data-c="${s.connection}">
              <span class="step-num">${s.n}</span>
              <span>
                <strong>${escapeHtml(s.label)}</strong>
                ${s.sum ? `<span class="step-sum">${escapeHtml(s.sum)}</span>` : ''}
              </span>
            </li>`).join('')}
        </ul>
      `;
      panel.querySelectorAll('.step-list li').forEach(li => {
        li.onclick = () => goTo('L2', +li.dataset.c);
      });
    } else if (state.level === 'L2') {
      const c = getConn(state.number);
      const scene = c.l2;
      const prevN = adjacentL2Connection(c.number, -1);
      const nextN = adjacentL2Connection(c.number, 1);
      const l2NavHtml = (prevN != null || nextN != null)
        ? `<h3>Navigate</h3>
          <div class="step-nav">
            ${prevN != null ? `<button class="nav-btn" onclick="window.__goL2(${prevN})">← ${prevN}</button>` : '<span></span>'}
            ${nextN != null ? `<button class="nav-btn" onclick="window.__goL2(${nextN})">${nextN} →</button>` : '<span></span>'}
          </div>`
        : '';
      if (scene.type === 'cycle') {
        const focused = state.focusId
          ? scene.arrows.find(a => a.id === state.focusId && a.deep)
          : null;
        if (focused) {
          const d = focused.deep;
          const href = githubLineUrl(d.source.file, d.source.line);
          const varsList = (d.vars || []).map(v => `<li><code>${escapeHtml(v)}</code></li>`).join('');
          panel.innerHTML = `
            <div class="kicker">Focused step</div>
            <h2>${escapeHtml(focused.caption)}</h2>
            <p>${escapeHtml(d.summary)}</p>
            ${d.tech ? `<p class="panel-tech">${escapeHtml(d.tech)}</p>` : ''}
            <h3>Call</h3>
            <p class="panel-call"><code>${escapeHtml(d.callLine)}</code></p>
            ${varsList ? `<h3>Names in scope</h3><ul class="var-list">${varsList}</ul>` : ''}
            <p><a class="call-site-link" href="${href}" target="_blank" rel="noopener">View this call on GitHub (${escapeHtml(d.source.file)} line ${d.source.line})</a></p>
            <p><button type="button" class="nav-btn" id="clear-arrow-focus">Clear focus</button></p>
            ${l2NavHtml}
          `;
          panel.querySelector('#clear-arrow-focus').onclick = () => clearL2Focus();
        } else {
          const arrowsHtml = scene.arrows
            .filter(a => !a.context && a.caption)
            .map(a => `
            <li>
              <span class="step-num">${a.stepNum}</span>
              <span>
                <strong>${escapeHtml(a.caption)}</strong>
              </span>
            </li>
          `).join('');
          panel.innerHTML = `
            <div class="kicker">${escapeHtml(scene.kicker || 'L2')}</div>
            <h2>${escapeHtml(scene.title)}</h2>
            <p>${escapeHtml(scene.description)}</p>
            <p class="panel-hint">Click an arrow on the canvas to dim the rest, see call-level detail, and open the exact line in GitHub.</p>
            <h3>What crosses each arrow</h3>
            <ul class="step-list">${arrowsHtml}</ul>
            ${l2NavHtml}
          `;
        }
      } else {
        const opsLines = (scene.operations || []).map(op =>
          `<li><code>${escapeHtml(op.tool)}</code><span>${escapeHtml(op.label || '')}${op.endpoint ? ' · ' + escapeHtml(op.endpoint) : ''}</span></li>`
        ).join('');
        panel.innerHTML = `
          <div class="kicker">L2 · Connection ${c.number}</div>
          <h2>${escapeHtml(c.title)}</h2>
          <p>${escapeHtml(scene.description)}</p>
          ${scene.annotation ? `<div class="annotation">${escapeHtml(scene.annotation)}</div>` : ''}
          ${opsLines ? `<h3>Operations on this connection</h3><ul class="op-list">${opsLines}</ul>` : ''}
          ${l2NavHtml}
        `;
      }
    }
  }

  window.__goL2 = (n) => goTo('L2', n);

  const CAT_LABEL = {
    agent: 'AGENT', service: 'SERVICE', external: 'EXTERNAL',
    storage: 'DATA', user: 'PERSON', data: 'DATA',
  };

  // ─── EMBEDDING SPACE GRAPHIC ─────────────────────────────────────────────
  // Scatter plot with 3 clusters + a highlighted preference arrow.
  function renderEmbeddingGraphic(parent, w, h, detail = 'small') {
    const g = parent.append('g').attr('class', 'embedding-graphic');
    // Bounding rect is drawn by caller (the node card). We just draw contents.

    // Seeded pseudo-random for consistent dot positions
    let seed = 7;
    const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };

    const clusters = [
      { cx: 0.27, cy: 0.70, n: detail === 'large' ? 16 : 10, r: 0.12, c: '#5b7fff' },
      { cx: 0.72, cy: 0.30, n: detail === 'large' ? 22 : 14, r: 0.15, c: '#00d4ff' },
      { cx: 0.50, cy: 0.50, n: detail === 'large' ? 14 : 9,  r: 0.10, c: '#8888a0' },
      { cx: 0.82, cy: 0.68, n: detail === 'large' ? 12 : 7,  r: 0.09, c: '#2fb37a' },
    ];

    const dotR = detail === 'large' ? 3.2 : 2.2;
    clusters.forEach(cl => {
      for (let i = 0; i < cl.n; i++) {
        const a = rnd() * Math.PI * 2;
        const d = Math.sqrt(rnd()) * cl.r;
        g.append('circle')
          .attr('cx', (cl.cx + Math.cos(a) * d) * w)
          .attr('cy', (cl.cy + Math.sin(a) * d) * h)
          .attr('r', dotR)
          .attr('fill', cl.c)
          .attr('opacity', 0.75);
      }
    });

    // Cluster halo (translucent) on dominant cluster
    g.append('circle')
      .attr('cx', 0.72 * w).attr('cy', 0.30 * h)
      .attr('r', 0.16 * Math.min(w, h))
      .attr('fill', 'rgba(0, 212, 255, 0.06)')
      .attr('stroke', 'rgba(0, 212, 255, 0.25)')
      .attr('stroke-width', 0.8)
      .attr('stroke-dasharray', '3 3');

    // Preference arrow from center toward the "liked" cluster
    const ox = 0.5 * w, oy = 0.5 * h;
    const tx = 0.68 * w, ty = 0.34 * h;
    g.append('line')
      .attr('x1', ox).attr('y1', oy)
      .attr('x2', tx).attr('y2', ty)
      .attr('stroke', '#ff6b9d')
      .attr('stroke-width', detail === 'large' ? 2.6 : 1.8)
      .attr('marker-end', 'url(#arrow-pref)');

    g.append('text')
      .attr('x', 0.59 * w).attr('y', 0.44 * h)
      .attr('fill', '#ff6b9d')
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('font-size', detail === 'large' ? 12 : 10)
      .attr('font-weight', 600)
      .text('preference');

    // Dim origin dot
    g.append('circle')
      .attr('cx', ox).attr('cy', oy)
      .attr('r', 3).attr('fill', '#ff6b9d').attr('opacity', 0.6);

    // Tiny axes hint (corner)
    g.append('text')
      .attr('x', w - 8).attr('y', h - 6)
      .attr('text-anchor', 'end')
      .attr('fill', 'rgba(255, 255, 255, 0.28)')
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('font-size', detail === 'large' ? 10 : 9)
      .text('ℝ¹⁵³⁶');

    return g;
  }

  // ─── L0: sketch layout — you + briefing center, CA / RA sides, notes beside agents
  function l0WrapLines(str, maxLen) {
    const words = String(str).split(/\s+/);
    const lines = [];
    let cur = '';
    words.forEach((w) => {
      const next = cur ? `${cur} ${w}` : w;
      if (next.length <= maxLen) cur = next;
      else {
        if (cur) lines.push(cur);
        cur = w;
      }
    });
    if (cur) lines.push(cur);
    return lines.slice(0, 7);
  }

  function l0DrawCallout(parent, x, y, w, lines, accent) {
    const pad = 11;
    const lh = 14;
    const hh = Math.max(86, lines.length * lh + pad * 2 + 4);
    const g = parent.append('g').attr('class', 'l0-floating-note');
    g.append('rect')
      .attr('x', x).attr('y', y).attr('width', w).attr('height', hh)
      .attr('rx', 10).attr('ry', 10)
      .attr('fill', 'rgba(12, 12, 26, 0.94)')
      .attr('stroke', accent)
      .attr('stroke-width', 1.2);
    lines.forEach((line, i) => {
      g.append('text')
        .attr('x', x + pad)
        .attr('y', y + pad + 11 + i * lh)
        .attr('fill', 'rgba(220, 222, 240, 0.95)')
        .attr('font-size', 11)
        .attr('font-family', 'Inter, system-ui, sans-serif')
        .text(line);
    });
  }

  function l0EdgeStrokeText(gg, x, y, text) {
    gg.append('text')
      .attr('class', 'l0-edge-label')
      .attr('x', x).attr('y', y)
      .attr('text-anchor', 'middle')
      .attr('fill', 'rgba(232, 234, 248, 0.92)')
      .attr('font-size', 10.5)
      .attr('stroke', 'rgba(4, 4, 14, 0.9)')
      .attr('stroke-width', 3)
      .attr('paint-order', 'stroke')
      .text(text);
  }

  /** L0 positions only; w/h/labels/shapes/categories come from L1_NODES so visuals stay in sync with L1/L2. */
  function l0NodeFromL1(id, cx, cy) {
    const n = L1_NODES.find(nn => nn.id === id);
    if (!n) return null;
    return { ...n, x: cx, y: cy };
  }

  function renderL0() {
    const g0 = sceneRoot.append('g').attr('class', 'l0-scene');
    if (typeof L0 === 'undefined' || !L0) return;

    // Hub layout: user at circle center; briefing + both agents on the ring at 120°.
    const hubX = 800;
    const hubY = 430;
    const ringR = 248;
    const rad = (deg) => (deg * Math.PI) / 180;
    const ringPos = (deg) => ({
      x: hubX + ringR * Math.cos(rad(deg)),
      y: hubY + ringR * Math.sin(rad(deg)),
    });

    const briefing = l0NodeFromL1('briefing', ringPos(-90).x, ringPos(-90).y);
    const curator = l0NodeFromL1('curator', ringPos(150).x, ringPos(150).y);
    const reporter = l0NodeFromL1('reporter', ringPos(30).x, ringPos(30).y);
    const user = l0NodeFromL1('user', hubX, hubY);

    const caLines = l0WrapLines(L0.calloutCA, 32);
    const raLines = l0WrapLines(L0.calloutRA, 32);

    g0.append('circle')
      .attr('class', 'l0-hub-ring')
      .attr('cx', hubX).attr('cy', hubY).attr('r', 92)
      .attr('fill', 'none')
      .attr('stroke', 'rgba(255, 255, 255, 0.07)')
      .attr('stroke-width', 1.2);

    // Reporter → curation: bulge *down* (negative offset — positive offset bends up
    // through the hub and reads as duplicate / “residual” strokes over other arrows).
    const arcOver = stepPath(reporter, curator, -280);
    g0.append('path')
      .attr('class', 'l0-flow-arrow')
      .attr('d', arcOver.d)
      .attr('marker-end', 'url(#arrow)');
    l0EdgeStrokeText(g0, 800, 668, 'How you reacted gets sent back');

    const caToBr = stepPath(curator, briefing, 0);
    g0.append('path')
      .attr('class', 'l0-flow-arrow')
      .attr('d', caToBr.d)
      .attr('marker-end', 'url(#arrow)');
    l0EdgeStrokeText(g0, 668, 348, 'into briefing');

    const brToRa = stepPath(briefing, reporter, 0);
    g0.append('path')
      .attr('class', 'l0-flow-arrow')
      .attr('d', brToRa.d)
      .attr('marker-end', 'url(#arrow)');
    l0EdgeStrokeText(g0, 932, 348, 'review');

    const brToUser = stepPath(briefing, user, 0);
    g0.append('path')
      .attr('class', 'l0-flow-arrow l0-warm')
      .attr('d', brToUser.d)
      .attr('marker-end', 'url(#arrow)');
    l0EdgeStrokeText(g0, 828, 308, 'read');

    const gNodes = g0.append('g').attr('class', 'nodes-layer');
    [curator, reporter, briefing, user].forEach((n) => {
      const g = gNodes.append('g')
        .datum(n)
        .attr('class', 'node')
        .attr('transform', `translate(${n.x - n.w / 2}, ${n.y - n.h / 2})`);
      if (n.shape === 'pages') renderPagesNode(g, n);
      else if (n.shape === 'person') renderPersonNode(g, n);
      else renderDefaultNode(g, n);
    });

    l0DrawCallout(g0, 268, 468, 200, caLines, 'rgba(255, 120, 170, 0.55)');
    l0DrawCallout(g0, 1132, 468, 200, raLines, 'rgba(90, 200, 255, 0.55)');
  }

  // ─── L1 ──────────────────────────────────────────────────────────────────
  function renderL1() {
    // Auto-assign a perpendicular offset to each step's arrow so that when
    // multiple steps share the same pair of modules they fan out in parallel
    // instead of piling on top of each other. Offsets are assigned in the
    // canonical (alphabetically-sorted) direction, then flipped for steps
    // drawn in the reverse direction so the three arrows actually visually
    // diverge rather than coincidentally landing on the same side.
    const SPACING = 130;
    const bucket = new Map();
    STEPS.forEach(s => {
      const key = [s.from, s.to].sort().join('|');
      if (!bucket.has(key)) bucket.set(key, []);
      bucket.get(key).push(s);
    });
    const stepOffset = new Map();
    bucket.forEach((group, key) => {
      const [canonA] = key.split('|');
      const n = group.length;
      group.sort((a, b) => a.n - b.n).forEach((s, i) => {
        let off = (i - (n - 1) / 2) * SPACING;
        if (s.from !== canonA) off = -off;  // flip for reversed direction
        stepOffset.set(s.n, off);
      });
    });

    // ── Step arrows (one per step, with offset for parallels) ────────────
    const gStepArrows = sceneRoot.append('g').attr('class', 'step-arrows-layer');
    const stepGeom = new Map();
    STEPS.forEach(s => {
      const from = L1_NODES.find(n => n.id === s.from);
      const to   = L1_NODES.find(n => n.id === s.to);
      const waypoint = s.waypoint ? L1_NODES.find(n => n.id === s.waypoint) : null;
      const geom = waypoint
        ? waypointPath(from, waypoint, to)
        : stepPath(from, to, stepOffset.get(s.n));
      stepGeom.set(s.n, geom);
      gStepArrows.append('path')
        .attr('class', `step-arrow step-arrow-${s.n}`)
        .attr('d', geom.d)
        .attr('marker-end', 'url(#arrow)')
        .style('--step-delay', `${(s.n - 1) * 1.5}s`);
    });

    // ── Module nodes ─────────────────────────────────────────────────────
    const gNodes = sceneRoot.append('g').attr('class', 'nodes-layer');
    L1_NODES.forEach(n => {
      const g = gNodes.append('g')
        .datum(n)
        .attr('class', 'node')
        .attr('transform', `translate(${n.x - n.w / 2}, ${n.y - n.h / 2})`);
      if (n.shape === 'pages')       renderPagesNode(g, n);
      else if (n.shape === 'person') renderPersonNode(g, n);
      else                           renderDefaultNode(g, n);
    });

    // ── Numbered step markers, placed at the midpoint of their arrow ─────
    const gMarks = sceneRoot.append('g').attr('class', 'marks-layer');
    STEPS.forEach(s => {
      const conn = CONNECTIONS.find(c => c.number === s.connection);
      const hosts = conn && conn.hosts || [];
      const { x: mx, y: my } = stepGeom.get(s.n).mid;

      const g = gMarks.append('g')
        .attr('class', `step-marker step-marker-${s.n}`)
        .attr('transform', `translate(${mx}, ${my})`)
        .style('cursor', 'pointer')
        .style('--step-delay', `${(s.n - 1) * 1.5}s`)
        .on('mouseover', function () {
          d3.select(this).classed('hover', true);
          d3.select(`.step-arrow-${s.n}`).classed('hover', true);
          d3.selectAll('.node').style('opacity', function (nn) {
            return hosts.includes(nn.id) ? 1 : 0.35;
          });
        })
        .on('mouseout', function () {
          d3.select(this).classed('hover', false);
          d3.select(`.step-arrow-${s.n}`).classed('hover', false);
          d3.selectAll('.node').style('opacity', 1);
        })
        .on('click', () => goTo('L2', s.connection));

      g.append('circle').attr('class', 'step-ring')
        .attr('r', 20)
        .attr('fill', 'rgba(10, 10, 20, 0.9)')
        .attr('stroke', 'rgba(255, 255, 255, 0.14)')
        .attr('stroke-width', 1.5);
      g.append('circle').attr('class', 'step-core')
        .attr('r', 15).attr('fill', '#fff');
      g.append('text').attr('class', 'step-number')
        .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
        .attr('fill', '#0a0a14')
        .attr('font-family', 'JetBrains Mono, monospace')
        .attr('font-weight', 700).attr('font-size', 12)
        .text(s.n);

      const lp = s.labelPos || 'below';
      let lx = 0, ly = 0, anchor = 'middle';
      if (lp === 'below')      { ly = 36; anchor = 'middle'; }
      else if (lp === 'above') { ly = -28; anchor = 'middle'; }
      else if (lp === 'left')  { lx = -28; ly = 4; anchor = 'end'; }
      else if (lp === 'right') { lx = 28;  ly = 4; anchor = 'start'; }

      g.append('text')
        .attr('class', 'step-label')
        .attr('x', lx).attr('y', ly)
        .attr('text-anchor', anchor)
        .text(s.label);
    });
  }

  // Quadratic-bezier path between two nodes, with perpendicular bulge = offset.
  // Parallel arrows also get their endpoints shifted along the boundary so
  // they don't all start/end at the same point.
  // Returns the path `d` plus the geometric midpoint (where the step marker sits).
  function stepPath(from, to, offset) {
    const angle = Math.atan2(to.y - from.y, to.x - from.x);
    const f0 = boundaryPoint(from, angle);
    const t0 = boundaryPoint(to, angle + Math.PI);
    const len = Math.hypot(t0.x - f0.x, t0.y - f0.y) || 1;
    const nx = -(t0.y - f0.y) / len;
    const ny =  (t0.x - f0.x) / len;
    const endShift = offset * 0.6;
    const fx = f0.x + nx * endShift, fy = f0.y + ny * endShift;
    const tx = t0.x + nx * endShift, ty = t0.y + ny * endShift;
    const mx = (fx + tx) / 2, my = (fy + ty) / 2;
    const cx = mx + nx * offset;
    const cy = my + ny * offset;
    const midx = 0.25 * fx + 0.5 * cx + 0.25 * tx;
    const midy = 0.25 * fy + 0.5 * cy + 0.25 * ty;
    return {
      d: `M ${fx} ${fy} Q ${cx} ${cy} ${tx} ${ty}`,
      mid: { x: midx, y: midy },
    };
  }

  // Polyline arrow from `from` through `waypoint` to `to`. Endpoints sit on
  // node boundaries, the middle vertex is the waypoint center. The waypoint
  // box itself will cover the line's corner, so visually the arrow looks
  // like it "enters" and "exits" the waypoint.
  function waypointPath(from, waypoint, to) {
    const a1 = Math.atan2(waypoint.y - from.y, waypoint.x - from.x);
    const f = boundaryPoint(from, a1);
    const a2 = Math.atan2(to.y - waypoint.y, to.x - waypoint.x);
    const t = boundaryPoint(to, a2 + Math.PI);
    const w = { x: waypoint.x, y: waypoint.y };
    // Marker sits along the second leg (waypoint → to) for clarity.
    return {
      d: `M ${f.x} ${f.y} L ${w.x} ${w.y} L ${t.x} ${t.y}`,
      mid: { x: (w.x + t.x) / 2, y: (w.y + t.y) / 2 },
    };
  }

  // ─── L1 NODE SHAPES ──────────────────────────────────────────────────────
  function renderDefaultNode(g, n) {
    g.append('rect')
      .attr('class', 'node-card')
      .attr('width', n.w).attr('height', n.h)
      .attr('rx', 12).attr('ry', 12)
      .attr('fill', 'rgba(20, 20, 36, 0.7)')
      .attr('stroke', `url(#grad-${n.category})`)
      .attr('stroke-width', 1.5);

    g.append('rect')
      .attr('width', 4).attr('height', n.h).attr('rx', 2)
      .attr('fill', `url(#grad-${n.category})`);

    const hasSublabel = !!n.sublabel;
    g.append('text').attr('class', 'label')
      .attr('x', 18).attr('y', hasSublabel ? 36 : n.h / 2 + 5)
      .attr('dominant-baseline', hasSublabel ? 'auto' : 'central')
      .text(n.label);
    if (hasSublabel) {
      g.append('text').attr('class', 'node-sublabel')
        .attr('x', 18).attr('y', 56).text(n.sublabel);
    }
  }

  // A "document" glyph: two page shadows behind the main page, with small
  // horizontal lines mimicking text below the title.
  function renderPagesNode(g, n) {
    const shadow = g.append('g').attr('class', 'pages-shadow');
    for (let i = 2; i >= 1; i--) {
      shadow.append('rect')
        .attr('x', i * 5).attr('y', i * 5)
        .attr('width', n.w - i * 5).attr('height', n.h - i * 5)
        .attr('rx', 8)
        .attr('fill', 'rgba(14, 14, 26, 0.85)')
        .attr('stroke', `url(#grad-${n.category})`)
        .attr('stroke-width', 1)
        .attr('opacity', 0.35);
    }

    const pw = n.w - 10, ph = n.h - 10;
    g.append('rect')
      .attr('class', 'node-card')
      .attr('width', pw).attr('height', ph)
      .attr('rx', 8)
      .attr('fill', 'rgba(20, 20, 36, 0.92)')
      .attr('stroke', `url(#grad-${n.category})`)
      .attr('stroke-width', 1.5);

    g.append('text').attr('class', 'label')
      .attr('x', 16).attr('y', 26).text(n.label);

    // Fake text lines inside the page
    const lineY0 = 42, lineGap = 11;
    const maxLines = Math.floor((ph - lineY0 - 10) / lineGap);
    for (let i = 0; i < maxLines; i++) {
      const y = lineY0 + i * lineGap;
      const w = (i % 3 === 2) ? pw - 70 : pw - 34;
      g.append('rect')
        .attr('x', 16).attr('y', y)
        .attr('width', w - 16).attr('height', 2.5)
        .attr('rx', 1.2)
        .attr('fill', 'rgba(255, 255, 255, 0.45)');
    }
  }

  // A minimal user-profile glyph: head + shoulders, on a faint backing card.
  function renderPersonNode(g, n) {
    g.append('rect')
      .attr('class', 'node-card')
      .attr('width', n.w).attr('height', n.h)
      .attr('rx', 14)
      .attr('fill', 'rgba(20, 20, 36, 0.7)')
      .attr('stroke', `url(#grad-${n.category})`)
      .attr('stroke-width', 1.5);

    const cx = n.w / 2, cy = n.h / 2 - 8;
    const grad = `url(#grad-${n.category})`;
    g.append('circle')
      .attr('cx', cx).attr('cy', cy - 14).attr('r', 11)
      .attr('fill', grad).attr('opacity', 0.9);
    g.append('path')
      .attr('d',
        `M ${cx - 22} ${cy + 22}
         Q ${cx - 22} ${cy + 2} ${cx} ${cy + 2}
         Q ${cx + 22} ${cy + 2} ${cx + 22} ${cy + 22} Z`)
      .attr('fill', grad).attr('opacity', 0.9);

    g.append('text').attr('class', 'label')
      .attr('x', cx).attr('y', n.h - 14)
      .attr('text-anchor', 'middle')
      .text(n.label);
  }

  // ─── L2 ──────────────────────────────────────────────────────────────────
  function renderL2(conn) {
    const scene = conn.l2;

    // Title banner
    const banner = sceneRoot.append('g').attr('transform', `translate(${VBW / 2}, 48)`);
    const kicker = scene.kicker
      || `CONNECTION ${conn.number} · ${scene.type === 'reasoning' ? 'INTERNAL REASONING' : 'TOOL CALLS'}`;
    const title = scene.title || conn.title;
    banner.append('text').attr('text-anchor', 'middle')
      .attr('fill', 'rgba(255, 255, 255, 0.4)')
      .attr('font-size', 11).attr('letter-spacing', '0.18em')
      .text(kicker.toUpperCase());
    banner.append('text').attr('text-anchor', 'middle').attr('y', 26)
      .attr('fill', '#fff').attr('font-size', 24).attr('font-weight', 600)
      .text(title);

    if (scene.type === 'cycle')          renderCycleScene(scene, conn);
    else if (scene.type === 'reasoning') renderReasoningScene(scene);
    else                                 renderConnectionScene(scene);
  }

  // ─── L2: cycle scene ─────────────────────────────────────────────────────
  // A shared L2 view that spans multiple L1 steps (e.g. the reporter cycle:
  // briefing → user → reporter → signals.txt). Arrows carry a plain-language
  // caption; the whole chase cycles.

  function renderCycleScene(scene, _conn) {
    const gNodes  = sceneRoot.append('g').attr('class', 'cycle-nodes');
    const gArrows = sceneRoot.append('g').attr('class', 'cycle-arrows');

    const nodeById = new Map();
    scene.nodes.forEach(n => {
      nodeById.set(n.id, n);
      const g = gNodes.append('g').datum(n).attr('class', 'node')
        .attr('transform', `translate(${n.x - n.w / 2}, ${n.y - n.h / 2})`);
      if (n.shape === 'pages')       renderPagesNode(g, n);
      else if (n.shape === 'person') renderPersonNode(g, n);
      else if (n.shape === 'label')  renderLabelNode(g, n);
      else                           renderDefaultNode(g, n);
    });

    scene.arrows.forEach(a => {
      const from = nodeById.get(a.from);
      const to   = nodeById.get(a.to);
      drawCycleArrow(gArrows, from, to, a);
    });

    if (!scene.arrows.length) return;

    if (state.focusId) refreshL2Dimming();
    else startCycleChaseFromDom();
  }

  function renderLabelNode(g, n) {
    g.append('text')
      .attr('class', 'label-node')
      .attr('x', n.w / 2)
      .attr('y', n.h / 2)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .text(n.label);
  }

  function drawCycleArrow(parent, from, to, a) {
    const angle = Math.atan2(to.y - from.y, to.x - from.x);
    const f0 = boundaryPoint(from, angle);
    const t0 = boundaryPoint(to, angle + Math.PI);
    const len = Math.hypot(t0.x - f0.x, t0.y - f0.y) || 1;
    const nx = -(t0.y - f0.y) / len;
    const ny =  (t0.x - f0.x) / len;

    // Optional perpendicular parallel shift — keeps the arrow a dead-straight
    // line, just offset from the node-center axis so stacked arrows don't overlap.
    const offset = a.offset || 0;
    const fx = f0.x + nx * offset, fy = f0.y + ny * offset;
    const tx = t0.x + nx * offset, ty = t0.y + ny * offset;

    const d  = `M ${fx} ${fy} L ${tx} ${ty}`;
    const mx = (fx + tx) / 2;
    const my = (fy + ty) / 2;

    const horizontal = Math.abs(to.x - from.x) >= Math.abs(to.y - from.y);
    const side = a.labelSide || (horizontal ? 'above' : 'left');
    const isSide = (side === 'above' || side === 'below');
    const CAP_W = a.labelW || (isSide ? 340 : 260);
    const dxOff = (a.labelOffset && a.labelOffset.dx) || 0;
    const dyOff = (a.labelOffset && a.labelOffset.dy) || 0;

    const g = parent.append('g')
      .attr('class', 'cycle-arrow-group' + (a.context ? ' context' : ''))
      .attr('data-arrow-id', a.id)
      .style('cursor', (a.context || a.deep) ? 'pointer' : 'default')
      .on('click', (event) => {
        event.stopPropagation();
        if (a.context) {
          goTo('L2', a.connection);
          return;
        }
        if (!a.deep) return;
        if (state.focusId === a.id) clearL2Focus();
        else setL2Focus(a.id);
      })
      .on('mouseover', function () { d3.select(this).classed('hover', true); })
      .on('mouseout',  function () { d3.select(this).classed('hover', false); });

    g.append('path')
      .attr('class', 'cycle-arrow' + (a.dashed ? ' dashed' : ''))
      .attr('d', d)
      .attr('marker-end', 'url(#arrow)');

    const markerG = g.append('g').attr('class', 'cycle-marker')
      .attr('transform', `translate(${mx}, ${my})`);
    markerG.append('circle').attr('class', 'cycle-ring').attr('r', 20);
    markerG.append('circle').attr('class', 'cycle-core').attr('r', 14);
    markerG.append('text').attr('class', 'cycle-num')
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
      .text(a.stepNum);

    // Caption placement by side (plain language only; no API/tool sublines)
    let capX, capY, capCls = '';
    if (side === 'above') {
      capX = mx - CAP_W / 2 + dxOff; capY = my - 82 + dyOff;
    } else if (side === 'below') {
      capX = mx - CAP_W / 2 + dxOff; capY = my + 28 + dyOff;
    } else if (side === 'right') {
      capX = mx + 34 + dxOff;        capY = my - 44 + dyOff;
      capCls = ' side-right';
    } else { // 'left' (default for vertical)
      capX = mx - CAP_W - 34 + dxOff; capY = my - 44 + dyOff;
      capCls = ' side';
    }

    const bgCls = a.labelBg ? ' with-bg' : '';
    if (a.caption) {
      const capFO = g.append('foreignObject')
        .attr('x', capX).attr('y', capY)
        .attr('width', CAP_W).attr('height', 80);
      capFO.append('xhtml:div')
        .attr('class', 'cycle-caption' + capCls + bgCls)
        .html(escapeHtml(a.caption));
    }

    return g;
  }

  // ─── L2: connection scene ────────────────────────────────────────────────
  // Two rich boxes on left/right (optionally a sink box at the bottom).
  // Tool calls live as ROWS inside the agent box. Arrows originate from each
  // row and terminate on the opposite box's edge — no labels on the arrow.
  // The arrowhead direction reflects which way the data flows.

  const HEADER_H = 96;
  const ROW_H    = 38;
  const PAD_BOT  = 28;

  function renderConnectionScene(scene) {
    const CANVAS_TOP = 130;
    const AVAIL_H = VBH - CANVAS_TOP - 40;
    const CY = CANVAS_TOP + AVAIL_H / 2;

    // Only ops that look like function calls become "tool rows".
    // UI/user events (e.g., "star click") are described in side panel only —
    // the user box's schema text already names them.
    const isFnCall = (op) => op && /^[\w.]+\(/.test(op.tool);
    const allOps = (scene.operations || []).filter(isFnCall);
    const horizOps = allOps.filter(o => o.dir === 'right' || o.dir === 'left');
    const sinkOps  = allOps.filter(o => o.dir === 'sink');

    const leftIsAgent  = scene.left.kind === 'agent';
    const rightIsAgent = scene.right.kind === 'agent';
    const rightIsGraphic = scene.right.kind === 'embedding-graphic';
    const rightIsStack   = scene.right.kind === 'external-stack';

    // Tool surface = rows shown inside the agent box. Always hosted by the
    // agent that owns the call.
    const leftSurface  = [];
    const rightSurface = [];
    horizOps.forEach(op => {
      if (leftIsAgent && !rightIsAgent) leftSurface.push(op);
      else if (rightIsAgent && !leftIsAgent) rightSurface.push(op);
      else if (op.dir === 'right') leftSurface.push(op);
      else rightSurface.push(op);
    });
    sinkOps.forEach(op => {
      if (rightIsAgent) rightSurface.push(op);
      else if (leftIsAgent) leftSurface.push(op);
    });

    function surfaceH(n) { return HEADER_H + n * ROW_H + PAD_BOT; }

    // Box dimensions
    const leftW = 340;
    const rightW = rightIsGraphic ? 500 : rightIsStack ? 360 : 340;

    let leftH  = leftSurface.length  ? surfaceH(leftSurface.length)  : 200;
    let rightH = rightSurface.length ? surfaceH(rightSurface.length) : 200;
    if (rightIsGraphic) rightH = Math.max(rightH, 380);
    if (rightIsStack)   rightH = Math.max(rightH, 280);

    // Left position. Right position is mirrored.
    const LX = 260;
    const RX = VBW - (rightW / 2 + 80);

    const left  = { x: LX,  y: CY - (leftH  / 2) + (leftH  / 2), w: leftW,  h: leftH  };
    const right = { x: RX,  y: CY - (rightH / 2) + (rightH / 2), w: rightW, h: rightH };
    // Center both vertically on the same midline:
    left.y  = CY;
    right.y = CY;

    // Render the two rich boxes
    const gBoxes = sceneRoot.append('g').attr('class', 'scene-boxes');
    renderRichBox(gBoxes, left,  scene.left,  leftSurface,  'left');
    renderRichBox(gBoxes, right, scene.right, rightSurface, 'right');

    // Optional sink box (signals.txt at the bottom for connection 7)
    let sink = null;
    if (scene.sink) {
      sink = { x: VBW / 2, y: VBH - 110, w: 380, h: 110 };
      renderRichBox(sceneRoot.append('g').attr('class', 'scene-sink'),
                    sink, scene.sink, [], 'sink');
    }

    // Draw clean arrows from each tool row to the opposite box's edge
    const gArrows = sceneRoot.insert('g', '.scene-boxes').attr('class', 'scene-arrows');

    function rowY(box, surface, op) {
      const idx = surface.indexOf(op);
      return box.y - box.h / 2 + HEADER_H + idx * ROW_H + ROW_H / 2;
    }

    horizOps.forEach(op => {
      const onLeft = leftSurface.includes(op);
      const homeBox  = onLeft ? left  : right;
      const otherBox = onLeft ? right : left;
      const surface  = onLeft ? leftSurface : rightSurface;

      const homeY = rowY(homeBox, surface, op);
      const otherY = homeY;  // straight horizontal

      const homeX = onLeft ? homeBox.x + homeBox.w / 2 : homeBox.x - homeBox.w / 2;
      const otherX = onLeft ? otherBox.x - otherBox.w / 2 : otherBox.x + otherBox.w / 2;

      drawConnectionArrow(gArrows, homeX, homeY, otherX, otherY, op);
    });

    // Sink arrows: from each sink-row in the agent box to the sink box top
    if (sink) {
      sinkOps.forEach((op, i) => {
        const onLeft = leftSurface.includes(op);
        const homeBox = onLeft ? left : right;
        const surface = onLeft ? leftSurface : rightSurface;
        const fromY = rowY(homeBox, surface, op);
        const fromX = homeBox.x + (onLeft ? -homeBox.w / 2 : homeBox.w / 2);
        const toX   = sink.x + (i - (sinkOps.length - 1) / 2) * 70;
        const toY   = sink.y - sink.h / 2;
        drawSinkArrow(gArrows, fromX, fromY, toX, toY, op);
      });
    }
  }

  // ─── Arrow renderers ─────────────────────────────────────────────────────
  function drawConnectionArrow(parent, fx, fy, tx, ty, op) {
    const cls = 'scene-edge' + (op.dashed ? ' dashed' : '');
    const line = parent.append('line')
      .attr('class', cls)
      .attr('x1', fx).attr('y1', fy)
      .attr('x2', tx).attr('y2', ty);
    // Direction is determined by op.dir, NOT by which box hosts the row.
    // op.dir === 'right' → arrowhead on the right end.
    // op.dir === 'left'  → arrowhead on the left end.
    const arrowOnRight = op.dir === 'right';
    if (fx < tx) {
      // Line drawn left-to-right: marker-end is on the right
      if (arrowOnRight) line.attr('marker-end', 'url(#arrow)');
      else              line.attr('marker-start', 'url(#arrow-bi-start)');
    } else {
      // Line drawn right-to-left: marker-end is on the left
      if (arrowOnRight) line.attr('marker-start', 'url(#arrow-bi-start)');
      else              line.attr('marker-end', 'url(#arrow)');
    }
  }

  function drawSinkArrow(parent, fx, fy, tx, ty, op) {
    const cls = 'scene-edge sink' + (op.dashed ? ' dashed' : '');
    const midY = (fy + ty) / 2;
    parent.append('path')
      .attr('class', cls)
      .attr('d', `M ${fx} ${fy} C ${fx} ${midY}, ${tx} ${midY}, ${tx} ${ty}`)
      .attr('fill', 'none')
      .attr('marker-end', 'url(#arrow)');
  }

  // ─── L2: rich box (header + body) ────────────────────────────────────────
  function renderRichBox(parent, box, party, surface, position) {
    const g = parent.append('g').attr('class', 'rich-box')
      .attr('transform', `translate(${box.x - box.w / 2}, ${box.y - box.h / 2})`);

    const cat = party.kind === 'agent' ? 'agent'
              : party.kind === 'embedding-graphic' ? 'service'
              : party.kind === 'external-stack' ? 'external'
              : party.kind === 'storage' ? 'storage'
              : party.kind === 'user' ? 'user' : 'data';
    const isAgent = party.kind === 'agent';

    // Drop shadow under the card
    g.append('rect')
      .attr('class', 'rich-box-shadow')
      .attr('width', box.w).attr('height', box.h)
      .attr('rx', 16)
      .attr('fill', 'rgba(8, 8, 16, 0.95)')
      .attr('filter', 'url(#card-shadow)');

    // Subtle dot-grid backing for texture
    g.append('rect')
      .attr('width', box.w).attr('height', box.h).attr('rx', 16)
      .attr('fill', 'url(#dot-grid)')
      .attr('pointer-events', 'none');

    // Inner top-light → bottom-shade gradient for depth
    g.append('rect')
      .attr('width', box.w).attr('height', box.h).attr('rx', 16)
      .attr('fill', 'url(#card-inner)')
      .attr('pointer-events', 'none');

    // Card border
    g.append('rect')
      .attr('class', 'rich-box-border')
      .attr('width', box.w).attr('height', box.h).attr('rx', 16)
      .attr('fill', 'none')
      .attr('stroke', `url(#grad-${cat})`)
      .attr('stroke-width', isAgent ? 2 : 1.5);

    // Glow halo on agent boxes
    if (isAgent) {
      g.append('rect')
        .attr('width', box.w).attr('height', box.h).attr('rx', 16)
        .attr('fill', 'none')
        .attr('stroke', `url(#grad-${cat})`)
        .attr('stroke-width', 1)
        .attr('opacity', 0.35)
        .attr('filter', 'url(#glow)')
        .attr('pointer-events', 'none');
    }

    // Left accent strip
    g.append('rect')
      .attr('width', 5).attr('height', box.h).attr('rx', 2)
      .attr('fill', `url(#grad-${cat})`);

    // ── Header ────────────────────────────────────────────────────────────
    g.append('text').attr('class', 'box-tag')
      .attr('x', 24).attr('y', 28)
      .attr('fill', `url(#grad-${cat})`)
      .text(CAT_LABEL[cat]);

    g.append('text').attr('class', 'box-title')
      .attr('x', 24).attr('y', 58)
      .text(party.label);

    if (party.sublabel) {
      g.append('text').attr('class', 'box-sublabel')
        .attr('x', 24).attr('y', 80)
        .text(party.sublabel);
    }

    // Header divider
    g.append('line').attr('class', 'box-divider')
      .attr('x1', 22).attr('y1', HEADER_H - 8)
      .attr('x2', box.w - 22).attr('y2', HEADER_H - 8);

    // ── Body: tool surface (if any) ───────────────────────────────────────
    if (surface && surface.length > 0) {
      const onLeft = position === 'left';
      surface.forEach((op, i) => {
        const ry = HEADER_H + i * ROW_H + ROW_H / 2;
        const display = op.tool.endsWith(')')
          ? op.tool.replace(/\(.*\)$/, '()')
          : op.tool;

        const rowG = g.append('g').attr('class', 'tool-row');
        // Hover background row
        rowG.append('rect')
          .attr('class', 'tool-row-bg')
          .attr('x', 12).attr('y', ry - ROW_H / 2 + 4)
          .attr('width', box.w - 24).attr('height', ROW_H - 8)
          .attr('rx', 6).attr('fill', 'rgba(255, 255, 255, 0.025)');
        // Indicator dot, always on the side facing the arrow exit
        const dotX = onLeft ? box.w - 18 : 18;
        rowG.append('circle')
          .attr('cx', dotX).attr('cy', ry).attr('r', 3.5)
          .attr('fill', `url(#grad-${cat})`);
        // Tool name
        const tx = onLeft ? 28 : box.w - 28;
        rowG.append('text')
          .attr('class', 'tool-row-name')
          .attr('x', tx).attr('y', ry + 4)
          .attr('text-anchor', onLeft ? 'start' : 'end')
          .text(display);
      });
    }

    // ── Body: special content ────────────────────────────────────────────
    if (party.kind === 'embedding-graphic') {
      const padX = 22, padY = HEADER_H + 14;
      const gW = box.w - padX * 2;
      const gH = box.h - padY - 22;
      const gInner = g.append('g').attr('transform', `translate(${padX}, ${padY})`);
      renderEmbeddingGraphic(gInner, gW, gH, 'large');
    }

    if (party.kind === 'external-stack' && party.stack) {
      const padX = 22, padY = HEADER_H + 12;
      const itemH = 50, itemGap = 8;
      party.stack.forEach((item, i) => {
        const iy = padY + i * (itemH + itemGap);
        const ig = g.append('g').attr('transform', `translate(${padX}, ${iy})`);
        ig.append('rect')
          .attr('width', box.w - padX * 2).attr('height', itemH)
          .attr('rx', 8)
          .attr('fill', 'rgba(82, 226, 160, 0.06)')
          .attr('stroke', 'rgba(82, 226, 160, 0.25)');
        ig.append('text')
          .attr('x', 14).attr('y', 20)
          .attr('fill', '#fff').attr('font-weight', 600).attr('font-size', 14)
          .text(item.label);
        ig.append('text')
          .attr('x', 14).attr('y', 38)
          .attr('fill', 'rgba(255, 255, 255, 0.55)').attr('font-size', 11)
          .attr('font-family', 'JetBrains Mono, monospace')
          .text(item.note);
      });
    }

    // Storage / user boxes — schema preview if no tool surface and no special graphic
    if ((party.kind === 'storage' || party.kind === 'user')
        && (!surface || surface.length === 0)
        && party.schema) {
      const fo = g.append('foreignObject')
        .attr('x', 22).attr('y', HEADER_H + 12)
        .attr('width', box.w - 44).attr('height', box.h - HEADER_H - 24);
      const div = document.createElement('div');
      div.className = 'schema-text';
      div.textContent = party.schema;
      fo.node().appendChild(div);
    }
  }

  // ─── L2: reasoning scene (inputs → agent → outputs) ──────────────────────
  // The agent reasons (LLM-backed). Inputs feed in from the left, outputs
  // emerge from the right. Boxes use the same rich-box style as connection
  // scenes for visual consistency.
  function renderReasoningScene(scene) {
    const CANVAS_TOP = 130;
    const AVAIL_H = VBH - CANVAS_TOP - 40;
    const CY = CANVAS_TOP + AVAIL_H / 2;

    const LX = 220, MX = VBW / 2, RX = VBW - 240;

    const inBoxes  = layoutStack(scene.inputs,  LX, CY);
    const outBoxes = layoutStack(scene.outputs, RX, CY);

    // Agent in the middle — taller box with reasoning-specific surface
    const agentBox = { x: MX, y: CY, w: 360, h: 220 };

    const gArrows = sceneRoot.append('g').attr('class', 'scene-arrows');
    const gBoxes  = sceneRoot.append('g').attr('class', 'scene-boxes');

    inBoxes.forEach(b => {
      renderInputBox(gBoxes, b);
      gArrows.append('line').attr('class', 'scene-edge')
        .attr('x1', b.x + b.w / 2).attr('y1', b.y)
        .attr('x2', agentBox.x - agentBox.w / 2).attr('y2', agentBox.y + (b.y - CY) * 0.35)
        .attr('marker-end', 'url(#arrow)');
    });

    outBoxes.forEach(b => {
      renderInputBox(gBoxes, b);
      gArrows.append('line').attr('class', 'scene-edge')
        .attr('x1', agentBox.x + agentBox.w / 2).attr('y1', agentBox.y + (b.y - CY) * 0.35)
        .attr('x2', b.x - b.w / 2).attr('y2', b.y)
        .attr('marker-end', 'url(#arrow)');
    });

    renderReasoningAgent(gBoxes, agentBox, scene.agent, scene.toolOnArrow);
  }

  function layoutStack(items, x, cy) {
    if (!items || !items.length) return [];
    const gap = 40;
    const w = 280, h = 160;
    const total = items.length * h + (items.length - 1) * gap;
    const startY = cy - total / 2;
    return items.map((it, i) => ({
      ...it, x, w, h,
      y: startY + i * (h + gap) + h / 2,
    }));
  }

  function renderInputBox(parent, b) {
    const cat = b.kind === 'storage' ? 'storage' : 'data';
    const g = parent.append('g').attr('class', 'rich-box')
      .attr('transform', `translate(${b.x - b.w / 2}, ${b.y - b.h / 2})`);

    g.append('rect').attr('width', b.w).attr('height', b.h).attr('rx', 14)
      .attr('fill', 'rgba(8, 8, 16, 0.95)').attr('filter', 'url(#card-shadow)');
    g.append('rect').attr('width', b.w).attr('height', b.h).attr('rx', 14)
      .attr('fill', 'url(#dot-grid)').attr('pointer-events', 'none');
    g.append('rect').attr('width', b.w).attr('height', b.h).attr('rx', 14)
      .attr('fill', 'url(#card-inner)').attr('pointer-events', 'none');
    g.append('rect').attr('width', b.w).attr('height', b.h).attr('rx', 14)
      .attr('fill', 'none').attr('stroke', `url(#grad-${cat})`).attr('stroke-width', 1.4);
    g.append('rect').attr('width', 4).attr('height', b.h).attr('rx', 2)
      .attr('fill', `url(#grad-${cat})`);

    g.append('text').attr('class', 'box-tag')
      .attr('x', 18).attr('y', 22)
      .attr('fill', `url(#grad-${cat})`)
      .text(CAT_LABEL[cat] || 'DATA');
    g.append('text').attr('class', 'box-title')
      .attr('x', 18).attr('y', 48).attr('font-size', 16)
      .text(b.label);

    if (b.schema) {
      const fo = g.append('foreignObject')
        .attr('x', 18).attr('y', 60)
        .attr('width', b.w - 36).attr('height', b.h - 72);
      const div = document.createElement('div');
      div.className = 'schema-text';
      div.textContent = b.schema;
      fo.node().appendChild(div);
    }
  }

  function renderReasoningAgent(parent, b, agent, toolName) {
    const g = parent.append('g').attr('class', 'rich-box')
      .attr('transform', `translate(${b.x - b.w / 2}, ${b.y - b.h / 2})`);

    g.append('rect').attr('width', b.w).attr('height', b.h).attr('rx', 18)
      .attr('fill', 'rgba(8, 8, 16, 0.97)').attr('filter', 'url(#card-shadow)');
    g.append('rect').attr('width', b.w).attr('height', b.h).attr('rx', 18)
      .attr('fill', 'url(#dot-grid)').attr('pointer-events', 'none');
    g.append('rect').attr('width', b.w).attr('height', b.h).attr('rx', 18)
      .attr('fill', 'url(#card-inner)').attr('pointer-events', 'none');
    g.append('rect').attr('width', b.w).attr('height', b.h).attr('rx', 18)
      .attr('fill', 'none').attr('stroke', `url(#grad-agent)`).attr('stroke-width', 2);
    g.append('rect').attr('width', b.w).attr('height', b.h).attr('rx', 18)
      .attr('fill', 'none').attr('stroke', `url(#grad-agent)`)
      .attr('stroke-width', 1).attr('opacity', 0.4).attr('filter', 'url(#glow)')
      .attr('pointer-events', 'none');
    g.append('rect').attr('width', 5).attr('height', b.h).attr('rx', 2)
      .attr('fill', `url(#grad-agent)`);

    // Header
    g.append('text').attr('class', 'box-tag')
      .attr('x', 24).attr('y', 28)
      .attr('fill', `url(#grad-agent)`)
      .text('AGENT · REASONING');

    g.append('text').attr('class', 'box-title')
      .attr('x', 24).attr('y', 60).text(agent.label);

    // ✦ glyph in the corner
    g.append('text')
      .attr('x', b.w - 24).attr('y', 56).attr('text-anchor', 'end')
      .attr('font-size', 36).attr('fill', `url(#grad-agent)`)
      .text('✦');

    g.append('line').attr('class', 'box-divider')
      .attr('x1', 22).attr('y1', 86).attr('x2', b.w - 22).attr('y2', 86);

    // Body: a small "LLM brain" panel
    g.append('text').attr('class', 'box-sublabel')
      .attr('x', 24).attr('y', 110)
      .text('hands inputs to a swappable LLM');

    if (toolName) {
      const ry = b.h - 56;
      g.append('rect')
        .attr('x', 22).attr('y', ry - 22)
        .attr('width', b.w - 44).attr('height', 38).attr('rx', 8)
        .attr('fill', 'rgba(255, 107, 157, 0.08)')
        .attr('stroke', 'rgba(255, 107, 157, 0.4)');
      g.append('circle').attr('cx', 38).attr('cy', ry - 3).attr('r', 3.5)
        .attr('fill', `url(#grad-agent)`);
      g.append('text').attr('class', 'tool-row-name')
        .attr('x', 50).attr('y', ry + 1)
        .text(toolName);
    }
  }

  // ─── GEOMETRY ────────────────────────────────────────────────────────────
  function boundaryPoint(node, angle) {
    const halfW = node.w / 2 + 2, halfH = node.h / 2 + 2;
    const cos = Math.cos(angle), sin = Math.sin(angle);
    const tx = Math.abs(cos) > 1e-6 ? halfW / Math.abs(cos) : Infinity;
    const ty = Math.abs(sin) > 1e-6 ? halfH / Math.abs(sin) : Infinity;
    const t = Math.min(tx, ty);
    return { x: node.x + cos * t, y: node.y + sin * t };
  }

  // ─── TEXT HELPERS ────────────────────────────────────────────────────────
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  // ─── INTRO OVERLAY ───────────────────────────────────────────────────────
  const intro = document.getElementById('intro-overlay');
  const introBtn = document.getElementById('intro-dismiss');
  if (localStorage.getItem('arch-intro-seen-v2')) {
    intro.style.display = 'none';
  } else {
    introBtn.addEventListener('click', () => {
      intro.classList.add('hidden');
      localStorage.setItem('arch-intro-seen-v2', '1');
      setTimeout(() => intro.style.display = 'none', 300);
    });
  }

  // ─── KEYBOARD ────────────────────────────────────────────────────────────
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (state.level === 'L2' && state.focusId) clearL2Focus();
      else if (state.level === 'L2') goTo('L1');
    } else if (e.key === 'ArrowRight' && state.level === 'L2') {
      const next = adjacentL2Connection(state.number, 1);
      if (next != null) {
        e.preventDefault();
        goTo('L2', next);
      }
    } else if (e.key === 'ArrowLeft' && state.level === 'L2') {
      const prev = adjacentL2Connection(state.number, -1);
      if (prev != null) {
        e.preventDefault();
        goTo('L2', prev);
      }
    } else if (e.key === '0') {
      resetView();
    }
  });

  // ─── BOOT ────────────────────────────────────────────────────────────────
  // Deep-link via hash: #L0, #L1, #L2-<n>
  function routeFromHash() {
    const m = /^#L(0|1|2)(?:-(\d+))?$/.exec(location.hash);
    if (!m) return false;
    if (m[1] === '0') { goTo('L0'); return true; }
    if (m[1] === '1') { goTo('L1'); return true; }
    const num = m[2] ? +m[2] : 1;
    goTo('L2', num);
    return true;
  }
  if (!routeFromHash()) goTo('L0');
  window.addEventListener('hashchange', routeFromHash);
})();
