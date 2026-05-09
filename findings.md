# Code review — gvpy.py and documentation

Bugs only. No nits.

## 1. `include()` / `pinclude()` from inside a control block breaks indentation — FIXED (Option C)

**Affects both genesis and jinja2 modes. Pre-existing in genesis, inherited in jinja2.**

**Resolution**: `include_file` and `pinclude_file` now refuse the call when
`current_emit_indent != 0`, with a clear `ERROR:: include(...) cannot be
called with non-zero current emit indent (N); move the include out of the
surrounding control block` message. New tests: 47–49. README "Includes"
section documents the restriction.

`include_file` and `pinclude_file` append unconditionally at column 0:

```python
# gvpy.py:284–303 (include_file) and 305–325 (pinclude_file)
exec_py += f'emit("{comment} begin file: {ffn}\\n")\n'
parse_file(ffn, incl=True)
exec_py += f'emit("{comment} end file: {ffn}\\n")\n'
```

They ignore `current_emit_indent`. When the parent is inside a `for` /
`if` / `while` body, the begin marker, the included content, and the
end marker all land at column 0, producing an `IndentationError` at
`exec()` time.

Reproducer (jinja2 mode):

```vpy
{% for i in range(2): %}
hello
{% include("inc.vpy") %}
{% endfor %}
```

`inc.vpy`:

```vpy
inner
```

Error:

```
Error: unexpected indent (<string>, line 64)
  File "/tmp/parent.vpy.<pid>.py", line 64
    emit('inner'); emit('\n')
IndentationError: unexpected indent
```

Genesis mode reproduces identically with `//;include("inc.vpy")` inside
a `//;for` block. Same story for `pinclude`.

Perl mode (`gvp.pl`) is unaffected because Perl is whitespace-insensitive.

**Fix sketch**: prefix the begin/end markers with `" " * current_emit_indent`,
and ensure the included file's `_parse_*` continues to write at the
parent's indent (it does — `current_emit_indent` is module-global).

## 2. README lies about `--defparam K=V` — FIXED (Option C)

**Resolution**: `init_py` now runs each `V` through `ast.literal_eval`,
keeping the parsed value if it's a Python literal (int / float / bool /
None / str / list / tuple / dict) and falling back to the raw string
when literal_eval rejects it. This eliminates the `--defparam W=hello`
NameError without forcing every template to wrap values in `int()`.

README's `parameter()` description rewritten to describe the actual
contract, with a table of representative inputs and resulting types.

New tests: 50 (bareword → str), 51 (`True` → bool), 52 (`'"quoted"'` →
str), 53 (`2**8` → str via fallback). Existing test 14 (`--defparam W=8`
→ int 8) still passes — Option C preserves the most-relied-on case.



README "Built-in helpers › `parameter()`":

> 1. `--defparam NAME=V` from the command line → returns `V` (string)

That's wrong. `init_py` writes the value verbatim into a Python dict
literal:

```python
# gvpy.py:132–135
exec_py += "parameters = {\n"
for k, v in defparams.items():
    exec_py += f'    "{k}": {v},\n'
```

So `V` is **evaluated as Python at exec time**, not stored as a string.
Consequences:

- `--defparam W=8` → `parameters["W"]` is `int 8`, not `"8"`.
- `--defparam W=hello` → `NameError: name 'hello' is not defined` at
  module init (because `hello` is parsed as a bareword identifier).
- To pass a literal string the user must write `--defparam W='"hello"'`
  (shell-quote the Python quotes).

The CLI table row also misleads:

> `--defparam K=V` | Set template parameter (repeatable) |

**Fix options**:

- (docs) call out the eval-as-Python behaviour explicitly in both the
  CLI table and the `parameter()` description, with the `'"hello"'`
  shell-quoting example.
- (code) `repr(v)` the value when emitting the dict literal so values
  are always strings. This would change semantics — existing templates
  that rely on numeric `--defparam W=8` returning an int would break.
  The docs route is safer.

---

## What I checked and did not find bugs in

- Escape correctness in `_emit_chain` (`\` and `'` ordering, mixed cases).
- `_scan_python_close` bracket/string nesting: f-strings, triple-quoted
  strings, dict literals inside `{{ }}`, embedded escapes.
- Bare end-keyword stack discipline (`endfor` / `endif` / `endwhile`),
  including nested loops and `else:`/`elif`/`except`/`finally` not
  pushing extra entries.
- Multi-line `{% %}` and `{{ }}` line tracking.
- `\{{` literal escape vs. `{{` expression open.
- Dash whitespace modifiers (`{%-`, `-%}`, `{{-`, `-}}`) accepted as no-op.
- EOF flush of partial logical lines.
- `at_line_start` detection vs. directive-must-start-line / -end-line errors.
- Tab-in-indent and non-multiple-of-4 indent diagnostics.
- Comment block `{# … #}` newline counting.
- Verilog backtick directives (`` `timescale ``, `` `ifdef ``, …) staying
  out of expression mode in genesis.
