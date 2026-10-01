#!/usr/bin/env python3
"""Render an animated GIF of a Filament playout on Cairo-48.

A standalone companion to filament.html.  It ports the Cairo-48 geometry, the
cascading-fill rules and the UCT Monte-Carlo search to Python, generates a
playout, and renders *only the board* to an animated GIF with Pillow.  It never
touches the HTML.

The design goal is reproducibility and low coupling:

  * the playout is a plain JSON "event log" (seed, winner, moves);
  * generation and rendering only talk through that log -- save it and replay
    the exact same animation later with --replay, no search and no RNG;
  * the static board is rasterised once and cached; each frame only composites
    stones over it, so rendering is cheap no matter how many frames there are;
  * MCTS uses a fixed iteration count and a seeded RNG, so runs are byte-for-
    byte reproducible (use --think for a wall-clock search when you don't care).

Visual conventions:
  * the stone just placed is ringed in a contrasting colour (white on a black
    stone, near-black on a white stone);
  * each cascading fill appears one at a time, marked with a small GRAY dot;
  * when the game ends the winning side's stones are ringed in YELLOW.

Examples
--------
    uv run animate_filament.py --policy random --seed 7
    uv run animate_filament.py --seed 42 --policy mcts --iters 400 -o game42.gif
    uv run animate_filament.py --replay game42.gif.json
    uv run animate_filament.py --self-test
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import Counter
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

# =========================================================================
# 1. BOARD -- cells, snub-square geometry, adjacency
# =========================================================================

# id, x, y, coloured-cell label (from cairo48_spec.md / filament.html)
CELLS = [
    (0, -2.3660, -2.7321, "C"), (1, -2.8660, -1.8660, "A"),
    (2, -0.5000, -3.2321, "C"), (3, -1.5000, -3.2321, "B"),
    (4, -1.8660, -1.8660, "B"), (5, -1.0000, -2.3660, "A"),
    (6, -1.8660, -0.8660, "A"), (7, -2.8660, -0.8660, "C"),
    (8, -3.2321, 0.5000, "C"), (9, -2.3660, 0.0000, "B"),
    (10, -3.2321, 1.5000, "B"), (11, -0.0000, -2.3660, "B"),
    (12, 0.8660, -2.8660, "A"), (13, -0.0000, -1.3660, "A"),
    (14, -1.0000, -1.3660, "C"), (15, -1.3660, 0.0000, "C"),
    (16, -0.5000, -0.5000, "B"), (17, -1.3660, 1.0000, "B"),
    (18, -2.3660, 1.0000, "A"), (19, -2.7321, 2.3660, "A"),
    (20, -1.8660, 1.8660, "C"), (21, 1.8660, -2.8660, "B"),
    (22, 1.8660, -1.8660, "A"), (23, 0.8660, -1.8660, "C"),
    (24, 0.5000, -0.5000, "C"), (25, 1.3660, -1.0000, "B"),
    (26, 0.5000, 0.5000, "B"), (27, -0.5000, 0.5000, "A"),
    (28, -0.8660, 1.8660, "A"), (29, 0.0000, 1.3660, "C"),
    (30, -0.8660, 2.8660, "C"), (31, -1.8660, 2.8660, "B"),
    (32, 2.7321, -2.3660, "C"), (33, 2.3660, -1.0000, "C"),
    (34, 3.2321, -1.5000, "B"), (35, 2.3660, -0.0000, "B"),
    (36, 1.3660, -0.0000, "A"), (37, 1.0000, 1.3660, "A"),
    (38, 1.8660, 0.8660, "C"), (39, 1.0000, 2.3660, "C"),
    (40, 0.0000, 2.3660, "B"), (41, 0.5000, 3.2321, "A"),
    (42, 3.2321, -0.5000, "A"), (43, 2.8660, 0.8660, "A"),
    (44, 2.8660, 1.8660, "C"), (45, 1.8660, 1.8660, "B"),
    (46, 1.5000, 3.2321, "B"), (47, 2.3660, 2.7321, "A"),
]

N_CELLS = len(CELLS)
ALL_IDS = tuple(c[0] for c in CELLS)


def _build_cells_geo():
    """Return the 48 cells with their Cairo-pentagon vertices.

    The pentagon is derived from the snub-square lattice (the cell-adjacency
    graph of the Cairo tiling), exactly as filament.html's buildCells does.
    """
    s = (1 + math.sqrt(3)) / 2
    v1 = (s * math.cos(math.pi / 6), s * math.sin(math.pi / 6))
    v2 = (s * math.cos(2 * math.pi / 3), s * math.sin(2 * math.pi / 3))

    def rnd(v):
        return round(v, 4)

    def key(x, y):
        return f"{rnd(x)},{rnd(y)}"

    def rot(p, deg):
        a = math.radians(deg)
        return (p[0] * math.cos(a) - p[1] * math.sin(a),
                p[0] * math.sin(a) + p[1] * math.cos(a))

    def square_corners(i, j):
        c = (i * v1[0] + j * v2[0], i * v1[1] + j * v2[1])
        d = 0 if (i + j) % 2 == 0 else 60
        return [(c[0] + p[0], c[1] + p[1])
                for p in (rot(q, d) for q in
                          ((0.5, 0.5), (-0.5, 0.5), (-0.5, -0.5), (0.5, -0.5)))]

    # full infinite-ish lattice, needed so rim pentagons close correctly
    grid = {}
    for i in range(-16, 17):
        for j in range(-16, 17):
            for p in square_corners(i, j):
                grid.setdefault(key(*p), p)

    def neighbours(k):
        x, y = grid[k]
        return [k2 for k2, p in grid.items()
                if k2 != k and math.hypot(p[0] - x, p[1] - y) < 1.05]

    def pentagon(k):
        x0, y0 = grid[k]
        ns = neighbours(k)
        ns.sort(key=lambda a: math.atan2(grid[a][1] - y0, grid[a][0] - x0))
        verts = []
        for t, a in enumerate(ns):
            b = ns[(t + 1) % len(ns)]
            x1, y1 = grid[a]
            x2, y2 = grid[b]
            if abs(math.hypot(x1 - x2, y1 - y2) - 1) < 1e-3:
                verts.append(((x0 + x1 + x2) / 3, (y0 + y1 + y2) / 3))
            else:
                verts.append(((x1 + x2) / 2, (y1 + y2) / 2))
        return verts

    return [{"id": cid, "x": x, "y": y, "colour": col,
             "pentagon": pentagon(key(x, y))}
            for cid, x, y, col in CELLS]


CELLS_GEO = _build_cells_geo()
CELL_BY_ID = {c["id"]: c for c in CELLS_GEO}


def _build_neighbours():
    """Two cells are adjacent iff their centres are exactly one unit apart."""
    nb = {}
    for c in CELLS_GEO:
        nb[c["id"]] = [
            o["id"] for o in CELLS_GEO
            if o["id"] != c["id"]
            and abs(math.hypot(o["x"] - c["x"], o["y"] - c["y"]) - 1) < 1e-3
        ]
    return nb


NEIGHBOURS = _build_neighbours()


# =========================================================================
# 2. RULES -- cascading fills and scoring (port of filament.html)
# =========================================================================

def flip_colour_on(board, cid, nb):
    """Colour that should fill an empty cell, or 0 if no local majority."""
    c1 = c2 = 0
    for n in nb[cid]:
        if board[n] == 1:
            c1 += 1
        elif board[n] == 2:
            c2 += 1
    majority = 1 if c1 > c2 else 2 if c2 > c1 else 0
    if not majority:
        return 0
    threshold = 3 if len(nb[cid]) == 5 else 2
    if (c1 if majority == 1 else c2) < threshold:
        return 0
    return 3 - majority


def apply_move(board, cid, player, nb):
    """Place a stone, then cascade.  Returns fills in play-out order."""
    board[cid] = player
    fills = []
    changed = True
    while changed:
        changed = False
        wave = []
        for c in ALL_IDS:
            if board[c]:
                continue
            col = flip_colour_on(board, c, nb)
            if col:
                wave.append((c, col))
        for c, col in wave:
            board[c] = col
            fills.append((c, col))
        if wave:
            changed = True
    return fills


def empty_cells(board):
    return [c for c in ALL_IDS if not board[c]]


def is_full(board):
    return all(board[c] for c in ALL_IDS)


def group_stats(board, player):
    seen = set()
    sizes = []
    for c in ALL_IDS:
        if board[c] != player or c in seen:
            continue
        size = 0
        stack = [c]
        seen.add(c)
        while stack:
            cur = stack.pop()
            size += 1
            for n in NEIGHBOURS[cur]:
                if n not in seen and board[n] == player:
                    seen.add(n)
                    stack.append(n)
        sizes.append(size)
    sizes.sort(reverse=True)
    return {"count": len(sizes), "sizes": sizes}


def compare_group_sizes(a_sizes, b_sizes):
    if len(a_sizes) != len(b_sizes):
        return 1 if len(a_sizes) < len(b_sizes) else 2
    for x, y in zip(a_sizes, b_sizes):
        if x != y:
            return 1 if x < y else 2
    return 0


def decide_winner(board):
    return compare_group_sizes(
        group_stats(board, 1)["sizes"], group_stats(board, 2)["sizes"]
    )


# =========================================================================
# 3. PLAYOUT -- seeded random and deterministic UCT Monte-Carlo
# =========================================================================

RNG = random.Random()
MCTS_C = math.sqrt(2)


@dataclass
class Node:
    board: list
    to_move: int
    parent: "Node | None" = None
    move: int | None = None
    visits: int = 0
    wins: float = 0.0
    children: list = field(default_factory=list)
    untried: list = field(default_factory=list)


def make_node(board, to_move, parent, move):
    untried = empty_cells(board)
    RNG.shuffle(untried)
    return Node(board=board[:], to_move=to_move, parent=parent, move=move,
                untried=untried)


def best_uct(node):
    log_n = math.log(node.visits)
    best, best_value = None, -math.inf
    for child in node.children:
        value = child.wins / child.visits + MCTS_C * math.sqrt(log_n / child.visits)
        if value > best_value:
            best_value, best = value, child
    return best


def select_and_expand(root):
    node = root
    while True:
        if node.untried:
            cid = node.untried.pop()
            board = node.board[:]
            apply_move(board, cid, node.to_move, NEIGHBOURS)
            child = make_node(board, 3 - node.to_move, node, cid)
            node.children.append(child)
            return child
        if not node.children:
            return node
        node = best_uct(node)


def simulate(board, to_move):
    b = board[:]
    player = to_move
    while True:
        empties = empty_cells(b)
        if not empties:
            break
        cid = empties[RNG.randrange(len(empties))]
        apply_move(b, cid, player, NEIGHBOURS)
        player = 3 - player
    return decide_winner(b)


def backpropagate(node, winner_player):
    while node:
        node.visits += 1
        if node.parent and (winner_player == 0 or node.parent.to_move == winner_player):
            node.wins += 0.5 if winner_player == 0 else 1
        node = node.parent


def mcts_search(board, player, iters, think_s=None):
    root = make_node(board, player, None, None)

    def rollout():
        leaf = select_and_expand(root)
        backpropagate(leaf, simulate(leaf.board, leaf.to_move))

    if think_s:
        deadline = time.perf_counter() + think_s
        while time.perf_counter() < deadline:
            rollout()
    else:
        for _ in range(iters):
            rollout()

    if not root.children:
        return -1
    return max(root.children, key=lambda c: c.visits).move


def play_game(seed, policy="mcts", iters=400, think_s=None, verbose=False):
    """Generate a full playout as a JSON-friendly event log."""
    RNG.seed(seed)
    board = [0] * N_CELLS
    current = 1
    moves = []
    while not is_full(board):
        if policy == "random":
            empties = empty_cells(board)
            cid = empties[RNG.randrange(len(empties))]
        else:
            cid = mcts_search(board, current, iters, think_s)
        if cid < 0:
            break
        fills = apply_move(board, cid, current, NEIGHBOURS)
        moves.append({"player": current, "cell": cid,
                      "fills": [[c, col] for c, col in fills]})
        if verbose:
            print(f"  move {len(moves):2d}: P{current} -> cell {cid:2d} "
                  f"(+{len(fills)} fill)", flush=True)
        current = 3 - current
    winner = decide_winner(board)
    return {"seed": seed, "policy": policy, "iters": iters,
            "winner": winner, "moves": moves}


def replay_board(log):
    """Rebuild the final board from an event log (verification / replay)."""
    board = [0] * N_CELLS
    last = 0
    for m in log["moves"]:
        last = m["player"]
        apply_move(board, m["cell"], m["player"], NEIGHBOURS)
    return board, last


# =========================================================================
# 4. TIMELINE -- event log to a flat list of display beats
# =========================================================================

@dataclass
class Beat:
    board: list          # board state at this beat
    placed: int | None   # cell just placed (contrasting ring)
    fills: list          # fill cells shown so far this turn (GRAY dots)
    highlight: int | None
    duration_ms: int


def build_beats(log, hold_ms=1000, fill_ms=500, wait_ms=1000, end_ms=5000,
                lead_ms=1000):
    board = [0] * N_CELLS
    beats = []
    if lead_ms:
        # empty board, held before the first stone is placed
        beats.append(Beat(list(board), None, [], None, lead_ms))
    for m in log["moves"]:
        cid, player = m["cell"], m["player"]
        board[cid] = player
        beats.append(Beat(list(board), cid, [], None, hold_ms))
        shown = []
        for fcid, col in m["fills"]:
            board[fcid] = col
            shown.append(fcid)
            beats.append(Beat(list(board), cid, list(shown), None, fill_ms))
        # pause on the finished turn before the opponent is allowed to move
        beats.append(Beat(list(board), cid, list(shown), None, wait_ms))
    winner = log.get("winner", 0) or None
    beats.append(Beat(list(board), None, [], winner, end_ms))
    return beats


# =========================================================================
# 5. RENDER -- cached static background + per-beat stone compositing
# =========================================================================

CELL_COLOUR = {"A": (242, 216, 167), "B": (188, 220, 198), "C": (188, 204, 238)}
BG = (29, 32, 38)
GRID = (58, 63, 74)
STONE_BASE = (32, 35, 41)
STONE_WHITE = (242, 242, 240)
STONE_EDGE = (14, 15, 19)
GRAY = (150, 156, 166)
YELLOW = (255, 213, 79)

STONE_R = 0.42
MARK_R = 0.135
RING_R = 0.26
RING_W = 0.06
HALO_R = 0.5


class Layout:
    """World (cell-centre) coordinates -> pixel coordinates."""

    def __init__(self, cells, pixels, margin):
        xs, ys = [], []
        for c in cells:
            for x, y in c["pentagon"]:
                xs.append(x)
                ys.append(y)
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        w, h = maxx - minx, maxy - miny
        self.k = min((pixels - 2 * margin) / w, (pixels - 2 * margin) / h)
        self.ox = (pixels - self.k * w) / 2 - self.k * minx
        self.oy = (pixels - self.k * h) / 2 - self.k * miny

    def pt(self, x, y):
        return (self.ox + self.k * x, self.oy + self.k * y)


def build_background(layout, pixels):
    """Rasterise the static board once at full supersampled resolution."""
    img = Image.new("RGB", (pixels, pixels), BG)
    d = ImageDraw.Draw(img)
    scene = [[layout.pt(x, y) for x, y in c["pentagon"]] for c in CELLS_GEO]
    for c, pts in zip(CELLS_GEO, scene):
        d.polygon(pts, fill=CELL_COLOUR[c["colour"]])
    lw = max(1, int(0.03 * layout.k))
    for pts in scene:
        d.line(pts + [pts[0]], fill=GRID, width=lw, joint="curve")
    return img


def render_frame(bg, layout, size, board, placed, fills, highlight):
    """Composite one beat's stones and markers over a copy of the background."""
    img = bg.copy()
    d = ImageDraw.Draw(img)
    r = STONE_R * layout.k
    edge = max(1, int(0.03 * layout.k))

    for c in CELLS_GEO:
        s = board[c["id"]]
        if not s:
            continue
        x, y = layout.pt(c["x"], c["y"])
        base = STONE_WHITE if s == 2 else STONE_BASE
        d.ellipse([x - r, y - r, x + r, y + r], fill=base, outline=STONE_EDGE,
                  width=edge)

    mr = MARK_R * layout.k
    for cid in fills:
        c = CELL_BY_ID[cid]
        x, y = layout.pt(c["x"], c["y"])
        d.ellipse([x - mr, y - mr, x + mr, y + mr], fill=GRAY)
    if placed is not None:
        c = CELL_BY_ID[placed]
        s = board[placed]
        x, y = layout.pt(c["x"], c["y"])
        rr = RING_R * layout.k
        d.ellipse([x - rr, y - rr, x + rr, y + rr],
                  outline=STONE_WHITE if s == 1 else STONE_EDGE,
                  width=max(1, int(RING_W * layout.k)))

    if highlight:
        hr = HALO_R * layout.k
        hw = max(1, int(0.05 * layout.k))
        for c in CELLS_GEO:
            if board[c["id"]] == highlight:
                x, y = layout.pt(c["x"], c["y"])
                d.ellipse([x - hr, y - hr, x + hr, y + hr], outline=YELLOW,
                          width=hw)

    return img.resize((size, size), Image.LANCZOS)


