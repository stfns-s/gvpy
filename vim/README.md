# Vim support for gvpy / Genesis2 templates

Filetype detection and syntax highlighting for two related template flavours:

- **`vpy`** — gvpy (Python) templates: `.vpy`, `.gvpy`
- **`vp`**  — Genesis2 (Perl) templates: `.vp`, `.svp`, `.vph`

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
cp ftdetect/vpy.vim       ~/.vim/ftdetect/vpy.vim
cp after/ftdetect/vp.vim  ~/.vim/after/ftdetect/vp.vim
cp syntax/vpy.vim         ~/.vim/syntax/vpy.vim
cp syntax/vp.vim          ~/.vim/syntax/vp.vim
```

The `vp` ftdetect lives under `after/` and uses `set filetype=vp` (force) so
it wins against the `verilog_systemverilog` plugin (and any other plugin)
whose ftdetect maps `*.vp` to a different filetype and uses `au!` to clear
earlier autocmds. The `vpy` extensions are unique to gvpy and don't need
this override.

For Neovim, swap `~/.vim` for `~/.config/nvim`.

### Plugin manager

Point your manager at this subdirectory. With `vim-plug`:

```vim
Plug 'gvpy', { 'rtp': 'vim' }
```

(Adjust the source spec for your fork/clone location.)

## Files
- `ftdetect/vpy.vim`       — maps `*.vpy`, `*.gvpy` to filetype `vpy`.
- `after/ftdetect/vp.vim`  — maps `*.vp`, `*.svp`, `*.vph` to filetype `vp`,
  forcing the filetype so it overrides plugins that also claim `*.vp`.
- `syntax/vpy.vim` — Python-on-Verilog/SystemVerilog syntax for gvpy.
- `syntax/vp.vim`  — Perl-on-Verilog/SystemVerilog syntax for Genesis2.
