#!/usr/bin/env bash
# Smoke-test runner for gvpy.py and gvp.pl.
#
# Each case lives under tests/cases/<NN_name>/ and may contain per-mode files
# named with a ".py" or ".pl" suffix. The runner picks files for the mode it
# is currently running. When two modes share content, the .pl file is a
# symlink to the .py file (and likewise in.vp -> in.vpy where input matches).
#
# Per-mode files (mode = py | pl):
#   in.vpy / in.vp                         -- template input; presence gates the mode
#   flags.<mode>                           -- optional CLI flags prepended before in.<ext>
#   cmd.<mode>                             -- optional full arg list (one per line)
#   expected.out.<mode>                    -- exact stdout match (diff -u)
#   expected_out_contains.<mode>           -- substring stdout match
#   expected_err.<mode>                    -- substring stderr match
#   expected_exit.<mode>                   -- integer exit code (default 0)
#
# Usage: run_tests.sh [py|pl|both]   (default: both)

set -u

mode_arg="${1:-both}"
case "$mode_arg" in
    py|pl|both) ;;
    *) echo "usage: $0 [py|pl|both]" >&2; exit 2 ;;
esac

TESTS_DIR=$(cd "$(dirname "$0")" && pwd)
CASES_DIR="$TESTS_DIR/cases"
GVP_PY=$(realpath "$TESTS_DIR/../gvpy.py")
GVP_PL=$(realpath "$TESTS_DIR/../gvp.pl")

# Startup checks: hard-fail if any required tool is missing.
missing=()
command -v python3 >/dev/null 2>&1 || missing+=("python3")
command -v perl    >/dev/null 2>&1 || missing+=("perl")
[[ -x "$GVP_PY" ]] || missing+=("$GVP_PY (executable)")
[[ -x "$GVP_PL" ]] || missing+=("$GVP_PL (executable)")
if (( ${#missing[@]} )); then
    echo "ERROR: missing prerequisites: ${missing[*]}" >&2
    exit 2
fi

modes=()
case "$mode_arg" in
    py)   modes=(py) ;;
    pl)   modes=(pl) ;;
    both) modes=(py pl) ;;
esac

ext_for() { case "$1" in py) echo "vpy" ;; pl) echo "vp" ;; esac; }

declare -A pass_per fail_per skip_per
for m in "${modes[@]}"; do pass_per[$m]=0; fail_per[$m]=0; skip_per[$m]=0; done

failures=()
skips=()

run_case_mode() {
    local case_dir="$1" mode="$2"
    local name; name=$(basename "$case_dir")
    local ext; ext=$(ext_for "$mode")
    local infile="in.$ext"

    if [[ ! -e "$case_dir/$infile" && ! -f "$case_dir/cmd.$mode" ]]; then
        printf "SKIP  %s [%s]\n" "$name" "$mode"
        skip_per[$mode]=$((skip_per[$mode] + 1))
        skips+=("$name[$mode]")
        return
    fi

    local -a args_arr
    if [[ -f "$case_dir/cmd.$mode" ]]; then
        mapfile -t args_arr < "$case_dir/cmd.$mode"
    elif [[ -f "$case_dir/flags.$mode" ]]; then
        local flags; flags=$(< "$case_dir/flags.$mode")
        local -a flag_arr
        read -ra flag_arr <<< "$flags"
        args_arr=("${flag_arr[@]}" "$infile")
    else
        args_arr=("$infile")
    fi

    local expected_exit=0
    [[ -f "$case_dir/expected_exit.$mode" ]] && expected_exit=$(< "$case_dir/expected_exit.$mode")

    local actual_stdout actual_stderr actual_exit
    actual_stdout=$(mktemp)
    actual_stderr=$(mktemp)
    if [[ "$mode" == "py" ]]; then
        (cd "$case_dir" && python3 "$GVP_PY" "${args_arr[@]}") >"$actual_stdout" 2>"$actual_stderr"
    else
        (cd "$case_dir" && "$GVP_PL" "${args_arr[@]}") >"$actual_stdout" 2>"$actual_stderr"
    fi
    actual_exit=$?

    local case_pass=1
    local -a case_msgs=()

    if [[ "$actual_exit" != "$expected_exit" ]]; then
        case_pass=0
        case_msgs+=("exit: expected $expected_exit, got $actual_exit")
    fi

    if [[ -f "$case_dir/expected.out.$mode" ]]; then
        if ! diff -q "$case_dir/expected.out.$mode" "$actual_stdout" >/dev/null 2>&1; then
            case_pass=0
            case_msgs+=("stdout differs from expected.out.$mode")
        fi
    fi

    if [[ -f "$case_dir/expected_out_contains.$mode" ]]; then
        local pattern; pattern=$(< "$case_dir/expected_out_contains.$mode")
        if ! grep -qF -- "$pattern" "$actual_stdout"; then
            case_pass=0
            case_msgs+=("stdout missing substring: $pattern")
        fi
    fi

    if [[ -f "$case_dir/expected_err.$mode" ]]; then
        local pattern; pattern=$(< "$case_dir/expected_err.$mode")
        if ! grep -qF -- "$pattern" "$actual_stderr"; then
            case_pass=0
            case_msgs+=("stderr missing substring: $pattern")
        fi
    fi

    if [[ $case_pass -eq 1 ]]; then
        pass_per[$mode]=$((pass_per[$mode] + 1))
        printf "PASS  %s [%s]\n" "$name" "$mode"
    else
        fail_per[$mode]=$((fail_per[$mode] + 1))
        failures+=("$name[$mode]")
        printf "FAIL  %s [%s]\n" "$name" "$mode"
        local m
        for m in "${case_msgs[@]}"; do
            printf "      %s\n" "$m"
        done
        if [[ -f "$case_dir/expected.out.$mode" ]]; then
            diff -u "$case_dir/expected.out.$mode" "$actual_stdout" 2>/dev/null | head -20 | sed 's/^/      /'
        fi
        if [[ -s "$actual_stderr" ]] && [[ ! -f "$case_dir/expected_err.$mode" ]]; then
            printf "      stderr was:\n"
            sed 's/^/      | /' "$actual_stderr" | head -10
        fi
    fi

    rm -f "$actual_stdout" "$actual_stderr"
}

for case_dir in "$CASES_DIR"/*/; do
    for m in "${modes[@]}"; do
        run_case_mode "$case_dir" "$m"
    done
done

echo
total_pass=0; total_fail=0; total_skip=0
for m in "${modes[@]}"; do
    printf "[%s] passed: %d, failed: %d, skipped: %d\n" \
        "$m" "${pass_per[$m]}" "${fail_per[$m]}" "${skip_per[$m]}"
    total_pass=$((total_pass + pass_per[$m]))
    total_fail=$((total_fail + fail_per[$m]))
    total_skip=$((total_skip + skip_per[$m]))
done
printf "Total runs: %d, passed: %d, failed: %d, skipped: %d\n" \
    "$((total_pass + total_fail + total_skip))" "$total_pass" "$total_fail" "$total_skip"

if (( total_fail != 0 )); then
    echo "Failed: ${failures[*]}"
    exit 1
fi
