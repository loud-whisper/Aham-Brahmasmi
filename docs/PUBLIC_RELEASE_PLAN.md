# Preview release procedure

1. Verify the final source tree, dependencies and license notices.
2. Run Foundation, the full Linux suite, the applicable portability jobs and the isolated offline release rehearsal.
3. Review source, every outgoing ref, documentation, binary assets, CI output and release attachments for private information. Handle any credential finding privately and update its consumers before revocation.
4. Reconcile the runtime register, generated status and acceptance checklist. Keep unperformed human and live-runtime checks open.
5. Prepare offline provenance for the reviewed tree using `docs/PROVENANCE.md`.
6. Obtain maintainer authorization for the exact candidate, configure available GitHub safeguards, and publish the preview tag and reviewed assets.
7. Verify anonymous source/download access and standalone setup without any maintainer-owned private resource.

The release label is 0.1.0-preview.1. Publication does not imply completion of stable-release acceptance. Repository settings and outside user data are never changed merely because this file describes them.
