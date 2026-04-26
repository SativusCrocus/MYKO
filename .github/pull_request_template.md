<!--
Thanks for contributing to MYKO.

Before opening, confirm:
  - You read CONTRIBUTING (or the README install/verify section).
  - This PR does not include secrets, paths, or personal npubs/nsec/macaroons.
  - For security-sensitive changes, you considered the threat model in SECURITY.md.

Keep PRs small and reviewable. Large changes are easier to review as a stack.
-->

## Summary

<!-- 1–3 sentences on what this PR does and why. -->

## Changes

<!-- Bulleted, file-anchored list. Reviewers should be able to scan it. -->

-

## Verification

- [ ] `pytest tests/ -v` — all 173 tests pass locally
- [ ] `cd frontend && npx tsc --noEmit` — no new type errors
- [ ] If the change touches crypto / Nostr / Lightning, tests in those modules cover it
- [ ] If the change touches docs, the affected commands have been re-run locally

## Threat-model impact

<!--
Required for any change to backend/crypto.py, backend/bridge.py,
backend/nostr.py, backend/lightning.py, or anything that handles
secrets, network IO, or audit logging.

If unaffected, write "n/a — no surface change."
-->

## Screenshots / output

<!-- Optional. UI changes benefit from before/after. -->

## Linked issues

<!-- "Fixes #123" / "Refs #456" -->
