# Cairo-48: a 48-cell all-odd Cairo board with the canonical 3-colouring

## 1. The lattice
Let s = (1+sqrt(3))/2, v1 = s*(cos30, sin30), v2 = s*(cos120, sin120).
Place a unit square centred at i*v1 + j*v2 for all integers i,j, rotated 0 deg if i+j is even, 60 deg if odd.
**Cells** = the square corners (each corner is shared by exactly 2 squares).
**Adjacency** = two cells are adjacent iff their centres are at distance 1.

This is the **snub-square lattice**, which *is* the cell-adjacency graph of the **Cairo pentagonal tiling** (Cairo = dual of snub-square). It is 5-regular and vertex-transitive.

## 2. The board (Cairo-48)
The 48 cells listed below. Properties, all verified:
- **connected**, **hole-free** (simply connected)
- **every cell has odd degree**: 28 cells of degree 5 (interior), 20 of degree 3 (rim). No degree-4 cells.
- This is why it matters: 5 and 3 are both odd, so **local majority is tie-free everywhere, including the boundary**. Flip thresholds: 3-of-5 interior, 2-of-3 rim.
- Found by MaxSAT (parity constraints, degree restricted to {3,5}). The minimal such board is 14 cells; the next hole-free ones found were 48, 160, 336.

## 3. The 3-colouring (Colouring A)
The Cairo cell graph has chromatic number exactly **3** (>=3 from its triangles, <=3 by explicit periodic colouring).
Up to relabelling there are exactly **two** 3-colourings of the infinite lattice; they are period-3 stripes and are exchanged by the tiling's 90 deg rotation. Colouring A is one of them.

**Closed form.** Let b1 = v1 + v2 (the stripe axis). For a cell at position p, set
    k = round( 6 * (p . b1) / |b1|^2 )  mod 9      (k is never 0, 3 or 6)
Then:
    A  if k in {1, 5}
    B  if k in {2, 7}
    C  if k in {4, 8}

**Local signature (holds at every degree-5 cell):** 0 neighbours of its own colour, **3 of one other colour and 2 of the third** — never 4-1 or 5-0. Note that 3 = the interior flip threshold.
Every degree-3 Cairo vertex (3 mutually adjacent cells) shows all three colours. Every degree-4 Cairo vertex (4 cells in a 4-cycle) shows the multiset (2,1,1), the repeat on the two diagonal cells.

**On Cairo-48:** colour counts are exactly **16 / 16 / 16**.
  - A: 16 cells (9 interior, 7 rim)
  - B: 16 cells (10 interior, 6 rim)
  - C: 16 cells (9 interior, 7 rim)

Caveat: on a finite board the colouring is *not* forced (boundary freedom admits many non-periodic proper 3-colourings). Colouring A must be **imposed**. Doing so breaks the board's 4-fold rotational symmetry — a chiral choice.

## 4. Cell table
Coordinates are the cell centres in the plane (= snub-square lattice points).

| id | x | y | deg | colour | neighbours |
|---|---|---|---|---|---|
| 0 | -2.3660 | -2.7321 | 3 | C | 1,3,4 |
| 1 | -2.8660 | -1.8660 | 3 | A | 0,4,7 |
| 2 | -0.5000 | -3.2321 | 3 | C | 3,5,11 |
| 3 | -1.5000 | -3.2321 | 3 | B | 0,2,5 |
| 4 | -1.8660 | -1.8660 | 5 | B | 0,1,5,6,14 |
| 5 | -1.0000 | -2.3660 | 5 | A | 2,3,4,11,14 |
| 6 | -1.8660 | -0.8660 | 5 | A | 4,7,9,14,15 |
| 7 | -2.8660 | -0.8660 | 3 | C | 1,6,9 |
| 8 | -3.2321 | 0.5000 | 3 | C | 9,10,18 |
| 9 | -2.3660 | 0.0000 | 5 | B | 6,7,8,15,18 |
| 10 | -3.2321 | 1.5000 | 3 | B | 8,18,19 |
| 11 | -0.0000 | -2.3660 | 5 | B | 2,5,12,13,23 |
| 12 | 0.8660 | -2.8660 | 3 | A | 11,21,23 |
| 13 | -0.0000 | -1.3660 | 5 | A | 11,14,16,23,24 |
| 14 | -1.0000 | -1.3660 | 5 | C | 4,5,6,13,16 |
| 15 | -1.3660 | 0.0000 | 5 | C | 6,9,16,17,27 |
| 16 | -0.5000 | -0.5000 | 5 | B | 13,14,15,24,27 |
| 17 | -1.3660 | 1.0000 | 5 | B | 15,18,20,27,28 |
| 18 | -2.3660 | 1.0000 | 5 | A | 8,9,10,17,20 |
| 19 | -2.7321 | 2.3660 | 3 | A | 10,20,31 |
| 20 | -1.8660 | 1.8660 | 5 | C | 17,18,19,28,31 |
| 21 | 1.8660 | -2.8660 | 3 | B | 12,22,32 |
| 22 | 1.8660 | -1.8660 | 5 | A | 21,23,25,32,33 |
| 23 | 0.8660 | -1.8660 | 5 | C | 11,12,13,22,25 |
| 24 | 0.5000 | -0.5000 | 5 | C | 13,16,25,26,36 |
| 25 | 1.3660 | -1.0000 | 5 | B | 22,23,24,33,36 |
| 26 | 0.5000 | 0.5000 | 5 | B | 24,27,29,36,37 |
| 27 | -0.5000 | 0.5000 | 5 | A | 15,16,17,26,29 |
| 28 | -0.8660 | 1.8660 | 5 | A | 17,20,29,30,40 |
| 29 | 0.0000 | 1.3660 | 5 | C | 26,27,28,37,40 |
| 30 | -0.8660 | 2.8660 | 3 | C | 28,31,40 |
| 31 | -1.8660 | 2.8660 | 3 | B | 19,20,30 |
| 32 | 2.7321 | -2.3660 | 3 | C | 21,22,34 |
| 33 | 2.3660 | -1.0000 | 5 | C | 22,25,34,35,42 |
| 34 | 3.2321 | -1.5000 | 3 | B | 32,33,42 |
| 35 | 2.3660 | -0.0000 | 5 | B | 33,36,38,42,43 |
| 36 | 1.3660 | -0.0000 | 5 | A | 24,25,26,35,38 |
| 37 | 1.0000 | 1.3660 | 5 | A | 26,29,38,39,45 |
| 38 | 1.8660 | 0.8660 | 5 | C | 35,36,37,43,45 |
| 39 | 1.0000 | 2.3660 | 5 | C | 37,40,41,45,46 |
| 40 | 0.0000 | 2.3660 | 5 | B | 28,29,30,39,41 |
| 41 | 0.5000 | 3.2321 | 3 | A | 39,40,46 |
| 42 | 3.2321 | -0.5000 | 3 | A | 33,34,35 |
| 43 | 2.8660 | 0.8660 | 3 | A | 35,38,44 |
| 44 | 2.8660 | 1.8660 | 3 | C | 43,45,47 |
| 45 | 1.8660 | 1.8660 | 5 | B | 37,38,39,44,47 |
| 46 | 1.5000 | 3.2321 | 3 | B | 39,41,47 |
| 47 | 2.3660 | 2.7321 | 3 | A | 44,45,46 |
