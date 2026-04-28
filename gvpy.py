#!/usr/bin/env python3
"""Template preprocessor — port of gvp.pl to Python.

Reads .vpy/.gvpy templates with embedded Python (after `<comment>;` lines or
inside backticks) and emits target-language source.
"""

import argparse
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
        exec_py += f'    "{k}": {v},\n'
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
    """True if a Python source line opens a new indented block (ends with `:`)."""
    s = re.sub(r"#.*$", "", s).rstrip()
    return s.endswith(":")


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

    py_esc_re = re.compile(r"^\s*" + re.escape(PY_ESC))
    py_esc2_re = re.compile(r"^\s*" + re.escape(PY_ESC2)) if PY_ESC2 else None
    py_esc_strip_re = re.compile(r"^(\s*)" + re.escape(PY_ESC))
    py_esc2_strip_re = re.compile(r"^(\s*)" + re.escape(PY_ESC2)) if PY_ESC2 else None
    pinclude_re = re.compile(r"""^\s*pinclude\s*\(\s*(['"])([^'"]+)\1\s*\)""")
    include_re = re.compile(r"""^\s*include\s*\(\s*(['"])([^'"]+)\1\s*\)""")
    verilog_dir_re = re.compile(r"^(\s*\/?\/?)(\s*`)(timescale|default_nettype|include|ifdef|if|ifndef|else|endif)")

    ln = 0
    try:
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
    finally:
        if opened:
            fh.close()


def include_file(fn):
    global exec_py

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
    global comment, PY_ESC, PY_ESC2, rawpython, mname_arg, libdirs, incdirs, defparams

    parser = argparse.ArgumentParser(prog=prog, add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("--libdirs", action="append", default=[])
    parser.add_argument("--incdirs", action="append", default=[])
    parser.add_argument("--defparam", action="append", default=[])
    parser.add_argument("--rawpython", "--pdebug", action="store_true")
    parser.add_argument("--mname")
    parser.add_argument("--comment", default="//")
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
