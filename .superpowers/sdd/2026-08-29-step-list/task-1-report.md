# Task 1 Report: `StepList` — `model/step_list.py`

**Status:** DONE

## What I implemented

Created `C:\Users\feelnn\Desktop\项目\KScript\model\step_list.py`:

1. **Step 1 (RED):** Wrote the file containing only the module header docstring + the smoke block, transcribed verbatim from the brief's Step 1 code block (header docstring lines 13–36 + full smoke block lines 37–155). No class yet.
2. **Step 2:** Ran `python -m model.step_list` → RED observed (see TDD evidence below).
3. **Step 3:** Added the `StepList` class verbatim from the brief's Step 3 code block, inserted between the module header and the smoke block:
   - `__init__` / `add` / `insert` / `remove` / `move` (writes)
   - `do_methods` / `to_format_strings` / `from_format_strings` (classmethod, strict decode with 「第 N 条」) / `create_empty` (classmethod) (exports)
   - `steps` property (copy), `__len__` / `__iter__` / `__getitem__` (reads/dunder)
   - Module-level: `from typing import Callable, Iterator, List, TYPE_CHECKING`, `from actions.base import Step`, `if TYPE_CHECKING: from model.step_manager import StepManager`, `__all__ = ["StepList"]` — all exactly as the brief specifies.
4. **Step 4:** GREEN (`StepList smoke OK`, EXIT=0).
5. **Step 5:** Dependency-chain regression green (`model.step_manager` and `actions.base` both OK, EXIT=0).

## TDD evidence

### RED

Command: `python -m model.step_list; echo "EXIT=$?"` (from repo root)

Output (abridged):
```
Traceback (most recent call last):
  ...
  File "...\model\step_list.py", line 33, in <module>
    from model.step_list import StepList
ImportError: cannot import name 'StepList' from 'model.step_list' (...\model\step_list.py). Did you mean: 'step_list'?
EXIT=1
```

Why expected: the class is not implemented yet, so the smoke's `from model.step_list import StepList` cannot resolve the name. EXIT=1, and the failure reason is precisely "class not implemented" — not an indentation/syntax error in the smoke, so no smoke fix was needed.

Note: the brief's expected RED text is `NameError: name 'StepList' is not defined`, but the actual observed error is `ImportError: cannot import name 'StepList'`. This is inherent to how `python -m` executes the file (runpy imports the module under its real name `model.step_list` first, populating `sys.modules`; the smoke block's `from model.step_list import StepList` then fails at attribute lookup). A `NameError` would only occur if the smoke block referenced `StepList` without importing it. The RED is semantically the same failure (class missing) and the EXIT code is 1 as expected, so no corrective action was needed.

### GREEN

Command: `python -m model.step_list; echo "EXIT=$?"`

Output:
```
StepList smoke OK
EXIT=0
```

### Step 5 regression (dependency chain)

Commands and outputs:
```
$ python -m model.step_manager
StepManager smoke OK
EXIT=0

$ python -m actions.base
<frozen runpy>:130: RuntimeWarning: 'actions.base' found in sys.modules after import of package 'actions', but prior to execution of 'actions.base'; this may result in unpredictable behaviour
Step smoke OK
EXIT=0
```
The `<frozen runpy>` RuntimeWarning on `actions.base` is the known-and-harmless warning from the global constraints; both smokes print their OK markers with EXIT=0.

## Files changed

- Created: `C:\Users\feelnn\Desktop\项目\KScript\model\step_list.py` (the only file touched).

## Self-review findings

- **Completeness (verbatim):** Programmatically verified the written file against the brief's code blocks with a diff script:
  - The full Step 3 class block is embedded in the file verbatim and appears exactly once (`class block verbatim: True`).
  - The Step 1 smoke block (including the header docstring) matches the brief's block 0 exactly, with the only differences being the 3 blank lines at the class-insertion seams (1 blank line after the docstring, 2 blank lines before `if __name__`) — these follow the codebase's own layout in `model/variable_tree.py` (blank line after docstring; 2 blank lines before the smoke block).
- **Discipline (YAGNI):** No extra methods, no extra imports, no modifications to any other file. Code follows existing `model/variable_tree.py` patterns (module docstring with usage example, section banner comments, `@classmethod` factories, `@property` returning a copy, dunder methods, smoke under `if __name__ == "__main__"`).
- **Constraints honored:** no git commands run; smoke run as `python -m model.step_list` with `echo "EXIT=$?"` (no tail/head piping); template bytes written via `GOOD.encode("utf-8")` (no Chinese bytes literals); strict decode implemented (ValueError messages contain 「第 N 条」and both smoke assertions for `第 0 条` passed); Chinese paths/identifiers untouched.
- **API surface for Task 2:** `add`, `insert`, `remove`, `move`, `do_methods`, `to_format_strings`, `from_format_strings` (classmethod), `create_empty` (classmethod), `steps` property, `__len__`, `__iter__`, `__getitem__` — all present and exercised by the smoke.

## Concerns

- None blocking. The only observation worth noting for the controller/reviewer: the brief's expected RED message (`NameError`) differs from the observed `ImportError` for the reason explained above; the RED semantics (class not implemented, EXIT=1) are identical, so no action was taken.
