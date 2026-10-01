// Node test harness for the pure engine embedded in filament.html.
//
// The game is a single standalone HTML file, so instead of importing a module
// we extract the <script> block and run it in a `vm` context with no DOM. The
// script exposes its pure API on globalThis.__filament when `document` is
// absent (see the guard at the bottom of the script). Run with:
//
//     node --test

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const root = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(root, "..", "filament.html"), "utf8");
const match = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match, "could not find a <script> block in filament.html");

const sandbox = { console, performance: { now: () => Date.now() } };
vm.createContext(sandbox);
vm.runInContext(match[1], sandbox);

const F = sandbox.__filament;
assert.ok(F, "engine did not expose globalThis.__filament");

// groupStats() is shaped { count, sizes } today; accept either shape so these
// tests keep passing when the scoring helpers are refactored. Array.from makes
// the result a local-realm array (the engine runs in a vm context).
const sizesOf = (g) => Array.from(Array.isArray(g) ? g : g.sizes);

const degreeCounts = (cells, nb) => {
  const out = {};
  for (const c of cells) { const d = nb[c.id].length; out[d] = (out[d] || 0) + 1; }
  return out;
};

const colourCounts = (cells) => {
  const out = {};
  for (const c of cells) out[c.colour] = (out[c.colour] || 0) + 1;
  return out;
};

test("selfTest() reports no failures", () => {
  const s = F.selfTest();
  const failures = s.results.filter((r) => !r.ok).map((r) => `${r.name}: ${r.detail}`);
  assert.equal(s.failed, 0, failures.join("\n"));
  assert.equal(s.passed, s.results.length);
});

test("Cairo-48 geometry invariants", () => {
  const { cells, neighbours } = F.loadBoard(48);
  assert.equal(cells.length, 48);
  assert.ok(cells.every((c) => c.pentagon.length === 5), "pentagon not 5-gonal");
  assert.deepEqual(degreeCounts(cells, neighbours), { 3: 20, 5: 28 });
  assert.deepEqual(colourCounts(cells), { A: 16, B: 16, C: 16 });
  assert.ok(cells.every((c) => neighbours[c.id].every((n) => neighbours[n].includes(c.id))),
    "adjacency is not symmetric");
});

test("Cairo-160 geometry invariants", () => {
  const { cells, neighbours } = F.loadBoard(160);
  assert.equal(cells.length, 160);
  assert.ok(cells.every((c) => c.pentagon.length === 5), "pentagon not 5-gonal");
  assert.deepEqual(degreeCounts(cells, neighbours), { 3: 40, 5: 120 });
  assert.deepEqual(colourCounts(cells), { A: 54, B: 52, C: 54 });
  assert.ok(cells.every((c) => neighbours[c.id].every((n) => neighbours[n].includes(c.id))),
    "adjacency is not symmetric");
});

test("flip thresholds: 3-of-5 and 2-of-3 fill the opposite colour", () => {
  const { cells, neighbours } = F.loadBoard(48);
  const empty = () => new Array(cells.length).fill(0);
  const deg5 = cells.find((c) => neighbours[c.id].length === 5);
  const deg3 = cells.find((c) => neighbours[c.id].length === 3);

  const b = empty();
  const n5 = neighbours[deg5.id];
  b[n5[0]] = 1; b[n5[1]] = 1; b[n5[2]] = 1; b[n5[3]] = 2; b[n5[4]] = 2;
  assert.equal(F.flipColourOn(b, deg5.id), 2);
  b[n5[2]] = 0;
  assert.equal(F.flipColourOn(b, deg5.id), 0, "2-of-5 should be below threshold");

  const c = empty();
  const n3 = neighbours[deg3.id];
  c[n3[0]] = 2; c[n3[1]] = 2;
  assert.equal(F.flipColourOn(c, deg3.id), 1);
  c[n3[1]] = 0;
  assert.equal(F.flipColourOn(c, deg3.id), 0, "1-of-3 should be below threshold");

  assert.equal(F.flipColourOn(empty(), deg5.id), 0, "empty neighbourhood has no majority");
});

