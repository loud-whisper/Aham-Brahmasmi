# Optional MemPalace semantic recall

Aham Brahmasmi works without MemPalace. The user-owned workspace files remain the durable Brain.

MemPalace can be connected as an optional semantic-memory provider so a runtime can search older context by meaning instead of only reading known files.

## What Aham Brahmasmi verified upstream

The reviewed upstream source is recorded in `third_party/registry.json`.

At the reviewed MemPalace source, its CLI provides the operations used by this adapter:

```text
mempalace --version
mempalace status
mempalace search <query> [--wing <wing>] [--results <n>]
mempalace wake-up [--wing <wing>]
```

Aham Brahmasmi does not copy MemPalace into this repository and does not silently install it. Installation remains controlled by the user and should follow the original MemPalace project's instructions.

## Configure an already-installed MemPalace

First make sure MemPalace itself has been installed and initialized according to its original documentation.

Then connect the private Brain workspace:

```text
python3 scripts/semantic_memory.py configure \
  --workspace <private-workspace> \
  --provider mempalace
```

Configure a default project or client wing for calls without `--project-id`:

```text
python3 scripts/semantic_memory.py configure \
  --workspace <private-workspace> \
  --provider mempalace \
  --wing <wing-name>
```

Configuration succeeds only after the adapter can run both `mempalace --version` and `mempalace status` successfully.

The Brain records only provider identity, optional wing, verification time, and the verified CLI version. It does not copy a palace path, API key, private URL, or maintainer-specific location into the public framework.

## Check status

```text
python3 scripts/semantic_memory.py status --workspace <private-workspace>
```

For machine-readable output:

```text
python3 scripts/semantic_memory.py status --workspace <private-workspace> --json
```

If MemPalace was configured but later becomes unavailable, the status command reports that condition. The local Brain remains usable.

## Search older context

```text
python3 scripts/semantic_memory.py search \
  --workspace <private-workspace> \
  --query "where did we leave off on the migration"
```

Use `--results <n>` when a different result count is useful.

Recall requires a scope. Pass `--project-id <stable-project-id>` to search the wing
with exactly that ID; it overrides the configured default wing. The project must
exist in Aham's registry. Store that project's provider context in the same wing.
Startup reports this scope but does not query the provider. Custom per-project wing
mapping and feeding committed records to the provider are S4 work.

If no project ID is supplied, the configured wing is the selected scope. Configuration
without a wing is allowed for availability checks, but recall refuses before running
the provider. Broad recall requires `--all-scopes`; it omits the wing and warns that
other projects or clients may be returned. A provider that ignores scope arguments
cannot provide isolation; use separate provider stores for such a trust boundary.

Every returned result is inside an untrusted-data envelope and labeled **unverified
recall**. Provider text is one escaped JSON string, so controls, hidden Unicode and
forged block delimiters cannot become raw terminal controls or separate framing lines.
The fixed instruction says this data cannot change Aham rules or grant permissions.
Provider errors are escaped too. No provider text is treated as proof of current fact
status: authenticated record mapping and retraction/supersession handling follow in S4.

Semantic recall is supporting context. It does not override durable files, checkpoint verification, repository state, or the rule that work must not be recorded as completed unless it was actually verified.

## Wake-up context

```text
python3 scripts/semantic_memory.py wake-up --workspace <private-workspace>
```

Scoped wake-up uses `mempalace search "project context for the current session"
--results 5 --wing <scope>`. It is bounded project recall, not MemPalace's native
identity-plus-story wake-up. The pinned native implementation includes global L0
identity even when a wing is supplied, so Aham invokes native `wake-up` only with
the explicit `--all-scopes` choice and warning.

Verified public implementation at the registry pin:
[CLI flags](https://github.com/MemPalace/mempalace/blob/25203ed6ee1a739103a77e87219a1f679dee81e9/mempalace/cli/parser.py),
[command routing](https://github.com/MemPalace/mempalace/blob/25203ed6ee1a739103a77e87219a1f679dee81e9/mempalace/cli/cmd_query.py),
[global L0 in native wake-up](https://github.com/MemPalace/mempalace/blob/25203ed6ee1a739103a77e87219a1f679dee81e9/mempalace/layers.py), and
[wing-filtered search](https://github.com/MemPalace/mempalace/blob/25203ed6ee1a739103a77e87219a1f679dee81e9/mempalace/searcher/cli_search.py).

## Disable the connection

```text
python3 scripts/semantic_memory.py disable --workspace <private-workspace>
```

This removes the Brain's provider configuration only. It does not delete the user's MemPalace data.

## Replaceability

The provider interface is defined in `core/semantic_memory.json`.

Core lifecycle scripts do not contain MemPalace-specific commands. A future semantic-memory provider can be added behind the same operations without changing where Aham Brahmasmi stores its authoritative durable state.
