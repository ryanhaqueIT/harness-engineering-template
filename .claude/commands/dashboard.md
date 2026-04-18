Launch the Harness DAG Dashboard — an Airflow-inspired live visualization of all 25 validation gates.

## Steps

1. Check if `scripts/dashboard.sh` exists. If not, report that bootstrap is required and suggest running `/bootstrap`.
2. Execute `bash scripts/dashboard.sh` from the repository root.
3. The script will:
   - Generate `.harness/dashboard.html` (self-contained, zero dependencies)
   - Start a local HTTP server on port 8099
   - Open the dashboard in the default browser
4. Report the URL to the user: `http://localhost:8099/dashboard.html`
5. Tell the user they can now run `/validate` in another terminal to watch gates light up in real-time.

## What the Dashboard Shows

- **Pipeline tab**: 6-stage development flow (Spec → Plan → Features → Implement → Validate → Ship)
- **Gates tab**: All 25 validation gates in 7-layer DAG, colored by status
- **Agents tab**: 8 specialized agents with active/idle status
- **History tab**: Airflow-style Grid View with run-over-run gate comparison

## Navigation

- **Arrow keys (◄►)**: Navigate between validation runs
- **Escape**: Return to live polling
- **Click a gate**: Open detail panel with findings and sparkline history
- **Click a run column in History**: Jump to that run's gate state

## Important

- Dashboard server runs in the background. PID saved in `.harness/dashboard.pid`.
- To stop: `kill $(cat .harness/dashboard.pid)` or close the terminal running `dashboard.sh`.
- Requires Python 3.7+ (stdlib only — no pip install needed).
- If port 8099 is in use, set `HARNESS_PORT=9000` before running the script.
