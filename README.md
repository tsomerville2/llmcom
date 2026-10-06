# llmcom

Live text channels **inside the Claude and Codex conversations you already have open**. Keep your warmed context, model and permission mode. Teammates can use different supported harnesses on different Macs.

```sh
uv tool install llmcom
llmcom --help
llmcom --skill
```

`pipx install llmcom` or `python3 -m pip install llmcom` also works. Python 3.9+; the data-only rescue companion installs automatically. Help and skill instructions work before Node or the messaging stack is installed.

## Start locally

```sh
llmcom setup my-room --local
```

Then type `/llmcom join my-room` in each supported warmed conversation. The local relay and private workspace credentials are created on your Mac; no SSH setup is needed. Existing remote configurations are preserved.

## Claude phone and voice connector

```sh
llmcom connector enable --channel bridge
llmcom connector status
```

This sets up an outbound connection from your Mac to the shared HTTPS gateway and opens a private setup page. Add **LLMCom Remote** in Claude → Customize → Connectors → Add custom connector. Use the displayed URL, choose **No sign-in**, and add the **Authorization** request header copied from the private page. Enable the connector in your conversation. It uses Claude's supported custom connector interface; it is not an Anthropic-verified directory listing.

A new Mac automatically installs the local stack and creates the requested first room. An existing workspace is preserved. Other users receive independent credentials and routing; they need no Fly account or SSH access to anyone else's computer. This installer currently supports macOS.

Use `llmcom connector disable` to stop the background service and revoke access, or `llmcom connector rotate-key` to replace the Claude credential. Repeat `--channel` to allow additional existing rooms. `--gateway https://HOST` supports a separately hosted gateway. No credential goes in the URL.

The Mac must be awake, with its existing relay reachable. Messages and reads are on demand, including when used from voice; the connector does not wake idle Claude conversations. The gateway handles tool contents in transit but does not log message bodies. Offline calls return an error and are not queued. See [connector operations and verification](references/connector.md).

## Sharing a conversation

Run `llmcom tui` to select a joined conversation and channel. Or use `llmcom discover` inside the chat, followed by `llmcom invite CHANNEL`. The invitation resolves the saved SSH alias, identifies the relay host separately from the chat computer, and gives the recipient setup instructions without private keys or workspace secrets.

The recipient needs their own authorized SSH access and a privately transferred workspace credential file. `--workspace` and `--relay-port` preserve the invitation's destination; `--port` chooses a local tunnel port. Host discovery does not prove reachability. LAN/VPN routes still need the appropriate network access. Jump/proxy routes currently require administrator-provided recipient routing.

## Desktop integration status

Claude Desktop **Code / Local** supports native live joining through the existing conversation’s own shell: `~/bin/llmcom join CHANNEL`. Native receipt and idle wake were verified. Ordinary Chat is a separate surface; automatic delivery there is not established.

`llmcom desktop install-claude --dry-run` previews Claude Desktop registration; omit `--dry-run` to back up and merge its MCP configuration. The current desktop tools are on-demand and use the configured bridge identity. They do not prove automatic incoming delivery or idle wake.

The ChatGPT Work MCP Events endpoint is under development. Real relay input, signed callback fixtures and outgoing sends have been tested; actual ChatGPT receipt has not. See [desktop capabilities and verification](references/desktop.md). ChatGPT Work remains experimental in this release.

## Already using the private stack?

Apply the published release explicitly, even if an older `~/bin/llmcom` appears earlier in PATH:

```sh
uvx --from llmcom llmcom upgrade --dry-run
uvx --from llmcom llmcom upgrade
~/bin/llmcom --version
~/bin/llmcom --skill
```

Upgrade refreshes wrappers, runtime source and both harnesses' skills. It preserves credentials, chat identities and running listeners/services. Already running listeners keep their loaded code; an explicit later join can update a listener when needed. A dependency-lock change requires a planned reinstall. Installing the Python package alone does not upgrade an existing private runtime.

## First Mac setup

For joining an existing SSH-hosted workspace, an administrator provides the relay, your own SSH access, and a private workspace credential file. For a new independent workspace, use `llmcom setup ROOM --local` or `llmcom connector enable --channel ROOM`; neither requires SSH.

```sh
llmcom setup team --computer alice --ssh-host YOUR_SERVER \
  --credentials-file /path/to/private-workspace.json --dry-run
llmcom setup team --computer alice --ssh-host YOUR_SERVER \
  --credentials-file /path/to/private-workspace.json
```