# =========================================================================
# 6. GIF -- shared palette so frames never flicker
# =========================================================================

def save_gif(frames, durations_ms, path, colors=64):
    """Quantise every frame to one global palette and write an animated GIF."""
    if not frames:
        raise ValueError("no frames to write")
    # Build the palette from a cheap montage of thumbnails of every frame, and
    # overwrite the first few cells with solid swatches of the key colours.
    # Without those swatches median-cut drops the tiny marker colours entirely
    # (a few dozen red pixels) and the red/gray markers come out the same.
    sw = 48
    key_colours = [BG, GRID, CELL_COLOUR["A"], CELL_COLOUR["B"],
                   CELL_COLOUR["C"], STONE_BASE, STONE_WHITE, STONE_EDGE,
                   GRAY, YELLOW]
    thumbs = [f.resize((sw, sw), Image.LANCZOS) for f in frames]
    width = sw * max(len(thumbs), len(key_colours))
    montage = Image.new("RGB", (width, sw))
    for i, t in enumerate(thumbs):
        montage.paste(t, (i * sw, 0))
    for i, colour in enumerate(key_colours):
        montage.paste(Image.new("RGB", (sw, sw), colour), (i * sw, 0))
    palette = montage.quantize(colors=min(256, colors), method=Image.MEDIANCUT)

    pframes = [f.quantize(palette=palette, dither=Image.Dither.NONE)
               for f in frames]
    durations = [max(20, int(round(d))) for d in durations_ms]
    for pf, d in zip(pframes, durations):
        pf.info["duration"] = d
    pframes[0].save(path, save_all=True, append_images=pframes[1:],
                    duration=durations, loop=0, optimize=True, disposal=1)


