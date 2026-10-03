# Vendored emergency installation

LLMCom 0.2.0 embeds a separate Apple Silicon rescue snapshot in the GitHub repository, wheel and source distribution. It contains Node 22.23.3, the exact installed npm dependency tree including native SQLite/history/broker/Flows binaries, upstream source archives, licenses/notices, a package inventory and checksums. Ordinary setup continues downloading pinned upstream dependencies. There is no silent fallback.

## Ordinary installation

```sh
uv tool install llmcom
llmcom setup team --computer alice --ssh-host SERVER --credentials-file PRIVATE_FILE
```

Alternatively, install the same release directly from GitHub:

```sh
uv tool install \
  --with 'https://github.com/tsomerville2/llmcom/releases/download/v0.2.0/llmcom_rescue_data-0.2.0-py3-none-any.whl' \
  'https://github.com/tsomerville2/llmcom/releases/download/v0.2.0/llmcom-0.2.0-py3-none-any.whl'
```

Setup attempts dependency installation itself, then configures the private tunnel/broker/MCP/skills. SSH access and the private workspace file are still prerequisites.

## Save the complete release before an outage

Keep both release wheels or the complete GitHub source kit on a disk you control. The data-only `llmcom-rescue-data` companion installs automatically with `llmcom`, splitting the embedded payload to keep each PyPI file below its default 100 MB limit. The `rescue/` directory must remain with the scripts. Both GitHub and PyPI are distribution locations, not automatic backups of dependencies. Keep a second copy outside those services. Installing the CLI plus its automatic data companion carries the whole rescue snapshot.

```sh
python3 -m pip download llmcom==0.2.0 -d saved-release
# From a local wheel, with no package registry access:
python3 -m pip install --no-index --find-links saved-release llmcom==0.2.0
```

The complete GitHub source kit also works directly with macOS system Python: `./llmcom --help`; it does not need pip/uv to bootstrap. Wheels and tarballs are attached to the GitHub release too.

## Explicit emergency setup

```sh
llmcom rescue status
llmcom rescue verify
llmcom setup team --offline --computer alice --ssh-host SERVER --credentials-file PRIVATE_FILE
```

`--offline` means no upstream dependency/runtime downloads. Your private Relaycast server and SSH connection must still be reachable; messaging is a network service. No cloud account, SSH key, harness install or hosted model service is created by this backup.

The bundled native snapshot currently supports **macOS Apple Silicon (`darwin-arm64`)**. Intel Macs retain ordinary upstream installation. Offline restore rejects an unsupported architecture rather than installing the wrong binaries.

## One idempotent setup command

```sh
llmcom setup team
# Select the embedded copy explicitly during an upstream outage:
llmcom setup team --offline
# Inspect the selected action without changing installation state:
llmcom setup team --offline --dry-run
```

An already configured Mac reuses its saved connection details and healthy dependencies. Missing/damaged dependencies are installed using the selected mode; an offline replacement preserves the old tree under `~/.local/share/agentworkforce/rescue-backups/`. Setup refreshes integration/skills when this release differs, then creates or reuses the room. It does not restart warmed conversations/listeners. A new Mac reports the missing connection arguments; the LLM asks the owner only for those values and repeats the same command.

Inside the same warmed chat, read `llmcom --skill` and invoke `/llmcom join team` (or `$llmcom` in Codex). Join creates a missing room, attaches this conversation, and reports whether it created the room. Repeated joins keep the same identity and avoid repeating an already pending/acknowledged receipt probe. Join must run through the chat's own shell tool; it does not create a replacement model conversation or change permission mode.

## Provenance and maintenance

`rescue/manifest.json` records pinned lock hash, payload/part hashes, native ABI, upstream source commits and any omitted foreign broker binaries. `packages.json` records installed package versions, registry origins, integrity values and declared licenses. Original third-party license/notice files remain inside the runtime and upstream archives; root notices are also under `rescue/sources/`. Source entries with `exactReleaseSource=false` are explicitly reference snapshots, not claimed to match the npm release; the executable npm snapshot itself is the exact pinned tree.

The maintainer script `vendor.py --node-archive VERIFIED_NODE_ARCHIVE` builds a fresh isolated npm-ci tree, checks native SQLite, archives source and compresses the payload into ordinary 20 MiB files. The parts live in normal Git and package data, without Git LFS or external rescue downloads. Verification detects missing/corrupt parts before runtime installation. Update and retest this snapshot whenever changing the dependency lock or native runtime.
