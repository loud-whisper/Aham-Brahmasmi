# S1 scanner evidence

## Pinned upstream rehearsal

Executed locally on 2026-10-01 using `scripts/release_audit.py --live-upstream`.
This exercised the isolated lifecycle and the upstream scan/activation boundary.
It used no hosted Actions minutes and executed no fetched Superpowers scripts.

- Source: [obra/superpowers](https://github.com/obra/superpowers/tree/b36e0829c6d0140e93cfef2ca599b1b07d4a7797).
- Exact pin: `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`.
- Tree digest: `2818b581e7b187d000c18d75c53ca392b1cd64c072bcff27edaf924110262789`.
- Rule pack: `1:c01922ce1eaf2020d9cb24d4bc68ccde41e27ff5a5935c90bbee784e8d71d2fa`.
- Reviewed tree: 194 files, 1,711,850 bytes, excluding Git metadata.
- Result: FAIL; 160 findings (3 FAIL, 155 REVIEW, 2 INFO).
- Activation: blocked; active manifest remained unchanged and quarantine was retained during the rehearsal.
- Lifecycle rehearsal: passed. This is not an approval of the upstream tree.

The three FAIL findings are potential context false positives: a browser-cookie
comment in a script that also contains a read operation, and two generic state
references in a test script. Sensitive-target matches also include environment
property syntax. Broad lexical checks do not distinguish these contexts reliably.
No rule was weakened to obtain PASS and no human acceptance was invented.
The unchanged Superpowers pin is therefore unavailable for activation under this
rule pack. S3 source review must resolve this through reviewed rule improvements
with regressions or an explicitly reviewed adaptation; FAIL has no normal waiver.

Every finding is accounted for below by rule, path and line. Repeated identical
matches on one line are represented once. Dispositions describe the observed
match category; they do not establish whole-file safety or grant acceptance.
Source text and scripts are not copied into this evidence document.

| Severity | Rule | Path | Lines | Disposition |
| --- | --- | --- | --- | --- |
| FAIL | `aham.direct_write` | `tests/brainstorm-server/windows-lifecycle.test.sh` | 240, 304 | Generic application/test state name; potential contextual false positive. FAIL retained. |
| FAIL | `target.sensitive` | `skills/brainstorming/scripts/start-server.sh` | 119 | Browser-cookie comment co-occurs with a script read operation; potential contextual false positive. FAIL retained. |
| INFO | `skill.length` | `skills/subagent-driven-development/SKILL.md` | 1 | Specification length guidance only; does not block activation. |
| INFO | `skill.length` | `skills/writing-skills/SKILL.md` | 1 | Specification length guidance only; does not block activation. |
| REVIEW | `execution.agent_hooks` | `hooks/hooks.json` | 1 | Real agent hook configuration; review before enabling it. |
| REVIEW | `execution.binary` | `assets/app-icon.png` | 1 | PNG asset falls under conservative binary detection; provenance review required. |
| REVIEW | `execution.script` | `hooks/run-hook.cmd` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `hooks/session-start` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `scripts/bump-version.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `scripts/lint-shell.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `scripts/package-codex-plugin.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `scripts/sync-to-codex-plugin.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `skills/brainstorming/scripts/start-server.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `skills/brainstorming/scripts/stop-server.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `skills/subagent-driven-development/scripts/review-package` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `skills/subagent-driven-development/scripts/sdd-workspace` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `skills/subagent-driven-development/scripts/task-brief` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `skills/systematic-debugging/find-polluter.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `skills/writing-skills/render-graphs.js` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/antigravity/run-tests.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/antigravity/test-antigravity-tools.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/brainstorm-server/start-server.test.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/brainstorm-server/stop-server.test.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/brainstorm-server/windows-lifecycle.test.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/claude-code/analyze-token-usage.py` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/claude-code/run-skill-tests.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/claude-code/test-helpers.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/claude-code/test-sdd-workspace.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/claude-code/test-subagent-driven-development-integration.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/claude-code/test-subagent-driven-development.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/claude-code/test-worktree-native-preference.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/claude-code/test-worktree-path-policy.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/codex-plugin-sync/test-sync-to-codex-plugin.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/codex/test-marketplace-manifest.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/codex/test-package-codex-plugin.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/devin/test-devin-plugin.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/explicit-skill-requests/run-all.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/explicit-skill-requests/run-extended-multiturn-test.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/explicit-skill-requests/run-haiku-test.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/explicit-skill-requests/run-multiturn-test.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/explicit-skill-requests/run-test.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/hooks/test-session-start.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/kimi/run-tests.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/kimi/test-plugin-manifest.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/opencode/run-tests.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/opencode/setup.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/opencode/test-bootstrap-caching.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/opencode/test-plugin-loading.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/opencode/test-priority.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/opencode/test-tools.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/shell-lint/test-lint-shell.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/systematic-debugging/test-find-polluter.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/version-bump/test-bump-version.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `execution.script` | `tests/writing-skills/test-render-graphs.sh` | 1 | Real executable/interpreter surface; read before any separately authorized execution. |
| REVIEW | `target.sensitive` | `.opencode/plugins/superpowers.js` | 58 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `RELEASE-NOTES.md` | 169 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `docs/plans/2025-11-22-opencode-support-design.md` | 160, 161 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `docs/plans/2026-01-17-visual-brainstorming.md` | 45, 46, 322 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `docs/superpowers/plans/2026-03-11-zero-dep-brainstorm-server.md` | 161, 162, 163, 164 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 106, 121, 155, 184, 255, 298, 355, 636, 1070, 1141, 1154, 1179, 1294 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `docs/superpowers/plans/2026-06-10-visual-companion-auth-hardening.md` | 197, 517, 519, 526 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `docs/superpowers/plans/2026-06-11-visual-companion-final-hardening-fixup.md` | 337, 353, 393, 407, 453, 454 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `docs/superpowers/specs/2026-05-06-lift-drill-into-evals-design.md` | 38, 109, 125, 132, 135, 139, 154, 222 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `docs/superpowers/specs/2026-06-10-visual-companion-auth-hardening-design.md` | 14, 15, 62, 112 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `skills/brainstorming/scripts/server.cjs` | 85, 90, 100, 101, 102, 112, 113, 123, 133, 134, 293, 533, 539, 540, 555, 561 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `skills/brainstorming/visual-companion.md` | 53 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `skills/systematic-debugging/SKILL.md` | 98 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `skills/systematic-debugging/defense-in-depth.md` | 58 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `skills/systematic-debugging/root-cause-tracing.md` | 77 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `tests/brainstorm-server/auth.test.js` | 78, 285 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `tests/brainstorm-server/branding.test.js` | 33, 37 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `tests/brainstorm-server/lifecycle.test.js` | 83, 84, 132, 146, 197, 221, 223, 233, 258, 285, 289, 299, 327, 332, 359, 375, 409, 423, 451, 482, 495 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `tests/brainstorm-server/server.test.js` | 54 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `target.sensitive` | `tests/hooks/test-session-start.sh` | 74, 122, 127 | Environment-property, cookie or keychain mention; contextual human review still required. |
| REVIEW | `text.hidden_comment` | `.github/ISSUE_TEMPLATE/bug_report.md` | 1 | Long hidden comment; inspect full context before acceptance. |
| REVIEW | `text.hidden_comment` | `.github/ISSUE_TEMPLATE/feature_request.md` | 1 | Long hidden comment; inspect full context before acceptance. |
| REVIEW | `text.hidden_comment` | `.github/ISSUE_TEMPLATE/platform_support.md` | 1 | Long hidden comment; inspect full context before acceptance. |
| REVIEW | `text.hidden_comment` | `.github/PULL_REQUEST_TEMPLATE.md` | 1 | Long hidden comment; inspect full context before acceptance. |
| REVIEW | `text.hidden_comment` | `docs/superpowers/plans/2026-02-19-visual-brainstorming-refactor.md` | 1 | Long hidden comment; inspect full context before acceptance. |
| REVIEW | `text.hidden_comment` | `docs/superpowers/specs/2026-02-19-visual-brainstorming-refactor-design.md` | 1 | Long hidden comment; inspect full context before acceptance. |
| REVIEW | `text.hidden_comment` | `skills/brainstorming/scripts/server.cjs` | 1 | Long hidden comment; inspect full context before acceptance. |
| REVIEW | `text.hidden_comment` | `skills/brainstorming/visual-companion.md` | 1 | Long hidden comment; inspect full context before acceptance. |
| REVIEW | `text.hidden_comment` | `tests/brainstorm-server/server.test.js` | 1 | Long hidden comment; inspect full context before acceptance. |
| REVIEW | `text.long_line` | `.kimi-plugin/plugin.json` | 25 | Long JSON instruction string; inspect the complete value. |

## Regression evidence

PR #50 retains the original hosted failing baseline: 251 tests, exactly 18
new failed assertions in workflow `36867861182`. Additional local failing
cases preceded implementation of advisory review, external adapters, waivers,
activation verification, output bounds, CLI paths and duplicate identities.
Exact head `de9c1eaec9de42ee2cbfcec7337c186fbc0cc660` passed hosted acceptance
`36873888390`: six jobs, 273 full Linux tests, 238 tests per Ubuntu/macOS Python
3.10/3.14 job (two skips per macOS job), and Windows unsupported-write refusal.
Draft Linux `36873457417` and stable local 273-test run also passed. PR #50 merged
as `4e2d68ad13cefc927539ae7a68063bc72a282270`. The acceptance matrix used 412 seconds
of summed runner wall time, or 11 minutes rounding each job up; this excludes the
separate draft and baseline gates and is not billing usage.
