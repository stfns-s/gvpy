" Vim syntax file
" Language: gvp Python template (.vpy / .gvpy)
" Mirrors ~/.vim/syntax/genesis2.vim with @pythonTop in place of @perlTop,
" plus two refinements: escape-aware backticks and Verilog-directive exclusion.

if version < 600
    syntax clear
elseif exists("b:current_syntax")
    finish
endif

" Base: SystemVerilog if available, else plain Verilog.
if !empty(globpath(&runtimepath, 'syntax/verilog_systemverilog.vim'))
    ru! syntax/verilog_systemverilog.vim
    set ft=verilog_systemverilog
else
    ru! syntax/verilog.vim
    set ft=verilog
endif
unlet! b:current_syntax

" Embedded Python.
syn include @pythonTop syntax/python.vim

" //; # ... -- comment-only Python lines (block-closing sentinels like
" `# end if`, `# endif`, `# end for`, `# endfor`). Highlighted as comments
" but bold so they stand out as structural markers.
syn match vpySentinel +//;\s*#.*$+ containedin=ALL

" //;<rest> -- the rest of the line is Python (excluding the sentinel form
" above, which is matched separately).
syn region vpyLine matchgroup=vpyDelim
    \ start=+//;\(\s*#\)\@!+ end=+$+
    \ keepend containedin=ALL contains=@pythonTop

" `expr` -- inline Python expression.
"   * \\\@<! is "not preceded by a backslash" so the gvpy literal-backtick
"     escape (\`) does not open or close the region.
"   * \@! after the start backtick excludes the Verilog `directive keywords
"     so they are not mis-parsed as opening a Python region.
syn region vpyInline matchgroup=vpyDelim
    \ start=#\\\@<!`\(timescale\|default_nettype\|include\|ifdef\|if\|ifndef\|else\|endif\)\@!#
    \ end=#\\\@<!`#
    \ keepend containedin=ALL contains=@pythonTop oneline

hi link vpyDelim PreProc

" Make embedded Python visually distinct from Verilog (which uses Statement).
hi vpyPyKeyword  cterm=bold gui=bold ctermfg=magenta guifg=magenta
hi vpyPyBuiltin  cterm=bold gui=bold
hi vpyPyFunction cterm=bold gui=bold
hi link pythonStatement   vpyPyKeyword
hi link pythonConditional vpyPyKeyword
hi link pythonRepeat      vpyPyKeyword
hi link pythonOperator    vpyPyKeyword
hi link pythonException   vpyPyKeyword
hi link pythonInclude     vpyPyKeyword
hi link pythonBuiltin     vpyPyBuiltin
hi link pythonFunction    vpyPyFunction
hi link pythonDecorator   vpyPyKeyword

" Sentinel highlight: same foreground as Comment, but bold. We can't use
" `:hi link` (it would clobber the bold attribute), so resolve Comment's
" colours at load time and apply them explicitly.
let s:_cterm_fg = synIDattr(synIDtrans(hlID('Comment')), 'fg', 'cterm')
let s:_gui_fg   = synIDattr(synIDtrans(hlID('Comment')), 'fg', 'gui')
exe 'hi vpySentinel cterm=bold gui=bold'
    \ . (!empty(s:_cterm_fg) ? ' ctermfg=' . s:_cterm_fg : '')
    \ . (!empty(s:_gui_fg)   ? ' guifg='   . s:_gui_fg   : '')
unlet s:_cterm_fg s:_gui_fg

let b:current_syntax = "vpy"

" vim: set ts=4 sw=4:
