# Task 1 Report: `StepManager` 模型扩展(移动 / 分组 / 类访问)

## What I implemented

In `model/step_manager.py`:

1. **Assertion block** (verbatim from brief, with ONE documented one-character deviation, see Issues): inserted after all existing smoke assertions, immediately before `print("StepManager smoke OK")`. Covers:
   - `move_template`: top-level → subdir success; target-exists → log "已存在" + no overwrite; unknown path → ValueError
   - `rename_group`: whole-group move with path sync; same-name target → log + group unchanged; illegal names / unknown group → ValueError; nested group rename preserves parent
   - `create_group`: top-level + nested success; duplicate → log; illegal names / missing parent → ValueError
   - `template_class`: returns the registered class; unknown path → ValueError

2. **Four methods** (verbatim from brief), inserted after `copy_source_templates`, before class body ends:
   - `template_class(path) -> type` — read-only registry lookup; unknown → ValueError
   - `move_template(path, target_dir="") -> None` — registry lookup → target conflict pre-check via `pkg.exists()` → error log + return if exists; else `pkg.move` + `load()` + info log
   - `rename_group(group, new_name) -> None` — validates name (empty/`/`/`.`/`..` → ValueError), `pkg.is_dir` check, parent-aware target, exists pre-check, `pkg.move` + `load()`
   - `create_group(name) -> None` — validates segments (`.`, `..`, empty → ValueError), parent must exist (`is_dir`), exists pre-check, `pkg.make_dir`

   No implementation path calls `create_step` (展示模板不创建对象). No Chinese bytes literals, no relative imports, all conflicts pre-checked with `exists()`, errors via `LogModel.error()`, successes via `LogModel.info()`.

## What I tested and test results

| Command | Result |
|---|---|
| `python -m model.step_manager` (RED) | `AttributeError: 'StepManager' object has no attribute 'move_template'`, EXIT=1 |
| `python -m model.step_manager` (GREEN) | `StepManager smoke OK`, EXIT=0 |
| `python -m actions.base` | `Step smoke OK`, EXIT=0 (known runpy RuntimeWarning on stderr) |
| `python -m actions.控制流程.time_delay` | `TimeDelay smoke OK`, EXIT=0 (known runpy RuntimeWarning) |
| `python -m model.kscp_package` | `KscpPackage smoke OK`, EXIT=0 (known runpy RuntimeWarning) |

## TDD Evidence

- **RED** — `python -m model.step_manager`:
  ```
  File "...\model\step_manager.py", line 445, in <module>
      mgr.move_template("本地", "子目录")
  AttributeError: 'StepManager' object has no attribute 'move_template'. Did you mean: 'remove_template'?
  EXIT=1
  ```
  Expected: first new-assertion call fails on the missing method — 功能缺失 red. All pre-existing assertions passed before reaching it, so the red is precisely at the new block's first call, as the brief requires.

- **GREEN** — `python -m model.step_manager`: `StepManager smoke OK`, EXIT=0.

- **Extra red→fix cycle (brief deviation)**: initial GREEN run failed at line 553 with `AssertionError` on `assert not any(p.startswith("新组/深") for p in mgr.template_paths())`. Root cause analysis below.

## Files changed

- `C:\Users\feelnn\Desktop\项目\KScript\model\step_manager.py` — added 4 methods + smoke assertion block (modified only; no other files touched)

## Self-review findings

- **Deviation from verbatim (one character), justified and verified**: brief line `assert not any(p.startswith("新组/深") ...)` was changed to `p.startswith("新组/深/")` (added trailing slash). At that point in the smoke the registry necessarily contains `新组/深层` (file `深层.py` was renamed 子目录 → 新组 earlier and is untouched by the nested-group rename), and `"新组/深层".startswith("新组/深")` is True — so the assertion as written can never pass, for ANY implementation of the (also verbatim) 4 methods. `新组/深层` is a sibling file under `新组`, not under group `新组/深`. The brief's own sibling assertion uses the correct form (`p.startswith("子目录/")`), and the block comment's intent ("重命名保留父组" — nothing remains under the renamed-away group path) is satisfied only by the trailing-slash form. Verified: with the fix, no remaining path (`控制流程/示例, 示例, 本地2, 新组/本地, 新组/深层, 新组/更深/本地2`) starts with `新组/深/`, and the assertion now passes. RED phase was unaffected (AttributeError fires at the first assertion line, before this line).
- Ending-state precondition verified by reading the file before editing: registry ends with 控制流程/示例、示例、本地、本地2、子目录/深层; files 本地步骤.py、本地2.py、子目录/深层.py — matches brief.
- API surface verified against `model/kscp_package.py` (move/exists/is_dir/make_dir/files) and `model/log_model.py` (error/info/entries/clear, `e.message`) before editing; `move` rekeys file paths so "移动建组" into a not-yet-existing directory works without extra mkdir.
- No duplicate logic: methods reuse `_actions_rel`, `load()`, existing pre-check idioms.
- Constraints honored: no `create_step` in implementation paths; no git commands (repo is not git); no new imports needed in smoke (`os`, `sys`, `LogModel` already imported there).

## Issues or concerns

1. **Brief typo** (the `新组/深` → `新组/深/` fix above) — the only deviation from verbatim; needs controller acknowledgment.
2. Nothing else outstanding; dependency chain fully green.
