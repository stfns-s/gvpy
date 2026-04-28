# gvpy

Minimalist port of Genesis2 hierarchical templating generator
(see: https://github.com/StanfordVLSI/Genesis2)

Two implementations live side by side:

| Script   | Embedded language | Use                                      |
|----------|-------------------|------------------------------------------|
| `gvp.pl` | Perl              | Original implementation; kept for parity |
| `gvpy.py`| Python            | Pythonic version                         |

Both produce identical output on language-neutral inputs (literal pass-through, `include`, Verilog `` ` ``-directives).

## Quick start

```bash
gvpy.py test.vpy
gvpy.py --defparam WIDTH=32 --mname my_module test.vpy

gvp.pl test.vp
gvp.pl --defparam WIDTH=32 --mname my_module test.vp
```

## CLI

| Flag | Purpose |
|------|---------|
| `-h`, `--help` | Usage message |
| `--mname NAME` | Top module name (default: stripped basename of input file) |
| `--defparam K=V` | Set template parameter (repeatable) |
| `--incdirs d1,d2,...` | Search path for `include`/`pinclude` (repeatable, comma-split) |
| `--libdirs d1,d2,...` | Prepended to `sys.path` before executing (repeatable, comma-split) |
| `--comment STR` | Output-language comment prefix (default `//`); also enables `<STR>;` as an alternate escape |
| `--rawpython` / `--pdebug` | Print generated Python source instead of executing (formatted with `black -l 140` if installed) |

Positional args are template files; multiple inputs are concatenated in order.

## Template syntax (gvpy.py)

> **Perl variant (`gvp.pl`):** the template syntax is otherwise equivalent — the only difference is that Perl blocks have no indent guards. Use a plain `}` to close a `//;` block instead of a `//;# end` sentinel, and rely on Perl's brace-delimited control flow as usual.

### Literal text

Most lines pass through verbatim:

```
module foo;
  wire x;
endmodule
```

### Backtick expressions — `` `expr` ``

Inline Python expressions evaluate and emit their `str()`:

```
assign x = 8'h`pp(0xab, "%02x")`;   →  assign x = 8'hab;
```

```
//;WIDTH = 16
wire [`WIDTH-1`:0] bus;             →  wire [15:0] bus;
```

Use `` \` `` for a literal backtick.

### `//;` Python control lines

Lines beginning with `//;` (or `<comment>;` if `--comment` is set) are Python source. Write the code **immediately after** `//;` — Python is whitespace-sensitive:

```
//;for i in range(4):
  wire w_`i`;
//;# end for
```

→
```
  wire w_0;
  wire w_1;
  wire w_2;
  wire w_3;
```

**Auto-indent**: when a `//;` line ends with `:`, subsequent literal lines are emitted inside that block. Use a non-`:` `//;` line at the outer indent (e.g. `//;# end`) to close the block. Nested example:

```
//;for i in range(2):
//;    if i % 2 == 0:
  even `i`;
//;    else:
  odd `i`;
//;    # end if
//;# end for
```

Inside `.vpy` files:
- Plain lines are emitted as Verilog text.
- Lines beginning with `//;` are Python (formerly Perl). Indent with leading
  spaces inside `//;` to mark Python block bodies; close blocks with a
  sentinel comment such as `//; # end for` / `//; # end if` (or the no-space
  forms `//; # endfor` / `//; # endif` — either style works, the text is just
  a Python comment; pick one and stay consistent within a file).
- Backtick-delimited regions interpolate Python expressions, e.g.
  ``wire [`WIDTH-1`:0] x;``.

### Verilog `` ` `` directives

Lines starting with `` `timescale ``, `` `ifdef ``, `` `ifndef ``, `` `else ``, `` `endif ``, `` `if ``, `` `default_nettype ``, or `` `include `` (optionally inside a `//` comment) pass through — the leading `` ` `` does not toggle expression mode.

### Includes

```
//;include("submodule.vpy")   -- preprocessed by gvp; searched in --incdirs
//;pinclude("helpers.py")    -- raw Python, pasted verbatim into the program
```

## Built-in helpers

These functions are injected into the generated program's global scope, so they are usable inside `//;` Python blocks and inside `` `...` `` backtick expressions without any import.

### `parameter(*, name="NAME", val=None)`

Resolve a template parameter. Lookup order:

1. `--defparam NAME=V` from the command line → returns `V` (string), prints `// parameter NAME => V (command line)`.
2. The `val` keyword argument → returns `val`, prints `// parameter NAME => val (default value)`.
3. Otherwise → returns `None`, prints `// parameter NAME => UNDEFINED`.

The banner line uses the current `--comment` prefix. Both arguments are keyword-only.

```
//;WIDTH = parameter(name="WIDTH", val=8)
wire [`WIDTH-1`:0] bus;
```

### `mname()`

Returns the current top module name as a string. Defaults to the input filename with its extension stripped; overridden by `--mname NAME`.

```
module `mname()` (...);
```

### `pp(num, fmt="%02d")`

Printf-style formatter — `return fmt % num`. Convenient inside backticks for zero-padded indices.

```
stage_`pp(i)`         →  stage_07
addr_`pp(i, "%04x")`  →  addr_000a
```

### `emit(*args)`

Write `str(args[0])` directly to stdout — no trailing newline, no `%` interpretation (unlike Perl's `printf`-style `emit` in `gvp.pl`). Extra arguments are ignored. Useful inside `//;` blocks where backticks aren't available.

```
//;for i in range(4):
//;    emit(f"  wire w_{i};\n")
//;# end
```

### `generate(tname, iname, **kwargs)`

Register an instance of template `tname` under the name `iname`, recording `kwargs` as its parameters. Stored at `self[tname][iname]`; returns an `_Inst` (a `dict` subclass with attribute access).

The returned object exposes:

- `.tname` — template name
- `.iname` — instance name
- `.params` — dict of the `kwargs` passed in

```
//;u0 = generate("adder", "u_add0", WIDTH=8)
//;u0.params["WIDTH"]   # → 8
//;u0.tname             # → "adder"
```

`generate_base(...)` is an alias kept for parity with the Perl original.

### `instantiate(inst)`

Emit a one-line instantiation banner for an `_Inst` returned by `generate`:

```
adder /*PARAMS: WIDTH=>8  */ u_add0
```

No newline is appended — follow it with literal text or another `emit` if you need a port list.

### `synonym(*a, **kw)`

No-op stub kept for compatibility with Genesis2 templates that call it. Accepts any arguments, returns `None`.

### `self`

The instance registry populated by `generate`: `self[tname][iname] -> _Inst`. Iterate over it to walk all registered instances.

### `parameters`

Dict of `--defparam` values from the command line (raw strings, no type coercion). `parameter()` reads from this; you can also access it directly.

### Includes

- `include("file.vpy")` — preprocessed by gvpy; searched along `--incdirs`. Equivalent to inlining the file at this point.
- `pinclude("file.py")` — raw Python, pasted verbatim into the generated program (no template processing).

## Example

`shifter.vpy`:

```
//;DEPTH = parameter(name="DEPTH", val=4)
module shifter (input clk, input [7:0] din, output [7:0] dout);
//;for i in range(DEPTH):
    reg [7:0] stage_`pp(i)`;
//;# end
endmodule
```

```bash
$ python3 gvpy.py --defparam DEPTH=2 shifter.vpy
// parameter DEPTH => 2 (command line)
module shifter (input clk, input [7:0] din, output [7:0] dout);
    reg [7:0] stage_00;
    reg [7:0] stage_01;
endmodule
```

An example template covering most features lives in [`example.vpy`](example.vpy).

## Debugging

When the embedded Python raises, gvpy.py writes the full generated source to `/tmp/<base>.<pid>.py` and re-runs it under `python -W all` so the traceback line numbers point at the generated source. Use `--rawpython` to print the generated Python without executing — pipes through `black -l 140` if installed, otherwise emits the source as built (with a stderr warning).

## Tests

```bash
bash tests/run_tests.sh
```

Cases live in `tests/cases/<NN_name>/`. Each case may contain:

| File                    | Meaning                                                  |
|-------------------------|----------------------------------------------------------|
| `in.vpy`                 | Template input (default positional arg)                  |
| `flags`                 | Whitespace-split CLI flags prepended before `in.vpy`      |
| `cmd`                   | One arg per line; replaces `flags` + `in.vpy` entirely    |
| `expected.out`          | Exact stdout match (`diff -u`)                           |
| `expected_out_contains` | Substring match against stdout                           |
| `expected_err`          | Substring match against stderr                           |
| `expected_exit`         | Expected exit code (default `0`)                         |

Add a case by creating a new numbered subdirectory.

## Editor support

### Vim

Syntax + ftdetect files for `.vpy` / `.gvpy` / `.vp` / `.gvp` live in [`vim/`](vim/). See [`vim/README.md`](vim/README.md) for installation and configuration details.

## Differences between gvpy.py and gvp.pl

| Area | gvp.pl | gvpy.py |
|------|--------|--------|
| Embedded language | Perl (`eval`) | Python (`exec`) |
| Indentation | Insignificant | Significant — auto-indent tracking applies to literal lines (see above) |
| `--rawpython` flag | n/a; uses `--rawperl` piped through `perltidy` | pipes through `python -m black -l 140` if available, else raw with stderr warning |
| `generate` API | `bless`ed hashref | `_Inst` (dict subclass) with attribute access |
| `emit` | `printf @_` (interprets `%`) | `sys.stdout.write(str(args[0]))` (no `%` interpretation) |
| Helper docstrings | n/a | identical signatures |
