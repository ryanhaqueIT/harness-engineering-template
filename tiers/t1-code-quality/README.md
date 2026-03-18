# Tier 1 -- Code Quality

Automated code-quality gates for **Python** and **Next.js** repositories.
T1 is the foundation tier: every repo that adopts the harness gets these gates
before anything else is layered on.

## Gates

| Gate | Tool (Python) | Tool (Next.js) | Blocks merge? |
|------|--------------|----------------|---------------|
| **T1.1 Lint** | ruff | ESLint | Yes |
| **T1.2 Format** | ruff format | Prettier | Yes |
| **T1.3 Typecheck** | pyright | tsc | Yes |
| **T1.4 Tests** | pytest | vitest / jest | Yes |

---

## Install Behavior (2x2 Matrix)

Each gate follows the same decision matrix when `install.sh` runs:

|                    | Tool Missing               | Tool Present          |
|--------------------|----------------------------|-----------------------|
| **Config Missing** | Install tool + copy org default config | Copy org default config |
| **Config Present** | Install tool, leave config | Do nothing            |

"Org default config" files live in `tiers/t1-code-quality/configs/`.

---

## Stack Detection

1. **Repo analyzer** (future): reads CI manifests, imports, and framework
   markers to classify the repo.
2. **Fallback -- file presence**:
   - `pyproject.toml` or `setup.py` present --> **Python**
   - `package.json` present --> **Next.js**
   - Both present --> both stacks apply.

---

## Test Detection Cascades

### Python

```
pyproject.toml [tool.pytest]
  --> pytest.ini
    --> setup.cfg [tool:pytest]
      --> tests/ directory exists
        --> skip (no test config found)
```

### Next.js

```
package.json scripts.test
  --> vitest.config.*
    --> jest.config.*
      --> skip (no test config found)
```

If the cascade ends at "skip," T1.4 is marked *not applicable* and the gate
passes automatically.

---

## Scripts

### `install.sh`

Runs once per repo onboarding. Steps:

1. Detect stack(s) (Python / Next.js / both).
2. For each gate, apply the 2x2 matrix above:
   - Install missing tools (`pip install ruff pyright pytest`,
     `npm i -D eslint prettier typescript vitest`).
   - Copy missing configs from `configs/`.
3. Register a **git pre-commit hook** that calls `post-edit.sh`.
4. Write `.harness/t1-manifest.json` recording what was installed and which
   configs were copied.
5. Run **auto-baseline ratchet**: execute all four gates, capture current
   counts, and write them to `.harness/ratchet-t1.json` so the first CI run
   has a baseline to compare against.

### `validate-t1.sh`

Runs in CI on every push / PR. For each applicable gate it:

1. Runs the tool (e.g. `ruff check .`).
2. Counts errors.
3. Compares the count to the ratchet baseline.
4. **Passes** if count <= baseline; **fails** if count > baseline.
5. If count < baseline, updates the ratchet file (counts can only go down).

Exit code is non-zero if any gate exceeds its baseline.

### `ratchet-t1.py`

Maintains `.harness/ratchet-t1.json` with four tracked categories:

```json
{
  "lint_errors": 42,
  "format_errors": 0,
  "type_errors": 7,
  "test_failures": 3,
  "updated_at": "2026-03-18T00:00:00Z"
}
```

- Values can only **decrease** (ratchet behavior).
- On each run, the script re-measures, compares, and either passes (count <=
  stored) or fails (count > stored).
- When a count drops, the file is rewritten and should be committed.

### `post-edit.sh`

Lightweight hook executed after every save / pre-commit. It:

1. Identifies changed files via `git diff --name-only`.
2. Runs **lint only** on those files (not format, typecheck, or tests).
3. Prints warnings inline -- does **not** block the commit (advisory mode).

---

## Usage Examples

### Onboard a Python repo

```bash
cd ~/projects/my-python-api
/path/to/harness/tiers/t1-code-quality/install.sh
# --> installs ruff, pyright, pytest (if missing)
# --> copies ruff.toml, pyrightconfig.json (if missing)
# --> writes .harness/t1-manifest.json
# --> baselines ratchet counts
```

### Onboard a Next.js repo

```bash
cd ~/projects/my-nextjs-app
/path/to/harness/tiers/t1-code-quality/install.sh
# --> installs eslint, prettier, typescript (if missing)
# --> copies eslint.config.mjs, prettier.config.mjs, tsconfig.base.json (if missing)
# --> writes .harness/t1-manifest.json
# --> baselines ratchet counts
```

### Run validation in CI

```bash
./tiers/t1-code-quality/validate-t1.sh
# exit 0 = all gates pass (at or below ratchet baseline)
# exit 1 = at least one gate regressed
```

### Check ratchet status

```bash
python tiers/t1-code-quality/ratchet-t1.py --status
# lint_errors:    42 (baseline 42) OK
# format_errors:   0 (baseline  0) OK
# type_errors:     5 (baseline  7) IMPROVED -- updating baseline
# test_failures:   3 (baseline  3) OK
```
