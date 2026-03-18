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
   - Install missing tools (`pip install ruff pyright`,
     `npm i -D eslint prettier typescript`).
   - Copy missing configs from `configs/`.
3. Copy `validate-t1.sh`, `ratchet-t1.py`, and `post-edit.sh` into `.harness/`.
4. Register a **git pre-commit hook** (symlink) that calls `validate-t1.sh`.
5. Write `.harness/manifest.json` recording which tiers and stacks are installed.
6. Run **auto-baseline ratchet**: execute `ratchet-t1.py` which counts current
   violations and writes them to `.harness/t1-baseline.json`.
7. Update `.gitignore` to exclude the baseline and instance-metadata files.

### `validate-t1.sh`

Runs on every commit (via pre-commit hook) or manually. For each applicable gate it:

1. Checks if the tool is available.
2. Runs the tool (e.g. `ruff check .`).
3. **Passes** if the tool exits 0; **fails** if non-zero.
4. Skips the gate (yellow) if the tool isn't installed.

Exit code is non-zero if any gate fails. Skips don't count as failures.

### `ratchet-t1.py`

Maintains `.harness/t1-baseline.json` with four tracked categories:

```json
{
  "lint_errors": 42,
  "format_errors": 0,
  "type_errors": 7,
  "test_failures": 3
}
```

- Values can only **decrease** (ratchet behavior).
- On first run, auto-creates the baseline from current counts (no `--init` needed).
- On each subsequent run, re-measures, compares, and either passes (count <=
  stored) or fails (count > stored).
- When a count drops, the baseline is rewritten (improvement locked in).

### `post-edit.sh`

Lightweight hook executed after every save / pre-commit. It:

1. Identifies changed files via `git diff --name-only`.
2. Runs **lint only** on those files (not format, typecheck, or tests).
3. Prints warnings inline -- does **not** block the commit (advisory mode).

---

## Usage Examples

### Onboard a Python repo

```bash
bash /path/to/harness/tiers/t1-code-quality/install.sh ~/projects/my-python-api
# --> installs ruff, pyright (if missing)
# --> copies ruff.toml, pyrightconfig.json (if missing)
# --> writes .harness/manifest.json
# --> baselines ratchet counts to .harness/t1-baseline.json
```

### Onboard a Next.js repo

```bash
bash /path/to/harness/tiers/t1-code-quality/install.sh ~/projects/my-nextjs-app
# --> installs eslint, prettier, typescript (if missing)
# --> copies eslint.config.mjs, prettier.config.mjs, tsconfig.json (if missing)
# --> writes .harness/manifest.json
# --> baselines ratchet counts to .harness/t1-baseline.json
```

### Run validation

```bash
bash .harness/validate-t1.sh
# exit 0 = all gates pass
# exit 1 = at least one gate failed
```

### Check ratchet status

```bash
python3 .harness/ratchet-t1.py --show
# lint_errors          42
# format_errors         0
# type_errors           7
# test_failures         3
```
