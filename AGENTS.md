# Engineering rules

- SQLite is the only online business source of truth. SSE, logs and in-memory objects are projections.
- Every invocation must reach `completed`, `failed` or `aborted`, including disconnects and restart recovery.
- Public writes must be idempotent at the repository boundary. Do not add a second write path for appointments, handoffs, behavior events or memory consolidation.
- API routes validate and authorize; state machines and transactions live in services; repositories own persistence.
- Never expose chain-of-thought, secrets, contacts or raw tool payloads in Trace. Emit structural progress and redacted evidence.
- Changes to workflow phases, handoff states, memory scoring, appointment states or security levels require matching documentation and regression tests.
- Run `python -m compileall -q .`, `pytest`, and `python -m evaluation.runner --fail-on-gate` before delivery.

