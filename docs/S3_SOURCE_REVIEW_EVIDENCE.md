# S3 Superpowers scanner context checkpoint

D8: review Superpowers first; defer more default collections.

Reviewed public source: [obra/superpowers](https://github.com/obra/superpowers/tree/b36e0829c6d0140e93cfef2ca599b1b07d4a7797).

Exact commit: `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`.
Tree digest: `2818b581e7b187d000c18d75c53ca392b1cd64c072bcff27edaf924110262789`.
Rule pack: `1:66da22d9ca00614fa7da2e8492b8e27d1c8306c8fb3163c8a8305419f1b464d6`.

Local live-upstream rehearsal passed on 2026-10-01. The unchanged tree contains 194 files and 1,711,850 bytes. Raw verdict is REVIEW: 98 REVIEW and 2 INFO findings. Activation was attempted and refused; the installed manifest stayed unchanged and quarantine was retained. No findings were accepted.

## Corrections

The prior S1 report remains historical evidence. Its two direct-write FAIL findings were test-server failure messages in `tests/brainstorm-server/windows-lifecycle.test.sh` at lines 240 and 304. The third was a browser-cookie comment at line 119 of `skills/brainstorming/scripts/start-server.sh`, escalated because an unrelated read occurred elsewhere in the script.

Eight inert regressions establish the distinction while retaining real direct-write and credential-read FAIL cases. Whole-line shell comments retain REVIEW. JavaScript `process.env` property access no longer counts as a dotenv path; actual dotenv paths remain findings. The updated rule pack invalidates prior activation reviews and waivers until content is rescanned under current rules.

## Remaining finding inventory

Every row remains unaccepted. Bundled scripts and hooks were never executed. This inventory is evidence, not approval or a claim of safety.

| Rule | Severity | Path | Line | Disposition |
| --- | --- | --- | --- | --- |
| text.hidden_comment | REVIEW | `.github/ISSUE_TEMPLATE/bug_report.md` | 1 | Pending explicit finding review |
| text.hidden_comment | REVIEW | `.github/ISSUE_TEMPLATE/feature_request.md` | 1 | Pending explicit finding review |
| text.hidden_comment | REVIEW | `.github/ISSUE_TEMPLATE/platform_support.md` | 1 | Pending explicit finding review |
| text.hidden_comment | REVIEW | `.github/PULL_REQUEST_TEMPLATE.md` | 1 | Pending explicit finding review |
| text.long_line | REVIEW | `.kimi-plugin/plugin.json` | 25 | Pending explicit finding review |
| target.sensitive | REVIEW | `RELEASE-NOTES.md` | 169 | Pending explicit finding review |
| execution.binary | REVIEW | `assets/app-icon.png` | 1 | Pending explicit finding review |
| text.hidden_comment | REVIEW | `docs/superpowers/plans/2026-02-19-visual-brainstorming-refactor.md` | 1 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 106 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 121 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 155 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 184 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 255 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 298 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 355 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 636 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 1070 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 1141 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 1154 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 1179 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-05-06-lift-drill-into-evals.md` | 1294 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-06-10-visual-companion-auth-hardening.md` | 197 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-06-10-visual-companion-auth-hardening.md` | 519 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/plans/2026-06-10-visual-companion-auth-hardening.md` | 526 | Pending explicit finding review |
| text.hidden_comment | REVIEW | `docs/superpowers/specs/2026-02-19-visual-brainstorming-refactor-design.md` | 1 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-05-06-lift-drill-into-evals-design.md` | 38 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-05-06-lift-drill-into-evals-design.md` | 109 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-05-06-lift-drill-into-evals-design.md` | 125 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-05-06-lift-drill-into-evals-design.md` | 132 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-05-06-lift-drill-into-evals-design.md` | 135 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-05-06-lift-drill-into-evals-design.md` | 139 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-05-06-lift-drill-into-evals-design.md` | 154 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-05-06-lift-drill-into-evals-design.md` | 222 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-06-10-visual-companion-auth-hardening-design.md` | 14 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-06-10-visual-companion-auth-hardening-design.md` | 15 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-06-10-visual-companion-auth-hardening-design.md` | 62 | Pending explicit finding review |
| target.sensitive | REVIEW | `docs/superpowers/specs/2026-06-10-visual-companion-auth-hardening-design.md` | 112 | Pending explicit finding review |
| execution.agent_hooks | REVIEW | `hooks/hooks.json` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `hooks/run-hook.cmd` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `hooks/session-start` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `scripts/bump-version.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `scripts/lint-shell.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `scripts/package-codex-plugin.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `scripts/sync-to-codex-plugin.sh` | 1 | Pending explicit finding review |
| text.hidden_comment | REVIEW | `skills/brainstorming/scripts/server.cjs` | 1 | Pending explicit finding review |
| target.sensitive | REVIEW | `skills/brainstorming/scripts/start-server.sh` | 119 | Pending explicit finding review |
| execution.script | REVIEW | `skills/brainstorming/scripts/start-server.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `skills/brainstorming/scripts/stop-server.sh` | 1 | Pending explicit finding review |
| target.sensitive | REVIEW | `skills/brainstorming/visual-companion.md` | 53 | Pending explicit finding review |
| text.hidden_comment | REVIEW | `skills/brainstorming/visual-companion.md` | 1 | Pending explicit finding review |
| skill.length | INFO | `skills/subagent-driven-development/SKILL.md` | 1 | Informational |
| execution.script | REVIEW | `skills/subagent-driven-development/scripts/review-package` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `skills/subagent-driven-development/scripts/sdd-workspace` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `skills/subagent-driven-development/scripts/task-brief` | 1 | Pending explicit finding review |
| target.sensitive | REVIEW | `skills/systematic-debugging/SKILL.md` | 98 | Pending explicit finding review |
| execution.script | REVIEW | `skills/systematic-debugging/find-polluter.sh` | 1 | Pending explicit finding review |
| skill.length | INFO | `skills/writing-skills/SKILL.md` | 1 | Informational |
| execution.script | REVIEW | `skills/writing-skills/render-graphs.js` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/antigravity/run-tests.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/antigravity/test-antigravity-tools.sh` | 1 | Pending explicit finding review |
| target.sensitive | REVIEW | `tests/brainstorm-server/auth.test.js` | 285 | Pending explicit finding review |
| target.sensitive | REVIEW | `tests/brainstorm-server/branding.test.js` | 37 | Pending explicit finding review |
| target.sensitive | REVIEW | `tests/brainstorm-server/lifecycle.test.js` | 223 | Pending explicit finding review |
| target.sensitive | REVIEW | `tests/brainstorm-server/lifecycle.test.js` | 233 | Pending explicit finding review |
| target.sensitive | REVIEW | `tests/brainstorm-server/lifecycle.test.js` | 289 | Pending explicit finding review |
| target.sensitive | REVIEW | `tests/brainstorm-server/lifecycle.test.js` | 299 | Pending explicit finding review |
| text.hidden_comment | REVIEW | `tests/brainstorm-server/server.test.js` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/brainstorm-server/start-server.test.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/brainstorm-server/stop-server.test.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/brainstorm-server/windows-lifecycle.test.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/claude-code/analyze-token-usage.py` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/claude-code/run-skill-tests.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/claude-code/test-helpers.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/claude-code/test-sdd-workspace.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/claude-code/test-subagent-driven-development-integration.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/claude-code/test-subagent-driven-development.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/claude-code/test-worktree-native-preference.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/claude-code/test-worktree-path-policy.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/codex-plugin-sync/test-sync-to-codex-plugin.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/codex/test-marketplace-manifest.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/codex/test-package-codex-plugin.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/devin/test-devin-plugin.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/explicit-skill-requests/run-all.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/explicit-skill-requests/run-extended-multiturn-test.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/explicit-skill-requests/run-haiku-test.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/explicit-skill-requests/run-multiturn-test.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/explicit-skill-requests/run-test.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/hooks/test-session-start.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/kimi/run-tests.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/kimi/test-plugin-manifest.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/opencode/run-tests.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/opencode/setup.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/opencode/test-bootstrap-caching.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/opencode/test-plugin-loading.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/opencode/test-priority.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/opencode/test-tools.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/shell-lint/test-lint-shell.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/systematic-debugging/test-find-polluter.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/version-bump/test-bump-version.sh` | 1 | Pending explicit finding review |
| execution.script | REVIEW | `tests/writing-skills/test-render-graphs.sh` | 1 | Pending explicit finding review |

## Verification

Local red: eight tests, four expected failures in the context distinctions. Targeted green: eight tests. Existing S1 regressions: 25 tests passed. Stable full local suite: 294 tests, one expected skip. Exact implementation `9dff88db264eadabea07bc9c7c037d9e14e41fe6` passed all six jobs in workflow `36883836912`: Linux 294, Ubuntu/macOS Python 3.10/3.14 portability 259 each (two skips per macOS job), Windows unsupported-write refusal. PR #54 merged as `5c1723a78b01af8156a3fbdc705b091181f8d62d`. One ready matrix, no hosted red or draft gate; 520 summed runner seconds and 13 per-job rounded minutes, not billing usage.

S3 lifecycle commands, registry expected-scan metadata and the complete acceptance gate remain pending. No additional default collection is approved by this checkpoint.
