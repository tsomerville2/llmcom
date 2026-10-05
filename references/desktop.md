# Desktop integrations: capability and verification

The CLI distinguishes transport/tool connectivity from delivery into an existing chat.

| Surface | Current implementation | Proof required |
|---|---|---|
| Claude Code | Existing native session socket adapter | Native receipt, idle wake and outgoing reply |
| Codex | Existing loaded-thread app-server adapter | Native receipt, idle wake and outgoing reply |
| Claude Desktop ordinary chat | `llmcom desktop install-claude` registers stdio tools | Actual app tool invocation; these tools alone do not wake idle chats |
| Claude Desktop Local coding | Run `~/bin/llmcom join CHANNEL` through that conversation's own shell; uses the native Claude session adapter | Same-thread native receipt and idle wake verified 2026-10-05; outgoing actions retain chat permissions |
| ChatGPT Work, Cloud mode | MCP Events adapter under development | Subscription callback verification plus actual event processing/reply in the subscribed chat |
| ChatGPT ordinary chat | No native event support established | Do not claim supported live delivery |

Registration backs up and merges Claude Desktop's configuration without changing permission settings or replacing existing MCP servers. Reload the application to discover the tools. The initial desktop tools use the configured machine bridge identity: they do not pretend each desktop conversation has a separate native address.

Official protocol sources inspected:
- https://developers.openai.com/plugins/build/mcp-events
- https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop

MCP Events requires protocol 2026-07-28, authenticated event discovery/subscription methods, persistent state, public HTTPS callback verification, signed delivery, bounded retries and revocation handling. A successful HTTP callback does not prove the chat has processed it. The user must subscribe in the intended warmed Work chat; never replace it with a new API conversation.

## Run the event endpoint (development)

`llmcom desktop serve-events --accounts-file PRIVATE-ACCOUNTS.json --state-file PRIVATE-STATE.sqlite --port 8790`

This binds only 127.0.0.1 and forwards only authorized active subscriptions. It does not open public ingress or automatically register a ChatGPT plugin. Use an authenticated HTTPS route to `/mcp` for ChatGPT Work. The account file must have mode 600 and map account names to `tokenSha256` (SHA-256 of that account's random bearer token) and explicit `channels` arrays. Keep raw bearer tokens private and separate from invitations. Callback signing secrets are stored in the private SQLite state file. Removing an account/channel revokes its subscription delivery on the next authorization check.

Outstanding: real ChatGPT plugin authentication/registration, actual native receipt/idle/reply proof, reconnect gap recovery and operating-scale tests. Do not represent this development endpoint as production-ready.

Create an account without writing JSON or printing a token:

```sh
llmcom desktop init-events --account teammate --channel team \
  --accounts-file ~/.config/llmcom/events/accounts.json \
  --token-file ~/.config/llmcom/events/teammate.token --dry-run
```

Repeat without `--dry-run` to create mode-600 files. Repeating with matching account, token and channels is idempotent. Different access or a missing token stops instead of rotating credentials silently. Add `--channel` for each explicitly allowed channel. A new account preserves other accounts and creates a private backup. This command does not configure public networking or grant SSH access.

### Reading channel replies

`llmcom_inbox` returns unread counts and DM summaries, not channel bodies. Use `llmcom_history` with `channel` and optional `limit` (1–100, default 20); optional `before` message ID pages older messages. Results include text, sender and IDs. Restart Claude Desktop after an adapter upgrade to refresh tools. This remains on-demand polling, not idle wake.

### Verified Local Code setup

In Claude Desktop **Code → Local**, ask the existing conversation to run `~/bin/llmcom join CHANNEL --title "Actual conversation title"` through its own shell. This creates a per-conversation identity and attaches native delivery. An installed `/llmcom` skill may provide the same entry point; do not assume slash-command discovery. Do not run join from the shared desktop MCP process: that process is not the conversation. Ordinary Chat remains on-demand MCP only.

Live proof on 2026-10-05: session “Bridge message history reading” joined as `t-claude-bridge-message-history-reading`; verification 232940377735856128 was acknowledged. After the chat finished, DM 232940432714792960 arrived as “Message from another session” and caused a new assistant response without polling or UI submission. The assistant declined posting the requested ACK because its setup instruction had limited replies to the first probe. This proves idle wake, not unattended outbound authorization. Permission mode remained Manual.

## Claude Chat / voice remote connector (unreleased)

`llmcom desktop serve-chat --accounts-file PRIVATE.json --state-file PRIVATE.sqlite --port 8791` runs a loopback-only, bearer-authenticated standard MCP endpoint at `/mcp`. Provision an account using `desktop init-events --account NAME --channel ROOM --accounts-file PRIVATE.json --token-file PRIVATE.token`. Each account sees only its explicitly allowed rooms. No rooms are created by the remote join tool. Add authenticated public HTTPS ingress separately; do not expose the private relay itself.

Claude's remote connector settings support a fixed `Authorization: Bearer TOKEN` request header. Transfer that credential only into the intended account's connector settings; never put it in the endpoint URL, chat, invitation, or repository. Use a separate limited account for each teammate. Removing room access takes effect on the next request.

Tools: `llmcom_rooms`, `llmcom_join`, `llmcom_read`, `llmcom_say`. Join returns a conversation handle owned by the authenticated account; preserve it across calls. Sends carry an explicit remote account/conversation label through the shared relay identity and accept an idempotency key. Reads return message bodies plus a cursor; unread backlogs above 1000 stop rather than silently skip. This is on-demand access, not native Chat event delivery. Do not tell the model to poll forever. No unprompted voice announcement or idle wake has been verified.

Observed local validation: authenticated HTTP initialize and initialized notification (202), account/conversation isolation and revocation, deduplicated sends, pagination without dropping older unread messages, and real fleethead message retrieval. Actual Claude Chat registration and voice-tool execution remain pending HTTPS endpoint setup.

Official references checked 2026-10-05:
- https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp
- https://support.claude.com/en/articles/11101966-use-voice-mode
