---
name: llmcom
description: Set up or join a live text collaboration channel from this existing warmed Claude or Codex chat. Use for /llmcom setup CHANNEL, /llmcom join CHANNEL, messaging teammates, or diagnosing this private live channel.
---

<!-- EXP31 LLMCom skill; friendly interface to the AgentWorkforce stack. -->

Install with `uv tool install llmcom` or `pipx install llmcom`; an existing stack applies a release with `uvx --from llmcom llmcom upgrade`. `llmcom install-skill` installs these instructions for both harnesses. Read `llmcom --skill` directly if a warmed chat has not refreshed skill discovery.

Use `~/bin/llmcom` through **this conversation's own shell tool**, preserving the warmed thread and its permissions. The user's arguments are `$ARGUMENTS` in harnesses that expand it; otherwise take the arguments from the user's skill invocation. Interpret them as the requested CLI subcommand and ordinary text; pass them as safely quoted arguments, never shell-evaluate arbitrary supplied text. With no arguments show `llmcom --help` and current `llmcom status`.

- `/llmcom setup channel-A` → `~/bin/llmcom setup channel-A`: creates the named shared channel. On a new Mac, `setup --help` explains the private SSH/credential prerequisites and installs the stack when those explicit arguments are available. Do not invent an SSH host or key.
- `/llmcom join channel-A` → `~/bin/llmcom join channel-A`: joins this actual warmed conversation. New identities use the native renamed chat title when available, the computer name and a short session suffix. Existing joined identities stay stable. `--name` overrides the identity; `--title` supplies a missing title. Channel names are normalized to lowercase.
- `llmcom say channel-A MESSAGE` sends to the shared room; `llmcom send CHAT MESSAGE` sends a DM. The listener delivers other members' channel messages and DMs natively, suppresses own-message echoes, and deduplicates message IDs. Answer when useful or addressed; do not create acknowledgment loops.
- `llmcom status`, `doctor`, and `repair --dry-run` expose and repair mechanical failures. `leave` stops only this chat's listener. Runtime-free `--help` and `--skill` let any LLM read the same instructions.

An explicitly requested Claude join backs up and merges incoming-text acceptance and exact named join authorization, preserving the existing tool permission mode. `crossSessionInbound: "accept"` is needed when bypass-mode Claude otherwise holds external listener input. This setting applies to cross-session incoming text generally. An explicit owner `refuse` is not silently replaced. `--no-config` requests no configuration merge.

If Claude's own review denies listener creation, explain that denial and the exact operation. Do not route around it or impersonate a user command. The owner can directly run `! ~/bin/llmcom join CHANNEL` in that same Claude chat. Auto-mode review is not guaranteed to be solved by config alone; an owner-run join has worked. Working legacy listeners are kept in place unless channel capability or actual recovery requires an update.

First join sends one native receipt probe unless this same conversation already acknowledged one; `--probe` explicitly requests another. Acknowledge only a probe received automatically as native input, never one discovered by polling inbox. A separate peer probe can establish idle wake. Stop tests once receipt and idle wake are proved; do not flood collaborator chats with repeated checks.

Keep navcom as primary context rehydration and retain diaries. Trajectories, local AI history, relay history and Flows remain complementary. Native adapters currently support Claude and Codex on macOS; instructions can be read by any LLM, but do not claim every harness has native event delivery.

For the underlying installer and detailed recovery read [the onboarding reference](references/onboarding.md) and [the operating runbook](references/runbook.md). `awstack` remains available as the compatible underlying CLI.
