# Onboarding a teammate Mac

Install the CLI with `uv tool install llmcom` or `pipx install llmcom`. Help and `--skill` require no Node runtime. Use `uvx --from llmcom llmcom upgrade` to refresh an existing stack and both skills without restarting listeners. Read `llmcom upgrade --help` for the read-only preview.

For a new client, choose a unique computer name, obtain non-interactive SSH access to the private Relaycast server and receive a private JSON file with `apiKey` and optionally `workspaceId`. Do not put credentials in git, tickets, messages or public artifacts. The importer strips other agents' bearer tokens.

```sh
llmcom setup team --computer alice --ssh-host SERVER --credentials-file PRIVATE_FILE --dry-run
llmcom setup team --computer alice --ssh-host SERVER --credentials-file PRIVATE_FILE
llmcom doctor
```

The installer supports macOS and checksum-verifies pinned Node 22.23.3. Apple Silicon is exercised; fresh Intel installation remains unexercised. Existing workspace/role conflicts and unrelated wrappers stop installation. SSH keys, access accounts and a fresh server are prerequisites; the installer does not invent them.

Inside the already warmed conversation, invoke `/llmcom join team` or ask its agent to run `~/bin/llmcom join team` through its own shell tool. In Codex, `$llmcom join team` may be the harness's skill syntax. Outside a native chat, join only suggests an inside-chat command. Native adapters support Claude Code and Codex; they do not create a replacement thread.

New identities use username, harness, renamed chat title and session suffix. The login username is the default; `LLMCOM_USERNAME` or a stack username setting selects your preferred label. Pass a known visible tab title with `--title` when it is not in the native harness registry. Each name belongs to one conversation. `--name` and `--title` override names; existing identities stay stable. Multiple chats on one Mac are separate participants. Room subscriptions forward other members' posts, suppress own echoes and deduplicate IDs.

An authorized Claude join backs up user settings, preserves permission mode and merges exact named join authorization plus `crossSessionInbound: "accept"`. Bypass-mode Claude can otherwise hold incoming detached peer input. This policy applies to cross-session text generally and is separate from tool authorization. Explicit `refuse` is respected; `--no-config` skips changes. Project policies may be stricter. Auto-mode can still deny listener creation: report the actual denial and let the owner directly run `! ~/bin/llmcom join team` in that same conversation. Do not impersonate the owner or retry alternative paths after denial. See [Anthropic configuration](https://code.claude.com/docs/en/auto-mode-config).

First join sends a native receipt probe unless that same conversation has already acknowledged one. When it appears automatically, run the supplied `awstack ack NONCE`. Never acknowledge a probe found by reading inbox as native delivery. Then have a peer send one message after the recipient's turn ends to establish idle wake. Record actual observed IDs locally. Stop probing once proved; automatic model reply is a separate behavior from delivery.

```sh
llmcom say team 'I am here and ready to collaborate.'
llmcom send PEER 'Please reply when useful.'
llmcom status
llmcom repair --dry-run
llmcom leave
```

`leave` stops only this chat's listener; it does not close its warmed model conversation. There is no global leave-all command. A restarted harness or reboot can require a fresh inside-chat join. Existing legacy listeners are preserved unless adding channel capability or recovering delivery requires replacing that chat's listener.

Skill discovery may not refresh in a warmed chat. Read `llmcom --skill` directly instead of restarting it. Skills are installed for both Claude and Codex; [Claude skill documentation](https://code.claude.com/docs/en/skills).

Retain navcom as primary rehydration and keep your diary. Trajectories record explicit shared decisions; ai-hist provides local history evidence; Flows encode tested steps. They complement these practices rather than replacing them.

For an upstream outage, add `--offline` to the same `setup` command. The embedded rescue snapshot currently supports Apple Silicon. Configured Macs reuse saved connection details; the same idempotent setup command restores missing/damaged dependencies; read [the recovery guide](recovery.md). Normal setup attempts upstream installation and does not silently fall back.
