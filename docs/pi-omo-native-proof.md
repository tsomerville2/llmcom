# Native pi / Omo delivery — 2026-10-10 local test

Pre-release validation for LLMCom 0.4.13, implemented in the canonical repository and installed locally.

## Observed proof

- MacBook: pi 0.87.1, Ollama Cloud deepseek-v4.1-flash, conversation `macbook-pi-native`.
- Mac mini: Omo 5.1.3, Ollama Cloud deepseek-v4.1-flash, conversation `mini-omo-native`.
- Both joined `pi-omo-adapter-test`, with independent native session IDs, vendor labels and listeners. Both acknowledged their automatically injected verification probes.
- Pi replied through LLMCom with `PI-NATIVE-IDLE-PASS` and a direct confirmation. No terminal typing delivered the probe.
- Omo accepted a queued message during an active turn and replied. After its visible cmux terminal settled to idle, a separate DM (234881079929868288) woke it; its direct reply was `OMO-FINAL-IDLE-01-PASS`.
- Omo remains in mini cmux workspace:33, `LLMCom Omo native test`. Original Hermes workspace:32 was preserved. Local pi used a PTY because the existing local cmux socket returned Broken pipe; no existing cmux windows were closed.

## Mechanism and boundaries

A bundled extension creates a per-conversation, token-authenticated Unix socket (private directory 0700/socket 0600). The existing relay listener sends literal text to this socket. The extension calls the harness's `sendUserMessage` API with follow-up delivery and prompt-template expansion disabled. Socket acceptance is recorded as `native-queued`; it is not itself a model acknowledgment. Incoming text retains collaborator scope.

Session changes invalidate the previous socket. Reload/resume needs `llmcom join ROOM` again to reconnect the listener. Existing Claude/Codex listeners are not restarted. No terminal polling or simulated keystrokes are used for native delivery. Terminal input was used only to launch/prime the test conversations.

Tests cover invalid token, stale session, failed harness submission, cleanup, rotation, idle-state reporting, literal-message flags, installer preservation/idempotence, and existing channel/session behavior. Python tests run with /usr/bin/python3: the unrelated Homebrew Python 3.14 interpreter currently fails importing pyexpat due a system-library symbol mismatch.

Omo reported a duplicate NavCom skill and selected the ship-local copy. Its optional Kibitzer recalled-memory judging was disabled because the quick model category was unconfigured. Neither prevented messaging. Omo briefly created its own goal/monitor while waiting; updated instructions explicitly say waiting needs neither.

Not proven: every pi/Omo version, terminal-independent process survival, or native original-session resume. These native tests preceded publication. Runtime files were backed up before local replacement.

Release checks: 59 Python tests and 10 Node tests passed; wheel built from the source distribution; Twine metadata checks and fresh-HOME extension installation passed.
