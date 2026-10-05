# 0.3 development acceptance audit

This is an incomplete development release. Passing transport tests is not a native chat receipt claim.

| Requirement | Evidence | Status |
|---|---|---|
| Discover selected conversation, channels, workspace and SSH route | discover command, workspace ID allowlist, SSH alias resolution, saved tunnel plist inspection | Implemented; current Mac verified |
| Distinguish chat computer from relay host | Separate output fields, arbitrary-host fixtures | Implemented |
| Any channel rather than a hardcoded example | TUI second-conversation/third-channel test; actual current session lookup | Implemented |
| Portable invitation with SSH ports and private access instructions | invite output; nondefault port/workspace tests; private key/API key exclusion | Implemented for direct SSH; proxy/jump routes report missing recipient route |
| Explain network/firewall/VPN requirements | invite text plus discover --check categories | Implemented; recipient network not live-tested |
| Idempotency and preservation | Python disposable-home tests, existing 8 JavaScript regressions, upgrade reports no listener restarts | Verified within tested scope |
| Claude Desktop ordinary chat tools | App initialized stdio server; real channels tool transport call | Registration/transport proved; chat invocation blocked on usable signed-in app |
| Claude Desktop ordinary chat native wake | No established native event interface | Not implemented/proven; on-demand tools explicitly labelled |
| Claude Desktop Local coding native adapter | Existing CLI adapter retained; desktop-specific same-thread test absent | Incomplete |
| ChatGPT Work native events | Official MCP Events docs; authenticated endpoint, signed verified callbacks, durable subscriptions and queue | Implemented protocol/transport; real plugin registration/receipt blocked on HTTPS endpoint and app access |
| ChatGPT ordinary chat live integration | Official native-event docs apply to Work/Cloud, not ordinary chat | No native support claimed |
| Live input, idle wake and outgoing reply in each supported existing desktop conversation | Real relay -> reader -> queue -> signed fixture; real outgoing relay message | Desktop requirement NOT met; fixtures are not chat proof |
| Desktop credential isolation and authorization | Hash-only endpoint account credentials, channel allowlists, private SQLite, callback SSRF checks, revocation tests | Tested locally |
| Packaging and local install | Development wheel build/fresh install, runtime upgrade and skills | Development artifact prepared; not a published release |
| Documentation/diary | README, --help, --skill, desktop.md, project diary | Updated with limits |

External inputs needed for the next full test: a usable signed-in Claude Desktop chat, and a ChatGPT Work connection to an authenticated HTTPS MCP endpoint. The computer-use tool refused the selected ChatGPT app identity; no bypass attempted. No public ingress has been opened.

Event-account provisioning, bounded retries, key rotation and per-subscription echo suppression now have tests. The next acceptance gate is an actual authenticated desktop host connection: the MCP handshake, native event processing and reply behavior must be observed before further compatibility changes or release claims. Disconnects are detected; replay is explicitly unsupported. No claim of lossless recovery is made. Do not mark the overall goal complete from this audit.