test("applyMoveOn only fills empty cells and keeps values in range", () => {
  const { cells } = F.loadBoard(48);
  const board = new Array(cells.length).fill(0);
  const start = cells[0].id;
  const fills = F.applyMoveOn(board, start, 1);
  assert.equal(board[start], 1);
  assert.ok(fills.every((id) => board[id] !== 0), "a fill left an empty cell");
  assert.ok(board.every((v) => v >= 0 && v <= 2), "value out of range");
});

test("emptyCells / isFullBoard agree", () => {
  const { cells } = F.loadBoard(48);
  const full = new Array(cells.length).fill(1);
  assert.equal(F.isFullBoard(full), true);
  assert.deepEqual(Array.from(F.emptyCells(full)), []);

  const one = full.slice();
  one[3] = 0;
  assert.equal(F.isFullBoard(one), false);
  assert.deepEqual(Array.from(F.emptyCells(one)), [3]);
});

test("groupStats counts isolated, adjacent and separated stones", () => {
  const { cells, neighbours } = F.loadBoard(48);
  const empty = () => new Array(cells.length).fill(0);
  const c0 = cells[0].id;

  let b = empty(); b[c0] = 1;
  assert.deepEqual(sizesOf(F.groupStats(b, 1)), [1]);

  b = empty(); b[c0] = 1; b[neighbours[c0][0]] = 1;
  assert.deepEqual(sizesOf(F.groupStats(b, 1)), [2]);

  b = empty();
  const far = cells.find((o) => o.id !== c0 && !neighbours[c0].includes(o.id));
  b[c0] = 1; b[far.id] = 1;
  assert.deepEqual(sizesOf(F.groupStats(b, 1)), [1, 1]);
});

test("decideWinner: draws, fewer groups, and the size tie-break", () => {
  const { cells, neighbours } = F.loadBoard(48);
  const empty = () => new Array(cells.length).fill(0);

  assert.equal(F.decideWinner(empty()), 0, "empty board should draw");

  // one group beats two groups
  const c = cells[0].id;
  const x = cells.find((p) => p.id !== c && !neighbours[c].includes(p.id));
  const y = cells.find((q) =>
    q.id !== x.id && q.id !== c &&
    !neighbours[x.id].includes(q.id) && !neighbours[c].includes(q.id));
  const fewer = empty();
  fewer[c] = 1; fewer[neighbours[c][0]] = 1;
  fewer[x.id] = 2; fewer[y.id] = 2;
  assert.equal(F.decideWinner(fewer), 1);

  // tie on group count, P1 sizes [1,1] vs P2 sizes [2,1] -> P1 wins
  const ids = cells.map((cc) => cc.id);
  let found = null;
  outer:
  for (const a of ids) for (const bb of ids) {
    if (bb <= a || neighbours[a].includes(bb)) continue;
    for (const cc of ids) for (const d of ids) {
      if (d <= cc || !neighbours[cc].includes(d)) continue;
      if ([a, bb].includes(cc) || [a, bb].includes(d)) continue;
      for (const e of ids) {
        if ([a, bb, cc, d].includes(e)) continue;
        if (neighbours[cc].includes(e) || neighbours[d].includes(e)) continue;
        const b = empty();
        b[a] = 1; b[bb] = 1; b[cc] = 2; b[d] = 2; b[e] = 2;
        if (sizesOf(F.groupStats(b, 1)).length === 2 &&
            sizesOf(F.groupStats(b, 2)).length === 2) { found = b; break outer; }
      }
    }
  }
  assert.ok(found, "no tie-break configuration found");
  assert.equal(F.decideWinner(found), 1);
});

test("seeded playouts are reproducible and reach a valid winner", () => {
  F.loadBoard(48);
  const a = F.randomPlayoutWinner(11);
  const b = F.randomPlayoutWinner(11);
  assert.equal(a, b, "same seed produced different winners");
  assert.ok([0, 1, 2].includes(a), `unexpected winner ${a}`);
});

test("mctsSearch returns a legal move (or -1)", () => {
  const { cells } = F.loadBoard(48);
  const board = new Array(cells.length).fill(0);
  const move = F.mctsSearch(board, 1, 0);
  assert.ok(move === -1 || board[move] === 0, `illegal move ${move}`);
});
