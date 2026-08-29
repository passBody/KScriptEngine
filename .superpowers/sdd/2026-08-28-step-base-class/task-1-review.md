# Task 1 Review: 步骤基类 `actions/base.py`

## Spec Compliance

✅ Spec compliant

- `actions/__init__.py` (4 lines): verbatim match with the brief (brief lines 26-32 vs file lines 1-3) — `from .base import Step, StepStatus` + `__all__`.
- `actions/base.py`: file-by-file comparison against the brief's Step 1 docstring/smoke block and Step 3 class code is exact except for the 3 adjudicated fixes, each verified minimal and correct (see below). No missing requirements, no unrequested features, no misconstrued requirements found.
- The 3 adjudicated plan-text fixes, verified in code and confirming none introduce a new problem:
  ① base.py:376 — `'{"name":"桩步骤"}'.encode("utf-8")` produces exactly the bytes the un-compilable `b'{"name":"桩步骤"}'` intended; one-line change.
  ② `from __future__ import annotations` removed — module's own annotations (base.py:90-91, 161-162) are quoted strings or imported typing names that are never runtime-evaluated (no `get_type_hints` anywhere), so removal is safe; `f.type` now yields `"number"` (base.py:78-79) as the smoke assertions require. One-line change.
  ③ base.py:294 — `self.outputs.total = self.inputs.a * 2` added to `_ManErrStep.run`, consistent with `_StubStep.run` (base.py:243-245) and the assertion/comment "写 5*2=10" (base.py:304). One-line change.
- Global constraints all satisfied: non-git run-verification via `__main__` asserts (base.py:204-381); format string is UTF-8 JSON → urlsafe base64 with padding stripped (base.py:151-158); io dataclasses are instantiated with no args (base.py:69-70) — defaults are the subclasses' contract, confirmed by the stub (base.py:230-235); instance attrs `self.inputs`/`self.outputs` don't shadow methods `input()`/`output()` (base.py:69-70 vs 108, 121); `QApplication.instance() or QApplication(sys.argv)` first (base.py:217); no directory names touched.
- Deviation disclosures verified: Step 2 red was `ImportError` at `actions/__init__.py:1` rather than the brief's expected `NameError` — same "missing feature" red class, correctly reasoned (base has no `Step` yet, so the failure surfaces at package import); `main.py --check` expectation — verified existing code renders and auto-quits with no text output (main.py:8-14, widgets/main_widget.py:530-536), so exit-code-based verification is the correct adaptation; runpy RuntimeWarning is a pre-existing package-import pattern, not introduced here.
- Only named-risk check performed: `main.py --check` output behavior (above). Result: implementer's claim accurate.

## Strengths

- Faithful transcription of the brief with minimal, surgical fixes; nothing added beyond spec (382 lines is justified: ~170 lines of class code + ~180 lines of required self-test under the project's run-verification convention).
- Smoke coverage is genuinely behavioral and covers every planned edge: slot-type derivation from dataclass annotations (base.py:249-250), full do() flow with variable-tree write-back (base.py:258-265), exception path — ERROR status, log message with step name and exception, re-raise, output not executed (base.py:268-287), manual ERROR preserved through do() (base.py:289-304), all three offset values 1/2/0 (base.py:261, 317, 329), format-string round-trip with padding-free output (base.py:332-338), all four None-return cases (base.py:346-365), and both ValueError categories — bad encodings including empty string and missing fields (base.py:368-379).
- `_decode` (base.py:181-199) is sound: padding math `"=" * (-len(fmt) % 4)` is correct; `binascii.Error`, `json.JSONDecodeError`, and `UnicodeEncodeError` (non-ASCII input) are all ValueError subclasses so the catch at base.py:190 catches every malformed-input path; key-set and per-key type checks (base.py:192-198) close the "structural" holes, and all downstream uses of "in"/"out" are plain equality comparisons, so no crash path exists even for deeply malformed signatures.
- Clear single responsibility and a well-defined interface: sectioned class (slot derivation / factory / GUI / execution / serialization, base.py:72-199), classmethod factory for unconstructed instances, and do()'s input→run→output ordering with correct status bookkeeping (RUNNING at entry, ERROR on any exception with re-raise, FINISHED only if run didn't force ERROR, base.py:126-144). The `offset` unbound-variable risk (run raises before assignment) is dead code because the except path re-raises (base.py:138-141).
- Report is honest and complete: all 3 fixes, the red-run discrepancy, and both concerns (future-annotations risk for Task 2, runpy warning) are disclosed with evidence, and the rulings confirm the fixes were adjudicated.

## Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

None.

#### Minor (Nice to Have)

1. base.py:110-112 — `input()` uses `zip(fields(...), values)`, which silently truncates if `resolve_inputs()` ever returns fewer values than fields, leaving stale defaults on remaining fields. Unreachable through the sanctioned construction paths (create_default builds io from the same signature, base.py:93-94; from_format_string rejects slot-count mismatches, base.py:176-178), so it is purely defensive; the code is per-brief, so this is a plan-design note rather than an implementer defect. A strict length check or explicit ValueError would be more robust.
2. base.py:126-144 — the RUNNING status is never directly observable in the smoke tests (no test hook samples status mid-`run`). Coverage of the status transitions (PENDING→FINISHED, PENDING→ERROR, ERROR preserved) is complete; RUNNING is transient and would need a spy stub to assert. Brief-level coverage gap, not a deviation; a future task's smoke could add it.
3. base.py:201-381 with actions/__init__.py:1 — the runpy RuntimeWarning (`python -m actions.base` executes base.py twice) is inherent to the package-import style the brief mandates and matches the existing `widgets.step_io_widget` pattern; correctly classified by the implementer as pre-existing and non-blocking. Flagging only so the controller can decide whether the plan's later tasks should standardize on lazy imports.

## Assessment

**Task quality:** Approved

**Reasoning:** Both files match the brief verbatim except the three adjudicated fixes, each of which is minimal, correct, and introduces no new problem; the smoke suite exercises every required behavior and edge case, and the two report disclosures (red-run form, `--check` output expectation) were verified accurate against existing code. Remaining items are plan-level polish, not task defects.
