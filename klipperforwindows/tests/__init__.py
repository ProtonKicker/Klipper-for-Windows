"""Robustness guardrails for the Klipper for Windows app.

- tests/selftest.py: live endpoint checks (what Mainsail/Fluidd hit)
- tests/scenarios.py: fault-injection scenarios (orphan port squatters,
  killed services, stale state, idempotency) — the app must self-heal
- watchdog.py: stack supervisor that restarts crashed services (bounded)
"""
