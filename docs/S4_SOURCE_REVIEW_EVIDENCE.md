# S4 MemPalace public source review

Reviewed 2026-10-01 by the solo project maintainer agent. Public sources only;
no private implementation was copied. MemPalace remains an independently
installed optional CLI, registered as a link, not an installable source.

Prior pin: `25203ed6ee1a739103a77e87219a1f679dee81e9`.
Reviewed pin: `f8b9ed1507888cab47c7c7e1d90755f89e0353c4`, committed
2026-09-18. The full one-commit delta includes 23 files: source directory identity
metadata at ingestion sites, conservative sync retention and closet cleanup,
related tests, changelog and reference documentation. No dependency, package,
workflow, hook, executable-permission or hidden-file changes occur in this delta.
Two new regular files implement directory identity and its tests.

The newer branch head `5ea40d30caf0ed2ff6e49623e386a0863b28edaa` from
2026-09-29 was inspected but not selected: its complete delta has 134 changed
files and includes a broader audit/storage/MCP release. The latest published
release observed live is v3.10.0, published 2026-09-16. Source review does not
assert that a released package contains either commit, or guarantee future support.

## Interface and license

At the reviewed pin, `LICENSE`, `README.md`, the CLI parser, query command,
mine command and write-routing module are byte-identical to the prior pin.
The miner change adds directory identity metadata; its absolute source-path
identity, stale drawer replacement and printed processing summary remain.

- [MIT license](https://github.com/MemPalace/mempalace/blob/f8b9ed1507888cab47c7c7e1d90755f89e0353c4/LICENSE), copyright 2026 MemPalace Contributors.
- [CLI parser](https://github.com/MemPalace/mempalace/blob/f8b9ed1507888cab47c7c7e1d90755f89e0353c4/mempalace/cli/parser.py): `--version`, `status`, `search QUERY --wing WING --results N`, `wake-up`, and `mine DIRECTORY --mode projects --wing WING`.
- [Query handler](https://github.com/MemPalace/mempalace/blob/f8b9ed1507888cab47c7c7e1d90755f89e0353c4/mempalace/cli/cmd_query.py): native wake-up still includes global identity, so scoped Aham wake-up uses filtered search.
- [Write routing](https://github.com/MemPalace/mempalace/blob/f8b9ed1507888cab47c7c7e1d90755f89e0353c4/mempalace/cli_write_routing.py): `--direct` selects synchronous legacy routing. Existing hub configuration may still forward mine; incompatible summaries cannot advance Aham progress.
- [Miner](https://github.com/MemPalace/mempalace/blob/f8b9ed1507888cab47c7c7e1d90755f89e0353c4/mempalace/miner.py): stored identity uses absolute `source_file`, modified sources purge old drawers, and exit success may include skipped files. Aham therefore uses stable staging paths and checks counts conservatively.
- [README](https://github.com/MemPalace/mempalace/blob/f8b9ed1507888cab47c7c7e1d90755f89e0353c4/README.md): uv, pipx and Docker choices; `npx skills add` installs a setup skill. No automatic install or package identity claim.
- [Complete delta](https://github.com/MemPalace/mempalace/compare/25203ed6ee1a739103a77e87219a1f679dee81e9...f8b9ed1507888cab47c7c7e1d90755f89e0353c4): directory identity can preserve drawers after transient mount changes, but cannot distinguish every volume replacement. Aham does not invoke sync or pruning.

Required commands were reviewed as source; upstream code, hook scripts and tests
were not executed. Aham's regressions use synthetic workspaces and fake providers.
No provider installation or live personal-record ingestion occurred.

Public open-issue review included [short-source retention #2608](https://github.com/MemPalace/mempalace/issues/2608),
[partial upsert #2122](https://github.com/MemPalace/mempalace/issues/2122),
[directory exclusions #2599](https://github.com/MemPalace/mempalace/issues/2599)
and [wing relocation #2119](https://github.com/MemPalace/mempalace/issues/2119).
An open issue does not establish that its reported code is present at this pin:
the reviewed miner already cleans partial drawers and raises after upsert failure.
Short-source retention remains relevant with large user-configured chunk minimums;
stamps exceed the default minimum but any skip preserves Aham lag. Aham indexes
only its dedicated corpus, resets progress when a wing changes, verifies current
record status independently, and makes no durable provider-ingestion claim.

## Deterministic scan evidence

Both exact commits were fetched into isolated review storage and exported into
quarantine without running their contents. Git metadata is excluded from scans.

| Pin | Files | Bytes | Tree digest | Raw verdict |
| --- | ---: | ---: | --- | --- |
| Prior | 704 | 66,422,152 | `f1f8a8d06f4508c1099187178fe17c9d36301b4adefad507b04729287cf35954` | FAIL |
| Reviewed | 706 | 66,554,277 | `177c93eafd9685a318e77d3a0f54e4c8220e0b3cfee9ba31ab7ccd7db0172f98` | FAIL |

Scanner: `aham-static-skill-scanner` version 3. Rule pack:
`1:66da22d9ca00614fa7da2e8492b8e27d1c8306c8fb3163c8a8305419f1b464d6`.
Each scan has 447 REVIEW and 21 FAIL findings. Eleven finding bindings change
because modified file identities change; counts and classifications do not.
Text-limit concerns remain REVIEW; the scan is a bounded heuristic, not a
complete malware audit.

[Retained inventory](evidence/s4_mempalace_scan_inventory.json) contains all
finding IDs, rules, severities, paths, lines and file digests for both scans,
plus raw-report hashes and limitations. It omits upstream excerpts and repeated
prose; it is a binding inventory, not the raw report. Full raw reports were
retained in local quarantine review storage and can be reproduced by rescanning.

FAIL locations comprise 18 instruction-override findings in benchmark result
JSONL, one direct-write heuristic finding in `examples/cursor/README.md`, and two
sensitive-target findings in `tests/test_hooks_cli.py`. No finding is waived,
lowered or accepted. No source activation is authorized. Registry `expected_scan`
retains FAIL with the current tree/rule binding; the source is not a default offer
and remains a link. Approval covers the documented interface of an independently
user-installed executable, not its safety or source activation. An installer or
skill activation would still require resolution of FAIL through the existing gate.
