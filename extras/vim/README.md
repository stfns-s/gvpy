# Vim support for gvpy / Genesis2 templates

Filetype detection and syntax highlighting for both template variants:

- **`genesis2`** — Perl-templated Verilog/SystemVerilog (`.vp`, `.svp`, `.vph`).
- **`genesispy`** — Python-templated variant used by `gvpy.py` (`.vpy`, `.gvpy`).

Highlights:
- Verilog (or SystemVerilog if `syntax/verilog_systemverilog.vim` is on the
  runtime path) as the base.
- `//;`-prefixed embedded-language lines highlighted via `@perlTop` (genesis2)
  or `@pythonTop` (genesispy).
- Backtick-delimited inline expressions, escape-aware (`` \` ``) and
  excluding Verilog backtick directives (`` `timescale ``, `` `ifdef ``, ...).
- Comment-only embedded lines (`//; # ...`) highlighted bold so they stand out
  from regular statements.

## Install

### Manual

Copy (or symlink) all four files into your vim runtime:

```sh
mkdir -p ~/.vim/after/ftdetect ~/.vim/ftdetect ~/.vim/syntax
cp after/ftdetect/genesis2.vim  ~/.vim/after/ftdetect/genesis2.vim
cp ftdetect/genesispy.vim       ~/.vim/ftdetect/genesispy.vim
cp syntax/genesis2.vim          ~/.vim/syntax/genesis2.vim
cp syntax/genesispy.vim         ~/.vim/syntax/genesispy.vim
```

The `genesis2` ftdetect lives under `after/` and uses `set filetype=genesis2`
(force) so it wins against the `verilog_systemverilog` plugin (and any other
plugin) whose ftdetect maps `*.vp` to a different filetype and uses `au!` to
clear earlier autocmds. The `genesispy` ftdetect lives under plain `ftdetect/`
because `*.vpy` / `*.gvpy` are not claimed by other plugins.

For Neovim, swap `~/.vim` for `~/.config/nvim`.

### Plugin manager

Point your manager at this subdirectory. With `vim-plug`:

```vim
Plug 'youruser/gvpy', { 'rtp': 'extras/vim' }
```

(Adjust the source spec for your fork/clone location.)

## Files

- `after/ftdetect/genesis2.vim` — maps `*.vp`, `*.svp`, `*.vph` to filetype
  `genesis2`, forcing the filetype so it overrides plugins that also claim
  `*.vp`.
- `ftdetect/genesispy.vim` — maps `*.vpy`, `*.gvpy` to filetype `genesispy`.
- `syntax/genesis2.vim` — Perl-embedded syntax rules layered on top of
  Verilog/SystemVerilog.
- `syntax/genesispy.vim` — Python-embedded syntax rules layered on top of
  Verilog/SystemVerilog.
