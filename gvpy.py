#!/usr/bin/env python3
"""Template preprocessor — port of gvp.pl to Python.

Reads .vpy/.gvpy templates with embedded Python (after `<comment>;` lines or
inside backticks) and emits target-language source.
"""

import argparse
import ast
import os
import re
import subprocess
import sys

prog = os.path.basename(sys.argv[0])

# globals (mutable across parse_file / include / pinclude)
comment = "//"
PY_ESC = "//;"
PY_ESC2 = None
rawpython = False
mname_arg = None
libdirs = ["./"]
incdirs = ["./"]
defparams = {}
exec_py = ""
current_emit_indent = 0  # auto-tracked indent for emit() lines (Python is whitespace-sensitive)
jinja2_mode = False


PRELUDE = r'''
import sys as _sys

def parameter(*, name="NAME", val=None):
    if name in parameters:
        _sys.stdout.write("%s parameter %s => %s (command line)\n" % (comment, name, parameters[name]))
        return parameters[name]
    if val is not None:
        _sys.stdout.write("%s parameter %s => %s (default value)\n" % (comment, name, val))
        return val
    _sys.stdout.write("%s parameter %s => UNDEFINED\n" % (comment, name))
    return None

_mname = "FIXME"
def mname():
    return _mname

def pp(num, fmt="%02d"):
    return fmt % num

def emit(*args):
    if args:
        _sys.stdout.write(str(args[0]))

class _Inst(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

self = {}

# Top-level function form. Perl's $self->generate(...) auto-self idiom is dropped.
def generate(tname, iname, **kwargs):
    if tname not in self:
        self[tname] = {}
    inst = _Inst(tname=tname, iname=iname, params=dict(kwargs))
    self[tname][iname] = inst
    return inst

def generate_base(*a, **kw):
    return generate(*a, **kw)

def instantiate(inst):
    emit(inst["tname"] + " /*PARAMS: ")
    for k, v in inst["params"].items():
        emit(str(k) + "=>")
        emit(v)
        emit(" ")
    emit(" */ " + inst["iname"])

def synonym(*a, **kw):
    pass
'''


def usage():
    sys.stderr.write(
        f"usage: {prog} [-h] [--libdirs dir] [--incdirs dir] [--defparam param=val] file(s)\n"
        f"    -h, --help        : This message\n"
        f"    --rawpython       : Output generated python source for debugging, rather than executing\n"
        f"    --pdebug          : Alias for --rawpython\n"
        f"    --mname  name     : Set top module name\n"
        f"    --libdirs d1,d2,. : Add dirs to the lib path (sys.path)\n"
        f'    --incdirs d1,d2,. : Add dirs to the include search path (used by {comment}; include("filename"))\n'
        f"    --defparam p=v    : Set parameter 'p' to value 'v'\n"
        f'    --comment str     : Set the comment start of output language to "str" (default "//").\n'
        f'                        Note that this also adds the gvp escape to "str"; (default "//;")\n'
        f"    -j2, --jinja2     : Parse templates with Jinja2 delimiters: '{{% stmt %}}',\n"
        f"                        '{{{{ expr }}}}', '{{# comment #}}' (replaces //; and backticks)\n"
    )


