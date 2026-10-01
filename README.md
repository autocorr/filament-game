# Filament

An abstract board game played on a bounded patch of the [Cairo pentagonal
tiling](https://en.wikipedia.org/wiki/Cairo_pentagonal_tiling).

## Files

- `filament.html`: standalone playable game file.
- `animate_filament.py`: Python companion sciprt that plays out games and
  renders the result to an animated GIF.
- `cairo48_spec.md`, `cairo160_spec.md`: board geometry for the size
  48 and 160 and their adjacency graphs.

## Running the animation

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```sh
uv run animate_filament.py --policy random --seed 7
uv run animate_filament.py --seed 42 --policy mcts --iters 400 -o game42.gif
uv run animate_filament.py --replay game42.gif.json
uv run animate_filament.py --self-test
```

## License

[MIT](LICENSE)
