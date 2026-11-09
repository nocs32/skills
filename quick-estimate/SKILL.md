---
name: quick-estimate
description: Fast hour estimate for a work task from a short description and context. Use when asked for an estimate, how long something takes, or how many hours.
---

# Quick estimate

Give one number, fast. Estimates are conservative: they include a standard contingency, so the work fits comfortably inside the number.

## Rules

- When the request gives enough to work with, don't ask: turn missing details into assumptions.
- When the request has almost no context (a bare title, no scope), ask 1-3 short questions that would move the number most, in one message, then estimate. Never turn it into a questionnaire.
- Keep it quick. A few light lookups are fine when they sharpen the number, such as reading the relevant file or ticket. No broad research unless asked.
- Work in hours. Round the total UP to one of: 0.5, 1, 2, 3, 4, 6, 8, 12, 16, 20, 24, 28, 32, 36, 40, then steps of 4 (half a day).

## How to estimate

1. Split the task into 2-6 parts.
2. Estimate each part realistically for an experienced developer.
3. Add the parts that are easy to forget, when relevant:
   - Testing: unit and integration tests, coverage requirements, test data and fixtures
   - Delivery: deployment, environment setup, migrations, configuration per environment
   - Access and wiring: permissions and roles, feature flags, connecting new pieces into existing screens or routes
   - Debugging: time lost to the platform's own quirks and tooling
   - Collaboration: code review fixes, clarifications and communication, one round of feedback fixes, handover notes
4. Add contingency to the sum:
   - x1.3 for clear, familiar work
   - x1.5 for normal work with some unknowns
   - x2 for vague requests, new technology, or third-party integrations
5. Round the total up. Spread the contingency across the parts so the breakdown adds up to the total.

## Output format

**Estimate: Xh**

- Part - Yh
- Part - Yh

Assumes: one short line with the key assumptions or risks that would change the number. Leave it out if nothing important.

Nothing else: no intro, no explanation of the method, and no questions alongside an estimate.

## Example

Input: estimate - add an "Export to CSV" button to the admin orders table that downloads the currently filtered rows

**Estimate: 4h**

- Export endpoint and CSV generation - 2h
- Button, download handling, permission check - 1h
- Tests and deploy - 1h

Assumes: existing filter logic can be reused server-side, exports stay small enough to build in one request.