# =========================================================================
# 7. SELF-TEST -- invariants that guard the port against silent drift
# =========================================================================

def run_self_test():
    problems = []

    def check(name, ok, detail=""):
        print(f"  [{'ok' if ok else 'FAIL'}] {name}{(' -- ' + detail) if detail and not ok else ''}")
        if not ok:
            problems.append(name)

    check("48 cells", N_CELLS == 48)
    check("all pentagons have 5 vertices",
          all(len(c["pentagon"]) == 5 for c in CELLS_GEO),
          str([c["id"] for c in CELLS_GEO if len(c["pentagon"]) != 5]))

    deg = Counter(len(NEIGHBOURS[c]) for c in ALL_IDS)
    check("degrees are all odd (28x5, 20x3)", deg == Counter({5: 28, 3: 20}),
          str(dict(deg)))

    cols = Counter(c["colour"] for c in CELLS_GEO)
    check("colour counts 16/16/16", cols == Counter({"A": 16, "B": 16, "C": 16}),
          str(dict(cols)))

    check("adjacency is symmetric",
          all(a in NEIGHBOURS[b] for a in ALL_IDS for b in NEIGHBOURS[a]))

    # cascade fills must terminate, be empty cells, and be exact opposites
    board = [0] * N_CELLS
    apply_move(board, 16, 1, NEIGHBOURS)
    check("apply_move leaves a full-ish consistent board",
          all(0 <= v <= 2 for v in board))

    # determinism: same seed -> identical log
    a = play_game(1, policy="random")
    b = play_game(1, policy="random")
    check("random playout is seed-deterministic", a == b)
    c = play_game(2, policy="random")
    check("different seed -> different playout", a != c)

    board2, _ = replay_board(a)
    check("replay reproduces the final board",
          decide_winner(board2) == a["winner"])

    # tie-break: a player missing a group at a cascade position counts as zero
    check("fewer groups wins cascade",
          compare_group_sizes([4, 2, 1], [4, 2, 1, 1]) == 1)
    check("equal sizes draw", compare_group_sizes([4, 2, 1], [4, 2, 1]) == 0)
    check("smaller group wins cascade",
          compare_group_sizes([4, 2, 1], [4, 1, 1]) == 2)
    check("empty sizes draw", compare_group_sizes([], []) == 0)

    print("self-test:", "PASS" if not problems else f"FAIL ({len(problems)})")
    return not problems


