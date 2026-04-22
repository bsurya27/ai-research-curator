# Architecture Visualization

An interactive, progressive-disclosure diagram of the AI Research Curator system.

## View it

Published via GitHub Pages from this `/docs` folder. Enable it once at
**Settings → Pages → Source: Deploy from a branch → Branch: `main` / folder: `/docs`**,
and the site will be available at:

```
https://bsurya27.github.io/ai-research-curator/
```

## Run locally

It's fully static. Any HTTP server works:

```bash
cd docs
python -m http.server 8080
# open http://localhost:8080
```

## The three levels

- **L1 — Data flow.** Seven modules (signals, curator, embedding space, scraping, briefing, reporter, user) connected by the daily loop. Seven numbered circles mark the *connections* between modules — each with a brief one-line description. The embedding space is drawn as an actual vector space: scatter of stored items with a preference arrow.
- **L2 — Inside a connection.** Click a number. The two parties involved sit on left and right, and every tool call that travels between them is drawn as a parallel arrow with its function name as label, its description beneath, and its return shape underneath that. Reasoning steps (LLM-backed) use a three-column `inputs → agent → output` layout instead.
- **L3 — Tools & code.** One more click. The actual Python functions used across that connection, each rendered as a card on the canvas with a syntax-highlighted inline code snippet and a link to its source file on GitHub.

No LLM node: the LLM is a swappable tool, not a first-class module. It shows up inside the code snippets at L3.

## Navigation

- Click a numbered circle on L1 → L2
- Click **See the tools & code** on L2 → L3
- `Esc` goes up one level
- `←` `→` step through L2 scenes
- **Drag to pan, scroll to zoom** the canvas — `0` resets the view

## Files

| File | Purpose |
|---|---|
| `index.html` | Entry point, loads D3 from CDN |
| `styles.css` | Dark gradient theme, scene + tool-card styles |
| `data.js`    | L1 graph + per-connection L2 scene data + per-connection L3 tool cards |
| `app.js`     | D3 rendering, level-change transitions, pan/zoom, panel updates |

## Editing content

All content lives in `data.js`. Each of the 7 entries in `CONNECTIONS[]` owns:

```js
{
  number: 2,
  title: 'Preference · clusters · embed · score',
  blurb: 'four round-trips: nudge pref → get clusters → embed new items → score all',
  marker: { x: 620, y: 330, labelBelow: false },  // L1 numbered circle position
  hosts: ['curator', 'embedding'],                 // L1 nodes that light up on hover

  l2: {
    type: 'connection',                            // or 'reasoning'
    description: 'Paragraph shown in the side panel at L2.',
    annotation: 'Optional callout.',

    // 'connection' layout
    left:  { id, kind, label, schema? },
    right: { id, kind, label, sublabel?, schema? },   // kind: 'embedding-graphic' draws the scatter
    sink:  { id, kind, label, schema? },              // optional 3rd party below
    operations: [
      {
        sub: 'a',                   // substep badge
        dir: 'right' | 'left' | 'sink',
        tool: 'update_preference(url, score, source)',
        label: 'nudge pref toward / away',
        endpoint: 'POST /update',   // optional
        returns: '{ok, updated}',    // optional
        dashed: true,                // optional
      },
      ...
    ],

    // 'reasoning' layout (alternative)
    inputs:  [{ id, label, kind, schema }],
    agent:   { id, label, role: 'reasoning' },
    outputs: [{ id, label, kind, schema }],
    toolOnArrow: '_queries_from_claude()',
  },

  l3: {
    description: 'Summary above the tool list in the panel.',
    tools: [
      { name, brief, file, code }   // code is the inline snippet on canvas
    ],
  },
}
```

`REPO_BASE` at the top of `data.js` turns every `file` value into a clickable GitHub link.
