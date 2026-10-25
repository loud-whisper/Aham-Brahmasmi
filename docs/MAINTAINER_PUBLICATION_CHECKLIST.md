# Maintainer publication checklist

## Candidate review

- [ ] Run the final source and isolated release checks in `docs/TEST_PLAN.md`.
- [ ] Review source, reachable history, refs, CI output and attachments for credentials, personal information and private dependencies.
- [ ] Check licensing and required third-party notices.
- [ ] Keep real newcomer and live-runtime checks open until independently performed.
- [ ] Confirm the monitored reporting route in `SECURITY.md` and `CODE_OF_CONDUCT.md`.
- [ ] Use a GitHub noreply author address and inspect commit/tag metadata.
- [ ] Keep release keys and provenance secrets offline and outside Git.

## GitHub settings

- [ ] Verify the default branch, required passing checks, protection rules and available security features.
- [ ] Use hosted runners for public contributions. Registering a self-hosted runner requires a separate security decision.
- [ ] Keep workflow token permissions restricted. Review fork workflow changes before approval and do not expose write tokens or secrets to fork PRs.
- [ ] Enable available secret scanning, push protection and private vulnerability reporting; document any unavailable feature accurately.
- [ ] Confirm intentional funding links and maintainer contact details.

## Release

- [ ] Prepare and verify the provenance commitment for the final reviewed tree.
- [ ] Obtain explicit maintainer authorization for public exposure and tagging.
- [ ] Publish reviewed assets, then verify anonymous downloads and documented setup.

Settings are performed by an authorized maintainer. These boxes are not evidence that an action occurred. Consult current GitHub documentation before changing settings.
