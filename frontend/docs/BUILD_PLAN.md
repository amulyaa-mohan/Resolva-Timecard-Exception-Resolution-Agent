# Frontend build sequence

1. Agree API contracts and reusable screen states with backend owners.
2. Build application navigation and exception inbox: severity, employee/location filters and selection.
3. Build the resolution panel: schedule and punch timeline, evidence sources, proposal, citations and checks.
4. Implement approve/edit/reject/escalate interactions with server confirmation and stale-state handling.
5. Add import preview, invalid-row feedback and confirmation using the agreed import API.
6. Add audit history and policy details; clearly preserve original versus corrected records.
7. Add supported-language requests and eligible bulk decisions after backend contracts exist.
8. Verify accessibility, responsive layouts and the full missing-punch-to-audit journey.

The current connection page is only scaffolding. No exception or decision API exists yet.
Use synthetic fixtures while waiting for SHARED-01; label fixture-backed screens in development.
Do not build analytics, decorative animation or extra dashboards before the core journey works.
