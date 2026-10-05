# Desktop integrations: capability and verification

The CLI distinguishes transport/tool connectivity from delivery into an existing chat.

| Surface | Current implementation | Proof required |
|---|---|---|
| Claude Code | Existing native session socket adapter | Native receipt, idle wake and outgoing reply |
| Codex | Existing loaded-thread app-server adapter | Native receipt, idle wake and outgoing reply |
| Claude Desktop ordinary chat | `llmcom desktop install-claude` registers stdio tools | Actual app tool invocation; these tools alone do not wake idle chats |
| Claude Desktop Local coding | Inspect its exposed session interface; do not assume ordinary-chat or CLI equivalence | Same-thread receipt and reply |
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
