# Emacs support for gvpy / Genesis2 templates

Two major modes:

- **`genesis2-mode`** — Perl-templated Verilog/SystemVerilog (`.vp`, `.svp`, `.vph`).
- **`genesispy-mode`** — Python-templated variant used by `gvpy.py` (`.vpy`, `.gvpy`).

Both derive from `verilog-mode` and use `mmm-mode` to layer the embedded
language (`perl-mode` or `python-mode`) onto `//;` lines and backtick
expressions.

## Install

```sh
mkdir -p ~/.emacs.d/lisp/mmm
curl -sSL https://melpa.org/packages/mmm-mode-20240222.428.tar \
    | tar -x --strip-components=1 -C ~/.emacs.d/lisp/mmm
cp genesis2-mode.el  ~/.emacs.d/
cp genesispy-mode.el ~/.emacs.d/
```

Add to `~/.emacs.d/init.el`:

```elisp
(add-to-list 'load-path "~/.emacs.d/lisp/mmm")
(require 'mmm-mode)
(load "~/.emacs.d/genesis2-mode")
(load "~/.emacs.d/genesispy-mode")
(setq mmm-submode-decoration-level 0)
(setq mmm-global-mode 'maybe)
```
