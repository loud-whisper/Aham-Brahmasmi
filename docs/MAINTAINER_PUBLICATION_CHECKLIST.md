# Maintainer publication checklist

This is a checklist for the maintainer, not authorization for an agent to change
settings, remove runners, delete history or publish the repository. No box below
is evidence that a setting has been changed. Names/availability were checked
against official GitHub documentation on 2026-10-01; recheck at publication.

## Before changing visibility

- [ ] Complete R7 real nontechnical walkthroughs and E1's remaining live evidence.
- [ ] Follow the ordered pre-publication review in `docs/dev/R5_REVIEW_FINDINGS.md`.
  Review every retained branch, old PR commit/comment, attachment and CI artifact.
  Existing historical privacy concerns require a human decision; a clean current
  main does not erase PR history. Do not copy sensitive matches into public notes.
- [ ] Re-run all-branch/all-PR pattern scans immediately before publication; review
  their sanitized categories/counts and privately inspect flagged originals.
  Include old and closed PRs, not just open heads. Pattern scans cannot prove absence.
- [ ] Decide which obsolete branches/history may become public. Deletion or history
  rewriting requires separate maintainer authorization; deleting a branch does not
  guarantee removal of GitHub PR references or cached data.
- [ ] Remove the actual self-hosted runner under Settings → Actions → Runners →
  selected runner → Remove, following GitHub's machine removal instructions.
  Retiring its workflow file does not remove its GitHub registration.
  [Official runner removal](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/remove-runners).
- [ ] In account Settings → Emails, select **Keep my email addresses private** and
  **Block command line pushes that expose my email**. Use the owner's GitHub
  noreply address for future commits. This does not rewrite historical addresses.
  The maintainer explicitly designated the email in SECURITY/CODE_OF_CONDUCT for
  public project reporting; that is separate from private author metadata.
  [Email privacy](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address),
  [push blocking](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/blocking-command-line-pushes-that-expose-your-personal-email-address).
- [ ] Verify the reporting contact in `SECURITY.md` and `CODE_OF_CONDUCT.md` is
  monitored. Do not promise a response SLA without a maintainer commitment.

## Repository settings at authorized publication

Some controls are available on GitHub Free for public repositories, but require a
paid plan for private repositories. Do not publish early to unlock a setting.
Record unavailable controls honestly and apply them when visibility is authorized.

- [ ] Settings → Branches → **Add classic branch protection rule**, pattern `main`:
  **Require a pull request before merging**, **Require status checks to pass before
  merging**, and consider **Require branches to be up to date before merging**.
  Select the exact successful check names: `verify-foundation`, the four
  `portability-OS-pyVERSION` jobs and `windows-native-core-py3.14`.
  Required skipped CI cannot validate a code acceptance. Once checks are enforced,
  documentation PRs must satisfy them too; the current [skip ci] savings convention
  may need adjustment. Review approval settings must fit the available maintainers.
  [Official protection and plan availability](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule).
- [ ] Settings → Actions → General → **Approval for running fork pull request
  workflows from contributors**: select **Require approval for all external
  contributors**. Inspect workflow changes before approving their runs. Keep
  workflow token permissions restricted and do not enable write tokens/secrets for
  fork PRs. [Official Actions settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository).
- [ ] Settings → Advanced Security: verify **Secret scanning** and **Push protection**
  are enabled for the authorized public repository. Review findings privately;
  scanners cover supported patterns, not every private fact.
  [Official security settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-security-and-analysis-settings-for-your-repository).
- [ ] Settings → Advanced Security → **Private vulnerability reporting** → Enable.
  Verify **Report a vulnerability** appears on the repository's Advisories page.
  It is a public-repository feature; until available, use SECURITY.md's email route.
  [Official private reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository).
- [ ] Settings → General → Features → **Sponsorships**: enable it so the Sponsor
  button reads `.github/FUNDING.yml` on the default branch. The `github:` entry
  needs an approved GitHub Sponsors profile; confirm both funding pages load.
- [ ] Verify Actions budget/limits and review Dependabot PRs before spending matrix
  minutes. Do not add scheduled full test/rehearsal runs just to poll upstreams.

## Final tree, provenance and release

- [ ] Compare README/STATUS claims with exact evidence, including explicit skips
  and historical live-model scope. Resolve remaining gates; no simulated humans.
- [ ] Run Foundation, the applicable full/portable test gates and
  `PYTHON scripts/release_audit.py` on the actual final reviewed tree.
  Run `--live-upstream` only for a justified final integration gate; retain its pin
  and scanner result. An upstream FAIL remains blocked, even if the lifecycle
  rehearsal correctly refuses activation.
- [ ] Generate a fresh provenance secret offline, outside Git and model access,
  following `docs/PROVENANCE.md`. Bind the final reviewed pre-commitment tree and
  independently verify the commitment. Never upload or paste the secret.
- [ ] Review release notes/version/schema migration limits and CHANGELOG. No
  version/tag/release is implied by the Unreleased entry.
- [ ] Record explicit maintainer authorization for the visibility change and release.
  Only then publish, apply available public controls and create the approved tag.

Leave all unperformed human/settings/publication boxes open. Keep a merged
checkpoint naming the next action so a different agent can resume safely.
