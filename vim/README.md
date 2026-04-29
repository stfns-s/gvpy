# Vim support for gvpy / Genesis2 templates

Filetype detection and syntax highlighting for two related template flavours:

- **`genesispy`** — gvpy (Python) templates: `.vpy`, `.gvpy`
- **`genesis2`**  — Genesis2 (Perl) templates: `.vp`, `.svp`, `.vph`

Highlights:
- Verilog (or SystemVerilog if `syntax/verilog_systemverilog.vim` is on the
  runtime path) as the base.
- `//;`-prefixed Python/Perl lines highlighted via embedded `@pythonTop` /
  `@perlTop`.
- Backtick-delimited inline expressions, escape-aware (`` \` ``) and
  excluding Verilog backtick directives (`` `timescale ``, `` `ifdef ``, ...).
- Sentinel comments (`//; # endfor`, `//; # endif`, ...) highlighted bold so
  block-closers stand out.

## Install

### Manual

Copy (or symlink) the directories into your vim runtime:

```sh
mkdir -p ~/.vim/after/ftdetect ~/.vim/ftdetect ~/.vim/syntax
cp ftdetect/genesispy.vim       ~/.vim/ftdetect/genesispy.vim
cp after/ftdetect/genesis2.vim  ~/.vim/after/ftdetect/genesis2.vim
cp syntax/genesispy.vim         ~/.vim/syntax/genesispy.vim
cp syntax/genesis2.vim          ~/.vim/syntax/genesis2.vim
```

The `genesis2` ftdetect lives under `after/` and uses `set filetype=genesis2`
(force) so it wins against the `verilog_systemverilog` plugin (and any other
plugin) whose ftdetect maps `*.vp` to a different filetype and uses `au!` to
clear earlier autocmds. The `genesispy` extensions are unique to gvpy and
don't need this override.

For Neovim, swap `~/.vim` for `~/.config/nvim`.

### Plugin manager

Point your manager at this subdirectory. With `vim-plug`:

```vim
Plug 'gvpy', { 'rtp': 'vim' }
```

(Adjust the source spec for your fork/clone location.)

## Files
- `ftdetect/genesispy.vim`       — maps `*.vpy`, `*.gvpy` to filetype `genesispy`.
- `after/ftdetect/genesis2.vim`  — maps `*.vp`, `*.svp`, `*.vph` to filetype
  `genesis2`, forcing the filetype so it overrides plugins that also claim `*.vp`.
- `syntax/genesispy.vim` — Python-on-Verilog/SystemVerilog syntax for gvpy.
- `syntax/genesis2.vim`  — Perl-on-Verilog/SystemVerilog syntax for Genesis2.
