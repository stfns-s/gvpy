# gvpy — agent notes

Project-specific guidance. Global rules at `~/.claude/CLAUDE.md` still apply.

## Companion project

`gvpy.py`'s CLI tracks `genesispy.gvpy_cli` at
`/home/stefanos/src/genesispy-port/genesispy/src/genesispy/gvpy_cli.py`.
When changing flags in `gvpy.py`, check that file first. Deviations are
intentional: `--rawpython` is gvpy-only; `--extension` / `--gvpy-strict`
are port-only.

## gvp.pl vs gvpy.py

`gvp.pl` is the Perl original and keeps the legacy flag names
(`--libdirs`, `--incdirs`, `--defparam`). `gvpy.py` is the Python port
and adopted the renames (`--py-path`, `--inc-path`, `-p`/`--parameter`)
with hidden deprecation aliases. Do not "harmonise" by renaming gvp.pl.

## Symlinked test fixtures

Several `tests/cases/<N>/flags.pl` and `cmd.pl` files are symlinks to
their `.py` siblings (`ls -L` to check). Editing the `.py` side silently
changes Perl-mode test inputs. Break the symlink first when the two
modes need different flags.

## Version lives in four places

- `__version__` in `gvpy.py`
- `our $VERSION` in `gvp.pl`
- `tests/cases/54_version/expected_out_contains.py`
- `tests/cases/54_version/expected_out_contains.pl`

Bump all four together, then `bash tests/run_tests.sh both` before tagging.

## Release ritual

1. Bump version (four files above).
2. `bash tests/run_tests.sh both` — must be 0 failures.
3. Commit.
4. Tag `vX.Y.Z` (lightweight, `v`-prefixed; not annotated).
5. `git push origin main vX.Y.Z`.

## Remote topology

One remote, `origin`, with two push URLs (github.com + gitsrv.us.int.ramyx.com).
A single `git push origin` hits both. There is no `gitsrv` remote.
