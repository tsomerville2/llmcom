# Claude onboarding: real screens and a blocker

Fresh Claude browser walkthrough and published installer rerun.

GIF: [`claude-onboarding.gif`](claude-onboarding.gif)

Capture: Evidence was captured fresh for this tour unless noted otherwise.

## Materiality Boundary

Existing Mac installer succeeded; clean Mac and David account not tested. No connector was saved on the inspected account.

## What Worked / Covered

- Published installer completed and helper connected on existing Mac.
- Claude Add menu, URL form and authentication form inspected live.

## Defects / Product Findings

- Guide omitted Continue before authentication; corrected.
- Inspected Claude account lacks Request headers even under Advanced; API-key connection cannot finish there.

## Not Materially Proven

- Fresh Mac installation
- David account linking and phone voice round trip

## Follow-up TODOs

- Test David account for Request headers; if absent provide a tested alternative authentication flow.

## Slides

### 1. Add custom connector

- Anchor: Phone setup / Claude
- Story: Open Claude Connectors, then Add.
- Callout: Use the Add menu, not directory search.

### 2. Paste the private URL

- Anchor: Phone setup / URL
- Story: Real form with illustrative field text, not a usable URL.
- Callout: Copy your own URL from the generated private page, then Continue.

### 3. Missing request headers

- Anchor: Phone setup / authentication blocker
- Story: No sign-in selected; Advanced exposes transport only.
- Callout: This account cannot complete the API-key path. Do not claim connection success.
