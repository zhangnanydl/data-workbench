# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Durable product decisions

- The primary surface is a Windows desktop data workbench in Chinese.
- Every input, transform, and output capability is a draggable plugin module rendered from backend metadata.
- The main layout follows the selected mock: project rail, searchable module library, node canvas, selected-module inspector, and persistent live result preview.
- Selecting or changing a node refreshes a sampled preview; full execution remains an explicit action.
- Preserve the light paper-white interface, cobalt primary actions, violet selected states, mint success states, compact typography, and thin separators from the selected design.
- The canvas uses a subtle layered line grid and does not show a minimap.
- Canvas edits must support undo; the toolbar also provides an explicit confirmed clear-canvas action.
- Configuration intended for non-technical users uses visual rule editors instead of requiring JSON syntax; saved legacy JSON remains backward compatible.
- Flow connections use arrowheads to make the data direction explicit; running-flow arrows follow the active blue animation color.
- EVTX event filtering offers common security event IDs as checkboxes and retains a custom-ID entry for competition-specific evidence.
- The module library prioritizes fast search and compact visual scanning: its header, search, and type filters stay fixed; processing modules use balanced secondary categories; and only expanded lists render.
