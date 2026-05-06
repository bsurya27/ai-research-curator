// Two-level flow:
//   L1: data-flow overview with numbered steps.
//   L2: zoom into a connection; cycle arrows are clickable for dimmed focus,
//       technical notes, and a GitHub link to the exact call site (line anchor).
// Canvas supports pan (drag) and zoom (wheel) via d3.zoom.

(function () {
  const svg = d3.select('#canvas');
  const panel = document.getElementById('panel-content');
  const breadcrumb = document.getElementById('breadcrumb');
  const resetBtn = document.getElementById('reset-view');

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

  const shadow = defs.append('filter')
    .attr('id', 'card-shadow')
    .attr('x', '-20%').attr('y', '-20%')
    .attr('width', '140%').attr('height', '140%');
  shadow.append('feDropShadow')
    .attr('dx', 0).attr('dy', 6)
    .attr('stdDeviation', 12)
    .attr('flood-color', '#000')
    .attr('flood-opacity', 0.55);

  const innerGrad = defs.append('linearGradient')
    .attr('id', 'card-inner').attr('x1', '0%').attr('y1', '0%')
    .attr('x2', '0%').attr('y2', '100%');
  innerGrad.append('stop').attr('offset', '0%').attr('stop-color', 'rgba(255, 255, 255, 0.05)');
  innerGrad.append('stop').attr('offset', '60%').attr('stop-color', 'rgba(255, 255, 255, 0)');
  innerGrad.append('stop').attr('offset', '100%').attr('stop-color', 'rgba(0, 0, 0, 0.18)');

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
  const state = { level: 'L1', number: null, focusId: null };
  let navSeq = 0;

  function getConn(n) { return CONNECTIONS.find(c => c.number === n); }

  function adjacentL2Connection(fromNum, delta) {
    if (fromNum == null) return null;
    const cur = getConn(fromNum);
    if (!cur) return null;
    const reps = [];
    const seen = new Set();
    for (const c of CONNECTIONS) {
      if (!seen.has(c.l2)) {
        seen.add(c.l2);
        reps.push(c.number);
      }
    }
    if (reps.length < 2) return null;
    const curRep = reps.find(n => getConn(n).l2 === cur.l2);
    const idx = reps.indexOf(curRep);
    if (idx < 0) return null;
    const next = (idx + delta + reps.length) % reps.length;
    return reps[next];
  }

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
    let h;
    if (state.level === 'HOME') h = '#home';
    else if (state.level === 'L1') h = '#L1';
    else h = '#L2-' + state.number;
    if (location.hash !== h) {
      try { history.replaceState(null, '', h); } catch (e) { /* e.g. file:// */ }
    }
  }

  function syncLayoutToLevel() {
    if (document.body) document.body.dataset.vizLevel = state.level;
  }

  function goTo(level, number) {
    navSeq++;
    const mySeq = navSeq;

    clearCycleChase();
    state.focusId = null;

    const prev = sceneRoot.selectAll('*');
    prev.transition().duration(180).style('opacity', 0).remove();

    state.level = level;
    state.number = number ?? null;

    syncLayoutToLevel();

    setTimeout(() => {
      if (mySeq !== navSeq) return;
      sceneRoot.attr('opacity', 0);
      if (state.level === 'L1') renderL1();
      else if (state.level === 'L2') renderL2(getConn(state.number));
      // HOME: leave canvas blank; the landing section is shown via CSS.
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

    if (state.level === 'HOME') return;
    add('Home', () => goTo('HOME'), false);
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
    if (state.level === 'HOME') { panel.innerHTML = ''; return; }
    if (state.level === 'L1') {
      panel.innerHTML = `
        <h2>${escapeHtml(L1_OVERVIEW.title)}</h2>
        <p>${escapeHtml(L1_OVERVIEW.paragraph)}</p>
        <h3>The 8 steps</h3>
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
            ${prevN != null ? `<button class="nav-btn" onclick="window.__goL2(${prevN})">← Prev scene</button>` : '<span></span>'}
            ${nextN != null ? `<button class="nav-btn" onclick="window.__goL2(${nextN})">Next scene →</button>` : '<span></span>'}
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
  function renderEmbeddingGraphic(parent, w, h, detail = 'small') {
    const g = parent.append('g').attr('class', 'embedding-graphic');

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

    g.append('circle')
      .attr('cx', 0.72 * w).attr('cy', 0.30 * h)
      .attr('r', 0.16 * Math.min(w, h))
      .attr('fill', 'rgba(0, 212, 255, 0.06)')
      .attr('stroke', 'rgba(0, 212, 255, 0.25)')
      .attr('stroke-width', 0.8)
      .attr('stroke-dasharray', '3 3');

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

    g.append('circle')
      .attr('cx', ox).attr('cy', oy)
      .attr('r', 3).attr('fill', '#ff6b9d').attr('opacity', 0.6);

    g.append('text')
      .attr('x', w - 8).attr('y', h - 6)
      .attr('text-anchor', 'end')
      .attr('fill', 'rgba(255, 255, 255, 0.28)')
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('font-size', detail === 'large' ? 10 : 9)
      .text('ℝ¹⁵³⁶');

    return g;
  }

  // ─── L1 ──────────────────────────────────────────────────────────────────
  function renderL1() {
    // ── Helper: resolve a step endpoint to a node or virtual port ─────────
    function resolveNode(id) {
      if (id === '_embedding_port_5') return EMBEDDING_PORT_5;
      if (id === '_embedding_port_8') return EMBEDDING_PORT_8;
      if (id === '_embedding_port')   return EMBEDDING_PORT_5; // fallback
      return L1_NODES.find(n => n.id === id) || null;
    }

    // ── Draw dashed region boxes first (behind everything) ────────────────
    if (typeof L1_REGIONS !== 'undefined' && L1_REGIONS.length) {
      const gRegions = sceneRoot.append('g').attr('class', 'regions-layer');
      L1_REGIONS.forEach(r => {
        const rg = gRegions.append('g').attr('class', 'l1-region');
        rg.append('rect')
          .attr('x', r.x).attr('y', r.y)
          .attr('width', r.w).attr('height', r.h)
          .attr('rx', 16).attr('ry', 16)
          .attr('fill', 'rgba(255, 255, 255, 0.018)')
          .attr('stroke', 'rgba(255, 255, 255, 0.28)')
          .attr('stroke-width', 1.5)
          .attr('stroke-dasharray', '9 6');
        const labelX = r.labelAnchor === 'right' ? r.x + r.w - 18 : r.x + 18;
        const labelAnchor = r.labelAnchor === 'right' ? 'end' : 'start';
        rg.append('text')
          .attr('x', labelX).attr('y', r.y + 30)
          .attr('fill', 'rgba(255, 255, 255, 0.72)')
          .attr('font-family', 'Inter, system-ui, sans-serif')
          .attr('font-size', 17)
          .attr('font-style', r.italic ? 'italic' : 'normal')
          .attr('font-weight', 700)
          .attr('letter-spacing', '0.03em')
          .attr('text-anchor', labelAnchor)
          .text(r.label);
      });
    }

    // ── Step arrows (elbow paths) ─────────────────────────────────────────
    // Parallel steps between same pair get a small vertical offset so they
    // don't stack. For elbow arrows the offset shifts the elbow bend point.
    const PARALLEL_OFFSET = 28;
    const bucket = new Map();
    STEPS.forEach(s => {
      const key = [s.from, s.to].sort().join('|');
      if (!bucket.has(key)) bucket.set(key, []);
      bucket.get(key).push(s);
    });
    const stepParallelIdx = new Map();
    bucket.forEach((group) => {
      group.sort((a, b) => a.n - b.n).forEach((s, i) => {
        stepParallelIdx.set(s.n, { idx: i, total: group.length });
      });
    });

    const gStepArrows = sceneRoot.append('g').attr('class', 'step-arrows-layer');
    const stepGeom = new Map();

    STEPS.forEach(s => {
      const from = resolveNode(s.from);
      const to   = resolveNode(s.to);
      if (!from || !to) return;

      const pi = stepParallelIdx.get(s.n) || { idx: 0, total: 1 };
      const autoShift = (pi.idx - (pi.total - 1) / 2) * PARALLEL_OFFSET;
      const parallelShift = (typeof s.shift === 'number') ? s.shift : autoShift;

      const geom = elbowPath(from, to, s.route || 'h-v', parallelShift);
      stepGeom.set(s.n, geom);

      gStepArrows.append('path')
        .attr('class', `step-arrow step-arrow-${s.n}`)
        .attr('d', geom.d)
        .attr('marker-end', 'url(#arrow)')
        .style('--step-delay', `${(s.n - 1) * 1.5}s`);
    });

    // ── Module nodes ──────────────────────────────────────────────────────
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

    // ── Numbered step markers ─────────────────────────────────────────────
    const gMarks = sceneRoot.append('g').attr('class', 'marks-layer');
    STEPS.forEach(s => {
      const geom = stepGeom.get(s.n);
      if (!geom) return;
      const conn = CONNECTIONS.find(c => c.number === s.connection);
      const hosts = (conn && conn.hosts) || [];
      const { x: mx, y: my } = geom.mid;

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
      if (lp === 'below')      { ly = 36;  anchor = 'middle'; }
      else if (lp === 'above') { ly = -28; anchor = 'middle'; }
      else if (lp === 'left')  { lx = -32; ly = 4; anchor = 'end'; }
      else if (lp === 'right') { lx = 32;  ly = 4; anchor = 'start'; }

      g.append('text')
        .attr('class', 'step-label')
        .attr('x', lx).attr('y', ly)
        .attr('text-anchor', anchor)
        .text(s.label);
    });
  }

  // ─── ELBOW PATH ──────────────────────────────────────────────────────────
  // Right-angle arrows. Virtual ports have w=0 h=0 so boundary math still works.
  function elbowPath(from, to, route, parallelShift) {
    parallelShift = parallelShift || 0;
    const fx = from.x, fy = from.y;
    const tx = to.x,   ty = to.y;
    const fR = fx + from.w / 2, fL = fx - from.w / 2;
    const fB = fy + from.h / 2, fT = fy - from.h / 2;
    const tR = tx + to.w / 2,   tL = tx - to.w / 2;
    const tB = ty + to.h / 2,   tT = ty - to.h / 2;

    let d, mid;

    if (route === 'h') {
      // Horizontal exit → vertical snap if y differs.
      // parallelShift moves BOTH source and target y so the line stays
      // purely horizontal but at a different height (used to lift / drop
      // an 'h' arrow on the target's vertical edge).
      const sx = tx > fx ? fR : fL;
      const sy = fy + parallelShift;
      const ex = tx > fx ? tL : tR;
      const ey = ty + parallelShift;
      if (Math.abs(ey - sy) > 6) {
        d = `M ${sx} ${sy} H ${ex} V ${ey}`;
      } else {
        d = `M ${sx} ${sy} H ${ex}`;
      }
      mid = { x: (sx + ex) / 2, y: sy };

    } else if (route === 'v') {
      // Vertical exit → horizontal snap if x differs
      const sx = fx + parallelShift;
      const sy = ty > fy ? fB : fT;
      const ex = tx;
      const ey = ty > fy ? tT : tB;
      if (Math.abs(ex - sx) > 6) {
        d = `M ${sx} ${sy} V ${ey} H ${ex}`;
      } else {
        d = `M ${sx} ${sy} V ${ey}`;
      }
      mid = { x: sx, y: (sy + ey) / 2 };

    } else if (route === 'h-v') {
      // Exit horizontally → turn at target's x → arrive vertically at target edge
      const goRight = tx >= fx;
      const goDown  = ty >= fy;
      const sx = goRight ? fR : fL;
      const sy = fy + parallelShift;
      // Horizontal leg stops at target's x-center
      const bendX = tx + parallelShift;
      // Vertical leg arrives at target's nearest horizontal edge
      const ey = goDown ? tT : tB;
      d = `M ${sx} ${sy} H ${bendX} V ${ey}`;
      mid = { x: (sx + bendX) / 2, y: sy };

    } else {
      // v-h: exit vertically → turn at target's y → arrive horizontally at target edge
      const goDown  = ty >= fy;
      const goRight = tx >= fx;
      const sx = fx + parallelShift;
      const sy = goDown ? fB : fT;
      // Vertical leg stops at target's y-center
      const bendY = ty + parallelShift;
      // Horizontal leg arrives at target's nearest vertical edge
      const ex = goRight ? tL : tR;
      d = `M ${sx} ${sy} V ${bendY} H ${ex}`;
      mid = { x: sx, y: (sy + bendY) / 2 };
    }

    return { d, mid };
  }

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

  function waypointPath(from, waypoint, to) {
    const a1 = Math.atan2(waypoint.y - from.y, waypoint.x - from.x);
    const f = boundaryPoint(from, a1);
    const a2 = Math.atan2(to.y - waypoint.y, to.x - waypoint.x);
    const t = boundaryPoint(to, a2 + Math.PI);
    const w = { x: waypoint.x, y: waypoint.y };
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

    if (n.bullets && n.bullets.length) {
      g.append('text').attr('class', 'label')
        .attr('x', n.w / 2).attr('y', 30)
        .attr('text-anchor', 'middle')
        .text(n.label);
      const startY = 58;
      const lh = 19;
      n.bullets.forEach((b, i) => {
        g.append('text').attr('class', 'node-bullet')
          .attr('x', 22).attr('y', startY + i * lh)
          .text(`• ${b}`);
      });
      return;
    }

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

    // Markers are r=20 circles centered on the arrow midpoint.
    // Above/below labels are 80px tall; clear the marker by ~10px on each side.
    let capX, capY, capCls = '';
    if (side === 'above') {
      capX = mx - CAP_W / 2 + dxOff; capY = my - 110 + dyOff;
    } else if (side === 'below') {
      capX = mx - CAP_W / 2 + dxOff; capY = my + 30 + dyOff;
    } else if (side === 'right') {
      capX = mx + 34 + dxOff;        capY = my - 44 + dyOff;
      capCls = ' side-right';
    } else {
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
  const HEADER_H = 96;
  const ROW_H    = 38;
  const PAD_BOT  = 28;

  function renderConnectionScene(scene) {
    const CANVAS_TOP = 130;
    const AVAIL_H = VBH - CANVAS_TOP - 40;
    const CY = CANVAS_TOP + AVAIL_H / 2;

    const isFnCall = (op) => op && /^[\w.]+\(/.test(op.tool);
    const allOps = (scene.operations || []).filter(isFnCall);
    const horizOps = allOps.filter(o => o.dir === 'right' || o.dir === 'left');
    const sinkOps  = allOps.filter(o => o.dir === 'sink');

    const leftIsAgent  = scene.left.kind === 'agent';
    const rightIsAgent = scene.right.kind === 'agent';
    const rightIsGraphic = scene.right.kind === 'embedding-graphic';
    const rightIsStack   = scene.right.kind === 'external-stack';

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

    const leftW = 340;
    const rightW = rightIsGraphic ? 500 : rightIsStack ? 360 : 340;

    let leftH  = leftSurface.length  ? surfaceH(leftSurface.length)  : 200;
    let rightH = rightSurface.length ? surfaceH(rightSurface.length) : 200;
    if (rightIsGraphic) rightH = Math.max(rightH, 380);
    if (rightIsStack)   rightH = Math.max(rightH, 280);

    const LX = 260;
    const RX = VBW - (rightW / 2 + 80);

    const left  = { x: LX,  y: CY - (leftH  / 2) + (leftH  / 2), w: leftW,  h: leftH  };
    const right = { x: RX,  y: CY - (rightH / 2) + (rightH / 2), w: rightW, h: rightH };
    left.y  = CY;
    right.y = CY;

    const gBoxes = sceneRoot.append('g').attr('class', 'scene-boxes');
    renderRichBox(gBoxes, left,  scene.left,  leftSurface,  'left');
    renderRichBox(gBoxes, right, scene.right, rightSurface, 'right');

    let sink = null;
    if (scene.sink) {
      sink = { x: VBW / 2, y: VBH - 110, w: 380, h: 110 };
      renderRichBox(sceneRoot.append('g').attr('class', 'scene-sink'),
                    sink, scene.sink, [], 'sink');
    }

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
      const otherY = homeY;

      const homeX = onLeft ? homeBox.x + homeBox.w / 2 : homeBox.x - homeBox.w / 2;
      const otherX = onLeft ? otherBox.x - otherBox.w / 2 : otherBox.x + otherBox.w / 2;

      drawConnectionArrow(gArrows, homeX, homeY, otherX, otherY, op);
    });

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

  function drawConnectionArrow(parent, fx, fy, tx, ty, op) {
    const cls = 'scene-edge' + (op.dashed ? ' dashed' : '');
    const line = parent.append('line')
      .attr('class', cls)
      .attr('x1', fx).attr('y1', fy)
      .attr('x2', tx).attr('y2', ty);
    const arrowOnRight = op.dir === 'right';
    if (fx < tx) {
      if (arrowOnRight) line.attr('marker-end', 'url(#arrow)');
      else              line.attr('marker-start', 'url(#arrow-bi-start)');
    } else {
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

  function renderRichBox(parent, box, party, surface, position) {
    const g = parent.append('g').attr('class', 'rich-box')
      .attr('transform', `translate(${box.x - box.w / 2}, ${box.y - box.h / 2})`);

    const cat = party.kind === 'agent' ? 'agent'
              : party.kind === 'embedding-graphic' ? 'service'
              : party.kind === 'external-stack' ? 'external'
              : party.kind === 'storage' ? 'storage'
              : party.kind === 'user' ? 'user' : 'data';
    const isAgent = party.kind === 'agent';

    g.append('rect')
      .attr('class', 'rich-box-shadow')
      .attr('width', box.w).attr('height', box.h)
      .attr('rx', 16)
      .attr('fill', 'rgba(8, 8, 16, 0.95)')
      .attr('filter', 'url(#card-shadow)');

    g.append('rect')
      .attr('width', box.w).attr('height', box.h).attr('rx', 16)
      .attr('fill', 'url(#dot-grid)')
      .attr('pointer-events', 'none');

    g.append('rect')
      .attr('width', box.w).attr('height', box.h).attr('rx', 16)
      .attr('fill', 'url(#card-inner)')
      .attr('pointer-events', 'none');

    g.append('rect')
      .attr('class', 'rich-box-border')
      .attr('width', box.w).attr('height', box.h).attr('rx', 16)
      .attr('fill', 'none')
      .attr('stroke', `url(#grad-${cat})`)
      .attr('stroke-width', isAgent ? 2 : 1.5);

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

    g.append('rect')
      .attr('width', 5).attr('height', box.h).attr('rx', 2)
      .attr('fill', `url(#grad-${cat})`);

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

    g.append('line').attr('class', 'box-divider')
      .attr('x1', 22).attr('y1', HEADER_H - 8)
      .attr('x2', box.w - 22).attr('y2', HEADER_H - 8);

    if (surface && surface.length > 0) {
      const onLeft = position === 'left';
      surface.forEach((op, i) => {
        const ry = HEADER_H + i * ROW_H + ROW_H / 2;
        const display = op.tool.endsWith(')')
          ? op.tool.replace(/\(.*\)$/, '()')
          : op.tool;

        const rowG = g.append('g').attr('class', 'tool-row');
        rowG.append('rect')
          .attr('class', 'tool-row-bg')
          .attr('x', 12).attr('y', ry - ROW_H / 2 + 4)
          .attr('width', box.w - 24).attr('height', ROW_H - 8)
          .attr('rx', 6).attr('fill', 'rgba(255, 255, 255, 0.025)');
        const dotX = onLeft ? box.w - 18 : 18;
        rowG.append('circle')
          .attr('cx', dotX).attr('cy', ry).attr('r', 3.5)
          .attr('fill', `url(#grad-${cat})`);
        const tx = onLeft ? 28 : box.w - 28;
        rowG.append('text')
          .attr('class', 'tool-row-name')
          .attr('x', tx).attr('y', ry + 4)
          .attr('text-anchor', onLeft ? 'start' : 'end')
          .text(display);
      });
    }

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

  // ─── L2: reasoning scene ─────────────────────────────────────────────────
  function renderReasoningScene(scene) {
    const CANVAS_TOP = 130;
    const AVAIL_H = VBH - CANVAS_TOP - 40;
    const CY = CANVAS_TOP + AVAIL_H / 2;

    const LX = 220, MX = VBW / 2, RX = VBW - 240;

    const inBoxes  = layoutStack(scene.inputs,  LX, CY);
    const outBoxes = layoutStack(scene.outputs, RX, CY);

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

    g.append('text').attr('class', 'box-tag')
      .attr('x', 24).attr('y', 28)
      .attr('fill', `url(#grad-agent)`)
      .text('AGENT · REASONING');

    g.append('text').attr('class', 'box-title')
      .attr('x', 24).attr('y', 60).text(agent.label);

    g.append('text')
      .attr('x', b.w - 24).attr('y', 56).attr('text-anchor', 'end')
      .attr('font-size', 36).attr('fill', `url(#grad-agent)`)
      .text('✦');

    g.append('line').attr('class', 'box-divider')
      .attr('x1', 22).attr('y1', 86).attr('x2', b.w - 22).attr('y2', 86);

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
  function routeFromHash() {
    const h = location.hash || '';
    if (h === '' || h === '#' || h === '#home') { goTo('HOME'); return true; }
    const m = /^#L(1|2)(?:-(\d+))?$/.exec(h);
    if (!m) return false;
    if (m[1] === '1') { goTo('L1'); return true; }
    const num = m[2] ? +m[2] : 1;
    goTo('L2', num);
    return true;
  }
  if (!routeFromHash()) goTo('HOME');
  window.addEventListener('hashchange', routeFromHash);

  const ctaBtn = document.getElementById('landing-cta');
  if (ctaBtn) ctaBtn.onclick = () => goTo('L1');
  const titleH1 = document.querySelector('.top-bar h1');
  if (titleH1) {
    titleH1.style.cursor = 'pointer';
    titleH1.onclick = () => goTo('HOME');
  }
})();