# =========================================================================
# 8. CLI
# =========================================================================

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Animate a Filament game to GIF.")
    p.add_argument("--seed", type=int, default=None,
                   help="RNG seed for a fresh playout (default: random)")
    p.add_argument("--policy", choices=("mcts", "random"), default="mcts",
                   help="how to choose moves (default: mcts)")
    p.add_argument("--iters", type=int, default=400,
                   help="MCTS iterations per move; reproducible (default: 400)")
    p.add_argument("--think", type=float, default=None,
                   help="wall-clock seconds per move instead of --iters "
                        "(stronger but not reproducible)")
    p.add_argument("--replay", default=None,
                   help="render a saved event-log JSON instead of searching")
    p.add_argument("--out", default=None,
                   help="output GIF path (default filament_<seed>.gif)")
    p.add_argument("--size", type=int, default=480,
                   help="output frame size in px (default: 480)")
    p.add_argument("--ss", type=int, default=2,
                   help="supersampling factor for antialiasing (default: 2)")
    p.add_argument("--lead-ms", type=int, default=1000,
                   help="hold the empty board before the first placement "
                        "(default: 1000)")
    p.add_argument("--hold-ms", type=int, default=1000,
                   help="display time of a placed stone (default: 1000)")
    p.add_argument("--fill-ms", type=int, default=500,
                   help="display time of each cascade fill (default: 500)")
    p.add_argument("--wait-ms", type=int, default=1000,
                   help="pause after a turn's fills before the opponent moves "
                        "(default: 1000)")
    p.add_argument("--end-ms", type=int, default=5000,
                   help="display time of the winner frame (default: 5000)")
    p.add_argument("--colors", type=int, default=64,
                   help="size of the shared GIF palette (default: 64)")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--self-test", action="store_true",
                   help="run port invariant checks and exit")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.self_test:
        raise SystemExit(0 if run_self_test() else 1)

    if args.replay:
        with open(args.replay) as f:
            log = json.load(f)
        base = args.replay[:-5] if args.replay.endswith(".json") else args.replay
        out = args.out or (base if base.lower().endswith(".gif") else base + ".gif")
        print(f"Replaying {len(log['moves'])} moves from {args.replay}")
    else:
        seed = args.seed if args.seed is not None else random.randrange(1 << 31)
        t0 = time.perf_counter()
        print(f"Playing: seed={seed} policy={args.policy} "
              f"iters={args.iters}" + (f" think={args.think}s" if args.think else ""))
        log = play_game(seed, policy=args.policy, iters=args.iters,
                        think_s=args.think, verbose=args.verbose)
        print(f"  generated in {time.perf_counter() - t0:.2f}s "
              f"({len(log['moves'])} moves)")
        out = args.out or f"filament_{seed}.gif"
        with open(out + ".json", "w") as f:
            json.dump(log, f, indent=0)
        print(f"Saved playout to {out}.json")

    winner = log.get("winner", 0)
    print("Winner: " + ({1: "Black (P1)", 2: "White (P2)"}.get(winner, "Draw")))

    beats = build_beats(log, hold_ms=args.hold_ms, fill_ms=args.fill_ms,
                        wait_ms=args.wait_ms, end_ms=args.end_ms,
                        lead_ms=args.lead_ms)
    pixels = args.size * args.ss
    layout = Layout(CELLS_GEO, pixels, margin=int(pixels * 0.03))
    bg = build_background(layout, pixels)

    t0 = time.perf_counter()
    frames = [render_frame(bg, layout, args.size, b.board, b.placed, b.fills,
                           b.highlight) for b in beats]
    durations = [b.duration_ms for b in beats]
    save_gif(frames, durations, out, colors=args.colors)
    print(f"Rendered {len(frames)} beats in {time.perf_counter() - t0:.2f}s")
    print(f"Done: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
