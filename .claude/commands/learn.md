# Learn — Gate Calibration & Pattern Learning

Analyze recent gate results, record calibration data, and suggest improvements.

## Workflow

### Step 1: Run validation and capture results

Run `bash scripts/validate.sh` and parse the output. For each gate that ran:
- Record the gate ID (B1, B8, X7, etc.)
- Record the verdict (PASS/FAIL/SKIP)
- Count the number of findings

### Step 2: Record calibration data

For each gate that produced findings, run:
```
python scripts/gate_calibration.py record --gate {ID} --verdict {VERDICT} --findings {COUNT}
```

If you can identify false positives (findings that are not real issues), add:
```
python scripts/gate_calibration.py record --gate {ID} --verdict {VERDICT} --findings {COUNT} --false-positives {FP_COUNT}
```

### Step 3: Generate report

Run `python scripts/gate_calibration.py report` to see the calibration dashboard.

### Step 4: Get suggestions

Run `python scripts/gate_calibration.py suggest` to see tuning recommendations.

### Step 5: Apply suggestions

If a gate has >50% false positive rate, investigate the findings and either:
- Add exclusion rules to the gate script
- Update the gate's configuration
- Document the false positive pattern for future reference

Report the calibration status to the user.