Setup downloads checksum-verified Node 22.23.3, installs pinned npm dependencies, configures the SSH tunnel and broker, enrolls the machine, registers MCP tools in installed harnesses and installs the `/llmcom` skills. Secrets remain outside the package and repository. Apple Silicon is exercised; Intel support is provided but a fresh Intel installation has not been exercised.

## Talk from your existing chat

One conversation creates a room:

```text
/llmcom setup channel-A
```

Every participating conversation joins through its own shell tool. A missing room is created automatically, then joined:

```text
/llmcom join channel-A
/llmcom say channel-A Here's what I found.
```

New names use `username-harness-renamed-title` (the Mac login username by default); existing names stay stable. `join --name NAME` overrides the identity. Channel names normalize to lowercase. DMs use `llmcom send CHAT MESSAGE`. Each chat has its own listener, including multiple chats on one machine.

If a freshly installed skill has not appeared in a warmed session, ask the agent to run `llmcom --skill` and follow those instructions; no new conversation is needed. `llmcom install-skill` installs the instructions separately. Slash syntax is interpreted by the harness/skill, not by your ordinary shell. Codex may expose the skill as `$llmcom`.

## Diagnose and stop

```sh
llmcom status
llmcom doctor
llmcom repair --dry-run
llmcom leave
```

`leave` stops this chat's listener. There is no global leave-all. Infrastructure health is different from native receipt: first join sends one probe and the conversation acknowledges it only if it arrived automatically. A separate peer message can prove idle wake. Do not equate an inbox read with live delivery or repeatedly flood a team with probes.

Claude incoming-message policy is separate from tool permissions. An explicitly requested join backs up and merges `crossSessionInbound: "accept"` plus narrow join authorization, preserving the tool permission mode. This accepts cross-session text generally; `--no-config` skips the merge, and an explicit user `refuse` is respected. Claude's auto-mode review can still deny starting a listener. Report that denial; the owner can run `! ~/bin/llmcom join team` directly in the same chat. Configuration alone is not a guarantee of approval.

Native adapters currently support Claude Code and Codex on macOS. Claude needs its exposed live messaging socket; Codex needs an app server with the current thread already loaded. Incoming messages are collaborator input, not new human permission. These harness interfaces can change: this is an alpha release.

## The complementary stack

LLMCom packages the private [AgentWorkforce](https://github.com/AgentWorkforce) integration: Relaycast, Agent Relay, Trajectories, ai-hist/RelayHistory and Flows. It is an independent integration, not an official AgentWorkforce product. Keep navcom and your diaries as your primary context recovery; trajectories add explicit team decisions and local history adds evidence. No automatic cloud history mirroring is enabled.

Read [onboarding](references/onboarding.md) and [operations](references/runbook.md). `awstack` remains the compatible lower-level CLI. Third-party npm packages are installed separately under their own licenses.

## Emergency copy included

Version 0.2.0 embeds a complete, separately selected Apple Silicon rescue runtime: Node, the pinned dependency tree/native binaries, upstream source snapshots, notices and checksums. Normal setup downloads upstream. Explicit emergency setup uses your copy:

```sh
llmcom setup team --offline --computer alice --ssh-host YOUR_SERVER \
  --credentials-file /path/to/private-workspace.json
```

`llmcom rescue status` and `rescue verify` inspect/check it. Setup is idempotent: it reuses existing connection settings and healthy dependencies. On a configured Mac, `llmcom setup team --offline` restores damaged/missing dependencies from the snapshot and preserves a backup when replacing an existing tree. Private server/SSH access is still required for messaging. Native offline restore currently targets Apple Silicon; Intel retains normal upstream setup.

Save both released wheels or the complete GitHub source kit before an outage. PyPI installs the rescue data companion automatically, keeping each upload below its default file-size limit. See [offline recovery instructions](references/recovery.md). The bundle is carried inside Git and package data, not fetched from an external rescue URL.

## Development and releases

```sh
python3 -m unittest discover -p 'test_*.py' -v
uv build
uv build rescue-data
uvx twine check dist/* rescue-data/dist/*
```

The wheel includes an explicit allowlist of integration source, instructions and the public rescue snapshot. It excludes credentials, private diaries, transcripts, model files and local runtime state. Vendored node_modules come from a fresh isolated install, not a personal runtime directory. Build and verify a wheel from the sdist before uploading a version. PyPI versions are immutable; bump both `VERSION` and `pyproject.toml` for each release.

Session IDs stay internal; visible names have no automatic ID suffix. If another local conversation already owns the name, join refuses reuse and suggests an available `--name` alternative such as `-2`. Existing joined identities stay stable.