def _format_python(src):
    """Pipe `src` through `python3 -m black -`. Best-effort: on any failure
    (black not installed, format error, subprocess timeout) emit a stderr
    warning and return the source unchanged."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "black", "-q", "--line-length", "140", "-"],
            input=src,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            return r.stdout
        sys.stderr.write(f"{prog}: black exited {r.returncode}; emitting raw output\n")
        if r.stderr:
            sys.stderr.write(r.stderr)
        return src
    except FileNotFoundError:
        sys.stderr.write(f"{prog}: black not installed (pip install black); emitting raw output\n")
        return src
    except (OSError, subprocess.SubprocessError) as e:
        sys.stderr.write(f"{prog}: black failed ({e}); emitting raw output\n")
        return src


def init_py():
    global exec_py
    exec_py += "import sys\n"
    for d in libdirs:
        exec_py += f"sys.path.insert(0, {d!r})\n"
    exec_py += "parameters = {\n"
    for k, v in defparams.items():
        try:
            parsed = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            parsed = v
        exec_py += f"    {k!r}: {parsed!r},\n"
    exec_py += "}\n"
    exec_py += f"comment = {comment!r}\n"
    exec_py += PRELUDE


def _strip_basename(fname):
    base = os.path.basename(fname)
    for ext in (".vpy", ".gvpy", ".vp", ".gvp"):
        if base.endswith(ext):
            return base[: -len(ext)]
    return base


def _opens_block(s):
    """True if a Python source line opens a new indented block (ends with `:`,
    after stripping trailing `#`-comments while honouring `'`/`"` quotes)."""
    in_s = False
    in_d = False
    cut = len(s)
    for i, ch in enumerate(s):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            cut = i
            break
    return s[:cut].rstrip().endswith(":")


def parse_file(fname, incl=False):
    global exec_py, current_emit_indent

    if fname is not None:
        try:
            fh = open(fname, "r")
        except OSError:
            sys.stderr.write(f"ERROR: Could not open {fname} for reading\n")
            sys.exit(1)
        opened = True
    else:
        fname = "STDIN"
        fh = sys.stdin
        opened = False

    name = mname_arg if mname_arg else _strip_basename(fname)
    if not incl:
        exec_py += f'_mname = "{name}"\n'
        current_emit_indent = 0

    try:
        if jinja2_mode:
            _parse_jinja2(fh.read(), fname)
        else:
            _parse_genesis(fh, fname)
    finally:
        if opened:
            fh.close()


def _parse_genesis(fh, fname):
    global exec_py, current_emit_indent

    py_esc_re = re.compile(r"^\s*" + re.escape(PY_ESC))
    py_esc2_re = re.compile(r"^\s*" + re.escape(PY_ESC2)) if PY_ESC2 else None
    py_esc_strip_re = re.compile(r"^(\s*)" + re.escape(PY_ESC))
    py_esc2_strip_re = re.compile(r"^(\s*)" + re.escape(PY_ESC2)) if PY_ESC2 else None
    pinclude_re = re.compile(r"""^\s*pinclude\s*\(\s*(['"])([^'"]+)\1\s*\)""")
    include_re = re.compile(r"""^\s*include\s*\(\s*(['"])([^'"]+)\1\s*\)""")
    verilog_dir_re = re.compile(r"^(\s*\/?\/?)(\s*`)(timescale|default_nettype|include|ifdef|if|ifndef|else|endif)")

    ln = 0
    for line in fh:
        orig_line = line
        ln += 1

        if py_esc_re.match(line) or (py_esc2_re and py_esc2_re.match(line)):
            line = py_esc_strip_re.sub(r"\1", line, count=1)
            if py_esc2_strip_re:
                line = py_esc2_strip_re.sub(r"\1", line, count=1)

            m = pinclude_re.match(line)
            if m:
                pinclude_file(m.group(2))
                continue
            m = include_re.match(line)
            if m:
                include_file(m.group(2))
                continue

            m_ws = re.match(r"^(\s*)", line)
            leading_ws = len(m_ws.group(1)) if m_ws else 0
            current_emit_indent = leading_ws + (4 if _opens_block(line) else 0)
            exec_py += line
        else:
            line = line.rstrip("\r\n")
            out = "emit('"
            expr_mode = False

            m = verilog_dir_re.match(line)
            if m:
                out += m.group(1) + m.group(2) + m.group(3) + " "
                line = line[m.end():]

            i = 0
            while i < len(line):
                char = line[i]
                next_char = line[i + 1] if i + 1 < len(line) else ""
                if char + next_char == "\\`":
                    out += next_char
                    i += 2
                    continue
                if char == "`":
                    out += "); emit('" if expr_mode else "'); emit("
                    expr_mode = not expr_mode
                else:
                    if not expr_mode and char in ("'", "\\"):
                        char = "\\" + char
                    out += char
                i += 1

            if expr_mode:
                sys.stderr.write(f"ERROR:: ({fname}, {ln}) Missing closing backtick:\n\t{orig_line}")
                sys.exit(1)

            out += "')"
            exec_py += " " * current_emit_indent + out + "; emit('\\n')\n"


# ---------------------------------------------------------------------------
# Jinja2-flavour scanner — port of genesispy-port _parse_vpy_jinja2.
# ---------------------------------------------------------------------------

_J2_END_KEYWORDS = frozenset({"endfor", "endif", "endwhile"})

_j2_pinclude_re = re.compile(r"""^\s*pinclude\s*\(\s*(['"])([^'"]+)\1\s*\)\s*$""")
_j2_include_re = re.compile(r"""^\s*include\s*\(\s*(['"])([^'"]+)\1\s*\)\s*$""")


def _die(msg):
    sys.stderr.write(f"ERROR:: {msg}\n")
    sys.exit(1)


def _scan_python_close(source, start, close_a, close_b, path, lineno):
    """Scan past a Python expression / statement to the close delimiter.

    Returns the index of the first character of the close delimiter
    (`}}` or `%}`, possibly preceded by `-`). String literals and bracket
    nesting (`( [ {`) are honoured so braces inside the embedded Python
    don't false-close. Calls _die on EOF.
    """
    i = start
    n = len(source)
    depth = 0
    in_str = None  # one of '"', "'", "'''", '"""'
    while i < n:
        ch = source[i]
        if in_str is not None:
            if len(in_str) == 3:
                if source.startswith(in_str, i):
                    i += 3
                    in_str = None
                    continue
            else:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                    i += 1
                    continue
            i += 1
            continue
        if ch in ('"', "'"):
            if source.startswith(ch * 3, i):
                in_str = ch * 3
                i += 3
                continue
            in_str = ch
            i += 1
            continue
        if depth == 0:
            if ch == "-" and (
                source.startswith(close_a, i + 1)
                or (close_b != close_a and source.startswith(close_b, i + 1))
            ):
                return i
            if source.startswith(close_a, i):
                return i
            if close_b != close_a and source.startswith(close_b, i):
                return i
        if ch in "([{":
            depth += 1
            i += 1
            continue
        if ch in ")]}":
            depth -= 1
            i += 1
            continue
        i += 1
    _die(f"{path}:{lineno}: unterminated {{{close_a[0]} ... {close_a}}}")


def _emit_chain(pieces, indent_spaces):
    """Build a gvpy-style emit chain Python source line.

    pieces: list of ("text", str) / ("expr", str) tuples.
    indent_spaces: leading whitespace count (raw spaces).

    Returns one Python line ending in `; emit('\\n')\n` -- ready to append
    to exec_py. A blank piece list still emits a newline.
    """
    pad = " " * indent_spaces
    parts = []
    for kind, seg in pieces:
        if kind == "text":
            if not seg:
                continue
            esc = seg.replace("\\", "\\\\").replace("'", "\\'")
            parts.append(f"emit('{esc}')")
        else:
            # Wrap expression in parens so embedded newlines are legal.
            parts.append(f"emit(({seg}))")
    if not parts:
        return f"{pad}emit(''); emit('\\n')\n"
    return f"{pad}{'; '.join(parts)}; emit('\\n')\n"


def _parse_jinja2(source, path):
    global exec_py, current_emit_indent

    last_py_indent = 0
    last_was_opener = False
    block_stack = []  # list of py_indent levels for blocks closeable by bare {% endX %}

    n = len(source)
    i = 0

    pieces = []
    line_pieces_lineno = None
    current_line = 1
    line_start = 0
    text_buf = []

    def at_line_start():
        return source[line_start:i].strip(" \t") == ""

    def push_text(s):
        nonlocal line_pieces_lineno
        if not s:
            return
        text_buf.append(s)
        if line_pieces_lineno is None:
            line_pieces_lineno = current_line

    def flush_text_to_pieces():
        if text_buf:
            pieces.append(("text", "".join(text_buf)))
            text_buf.clear()

    def flush_logical_line():
        nonlocal pieces, line_pieces_lineno
        global exec_py
        exec_py += _emit_chain(pieces, current_emit_indent)
        pieces = []
        line_pieces_lineno = None

    while i < n:
        ch = source[i]

        # Newline at top level → end of logical line.
        if ch == "\n":
            flush_text_to_pieces()
            flush_logical_line()
            i += 1
            current_line += 1
            line_start = i
            continue

        # `\{{`: literal `{{` in text.
        if ch == "\\" and source.startswith("\\{{", i):
            push_text("{{")
            i += 3
            continue

        # `{%` or `{%-` → directive.
        if source.startswith("{%", i):
            if not at_line_start():
                _die(f"{path}:{current_line}: '{{%' must start the line "
                     "(no plain Verilog before the directive)")
            text_buf.clear()
            if pieces:
                _die(f"{path}:{current_line}: directive '{{%' cannot share "
                     "a logical line with prior text")
            opener_line = current_line
            i += 2
            if i < n and source[i] == "-":
                i += 1
            close = _scan_python_close(source, i, "%}", "%}", path, opener_line)
            inner = source[i:close]
            i = close
            if source.startswith("-%}", i):
                i += 3
            else:
                i += 2
            if inner.startswith(" "):
                inner = inner[1:]
            if inner.endswith(" "):
                inner = inner[:-1]
            consumed_newlines = source.count("\n", line_start, i)
            current_line = opener_line + consumed_newlines
            # Closer's physical line tail must be whitespace-only.
            j = i
            while j < n and source[j] != "\n":
                if source[j] not in " \t":
                    _die(f"{path}:{current_line}: '%}}' must end the line "
                         "(no plain Verilog after the directive)")
                j += 1
            if j < n and source[j] == "\n":
                i = j + 1
                current_line += 1
                line_start = i
            else:
                i = j

            # include() / pinclude() dispatch.
            stripped_inner = inner.strip()
            m = _j2_pinclude_re.match(inner)
            if m:
                pinclude_file(m.group(2))
                continue
            m = _j2_include_re.match(inner)
            if m:
                include_file(m.group(2))
                continue

            # Bare end-keyword: pops block_stack.
            if stripped_inner in _J2_END_KEYWORDS:
                if not block_stack:
                    _die(f"{path}:{opener_line}: '{{% {stripped_inner} %}}' "
                         "without matching opener")
                popped = block_stack.pop()
                exec_py += f'{"    " * popped}# {stripped_inner}\n'
                last_py_indent = popped
                last_was_opener = False
                current_emit_indent = last_py_indent * 4
                continue

            # Indent / opener handling on the joined inner content.
            inner_lines = inner.split("\n")
            first_line = inner_lines[0]
            leading_ws = first_line[: len(first_line) - len(first_line.lstrip(" \t"))]
            if "\t" in leading_ws:
                _die(f"{path}:{opener_line}: tab character in {{% %}} indent; "
                     "use spaces (indent unit is 4 spaces)")
            n_spaces = len(first_line) - len(first_line.lstrip(" "))
            if n_spaces % 4 != 0:
                _die(f"{path}:{opener_line}: misaligned {{% %}} indent "
                     f"({n_spaces} spaces); expected multiple of 4")
            py_indent = n_spaces // 4
            body_first = first_line[n_spaces:]
            indent_str = "    " * py_indent
            if body_first == "" and len(inner_lines) == 1:
                # Bare `{% %}`: blank, indent state unchanged.
                exec_py += "\n"
            else:
                exec_py += f"{indent_str}{body_first}\n"
                for extra in inner_lines[1:]:
                    exec_py += f"{extra}\n"
                last_nonblank = ""
                for ln in reversed(inner_lines):
                    if ln.strip():
                        last_nonblank = ln
                        break
                last_was_opener = _opens_block(last_nonblank.lstrip(" \t"))
                last_py_indent = py_indent
                current_emit_indent = (last_py_indent + (1 if last_was_opener else 0)) * 4
                if last_was_opener and (
                    not block_stack or py_indent > block_stack[-1]
                ):
                    block_stack.append(py_indent)
            continue

        # `{{` or `{{-` → expression.
        if source.startswith("{{", i):
            opener_line = current_line
            flush_text_to_pieces()
            i += 2
            if i < n and source[i] == "-":
                i += 1
            close = _scan_python_close(source, i, "}}", "}}", path, opener_line)
            expr = source[i:close]
            i = close
            if source.startswith("-}}", i):
                i += 3
            else:
                i += 2
            if expr.startswith(" "):
                expr = expr[1:]
            if expr.endswith(" "):
                expr = expr[:-1]
            consumed = expr.count("\n")
            current_line = opener_line + consumed
            if line_pieces_lineno is None:
                line_pieces_lineno = opener_line
            pieces.append(("expr", expr))
            continue

        # `{#` → comment.
        if source.startswith("{#", i):
            opener_line = current_line
            i += 2
            j = source.find("#}", i)
            if j < 0:
                _die(f"{path}:{opener_line}: unterminated {{# ... #}}")
            consumed = source.count("\n", i, j)
            current_line = opener_line + consumed
            i = j + 2
            continue

        # Plain text character.
        push_text(ch)
        i += 1

    # EOF flush.
    flush_text_to_pieces()
    if pieces or line_pieces_lineno is not None:
        flush_logical_line()


def include_file(fn):
    global exec_py

    if current_emit_indent != 0:
        sys.stderr.write(
            f"ERROR:: include({fn!r}) cannot be called with non-zero current "
            f"emit indent ({current_emit_indent}); move the include out of "
            "the surrounding control block\n"
        )
        sys.exit(1)

    if fn.startswith("/"):
        exec_py += f'emit("{comment} begin file: {fn}\\n")\n'
        parse_file(fn, incl=True)
        exec_py += f'emit("{comment} end file: {fn}\\n")\n'
        return

    for d in incdirs:
        ffn = os.path.join(d, fn)
        if os.path.isfile(ffn):
            exec_py += f'emit("{comment} begin file: {ffn}\\n")\n'
            parse_file(ffn, incl=True)
            exec_py += f'emit("{comment} end file: {ffn}\\n")\n'
            return

    sys.stderr.write(f"ERROR:: could not find file {fn} in include path '{':'.join(incdirs)}'\n")
    sys.exit(1)


def pinclude_file(fn):
    global exec_py

    if current_emit_indent != 0:
        sys.stderr.write(
            f"ERROR:: pinclude({fn!r}) cannot be called with non-zero current "
            f"emit indent ({current_emit_indent}); move the pinclude out of "
            "the surrounding control block\n"
        )
        sys.exit(1)

    if fn.startswith("/"):
        exec_py += f'emit("{comment} begin python file: {fn}\\n")\n'
        with open(fn) as f:
            exec_py += f.read()
        exec_py += f'\nemit("{comment} end python file: {fn}\\n")\n'
        return

    for d in incdirs:
        ffn = os.path.join(d, fn)
        if os.path.isfile(ffn):
            exec_py += f'emit("{comment} begin python file: {ffn}\\n")\n'
            with open(ffn) as f:
                exec_py += f.read()
            exec_py += f'\nemit("{comment} end python file: {ffn}\\n")\n'
            return

    sys.stderr.write(f"ERROR:: could not find file {fn} for pinclude in '{':'.join(incdirs)}'\n")
    sys.exit(1)


def main():
    global comment, PY_ESC, PY_ESC2, rawpython, mname_arg, libdirs, incdirs, defparams, jinja2_mode

    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("--libdirs", action="append", default=[])
    parser.add_argument("--incdirs", action="append", default=[])
    parser.add_argument("--defparam", action="append", default=[])
    parser.add_argument("--rawpython", "--pdebug", action="store_true")
    parser.add_argument("--mname")
    parser.add_argument("--comment", default="//")
    parser.add_argument("-j2", "--jinja2", action="store_true")
    parser.add_argument("files", nargs="*")

    try:
        args = parser.parse_args()
    except SystemExit as e:
        usage()
        raise

    if args.help:
        usage()
        sys.exit(0)

    comment = args.comment
    PY_ESC = "//;"
    PY_ESC2 = comment + ";" if comment != "//" else None
    rawpython = args.rawpython
    mname_arg = args.mname
    jinja2_mode = args.jinja2

    libdirs = []
    for entry in (args.libdirs or ["./"]):
        libdirs.extend(entry.split(","))
    incdirs = []
    for entry in (args.incdirs or ["./"]):
        incdirs.extend(entry.split(","))
    defparams = {}
    for kv in args.defparam:
        k, _, v = kv.partition("=")
        defparams[k] = v

    init_py()
    for f in args.files:
        parse_file(f)

    if rawpython:
        sys.stdout.write(_format_python(exec_py))
        return

    try:
        ns = {"__name__": "__gvp__"}
        exec(exec_py, ns)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        base = os.path.basename(args.files[0]) if args.files else "unknown"
        tmpfile = f"/tmp/{base}.{os.getpid()}.py"
        try:
            os.unlink(tmpfile)
        except OSError:
            pass
        try:
            with open(tmpfile, "w") as f:
                f.write(exec_py)
            sys.stderr.write(f"\n{prog}: dumping generated python to {tmpfile}..\n")
            sys.stderr.write(f'{prog}: running "{sys.executable} -W all {tmpfile}" for debug info:\n{"-" * 80}\n')
            subprocess.run([sys.executable, "-W", "all", tmpfile])
            sys.stderr.write(f"{'-' * 80}\n")
        except OSError:
            sys.stderr.write(f"{prog}: error could not write {tmpfile}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
