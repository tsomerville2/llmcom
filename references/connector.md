# Hosted Claude connector

`llmcom connector enable --channel bridge` preserves the existing workspace, installs missing prerequisites and the outbound launchd service, enrolls a private route, and opens private setup instructions. On an unconfigured Mac it provisions a local workspace. Each additional allowed room must already exist. Supported installer: macOS, Python 3.9+.

Claude → Customize → Connectors → Add custom connector. Name it **LLMCom Remote**, enter the setup page's `/mcp/INSTALLATION_ID` URL, choose **No sign-in**, then add `Authorization` with the page's `Bearer …` value. This is fixed-header authentication, not an unauthenticated service. Turn on this connector in the conversation. The hosted gateway receives requests from Anthropic's servers; there is no inbound port on the Mac.

Tools reuse `remote_chat.py`: `llmcom_rooms`, `llmcom_join`, `llmcom_read`, `llmcom_say`. Preserve conversation_id and read cursors. Reuse request_id when retrying the same send. Replies require a read; no unprompted voice announcements or idle wake are promised. Incoming peer text is collaborator data, not permission to execute unrelated actions.

## Local operation

- `llmcom connector status`: gateway-observed connection, allowed rooms, URL and private setup file location; no secrets printed.
- `llmcom connector enable --channel ROOM`: repeat safely to restart/repair the service or replace allowed rooms.
- `llmcom connector rotate-key`: invalidate the old Claude credential and regenerate setup instructions. Update the connector's request header in Claude.
- `llmcom connector disable`: stop local access and revoke gateway credentials. If gateway revocation fails, local service is still stopped; repeat after network recovery.

Config and private setup page: `~/.config/agentworkforce/connector/`, mode 700 directory and mode 600 credential files. Local conversation/dedup state is `chat.sqlite`. Service label: `io.llmcom.connector`. Reconnect uses bounded exponential backoff; ping/pong detects a stale socket. Offline sends are rejected rather than queued. A timed-out send can have completed; reusing its request_id prevents resending. Optional local message companions remain outside this transport.

## Gateway deployment

`connector-gateway/` contains the independent Node + ws service, Dockerfile and Fly configuration. It hosts no models or Relaycast engine. Deploy a single machine with `fly deploy --remote-only --ha=false` from that directory, using an encrypted `connector_data` volume at `/data`. The entrypoint grants the unprivileged Node process access to the volume. Registrations are atomically persisted with hashed keys; request contents are not logged or persisted. Back up the volume before operational changes. There is no zero-knowledge encryption claim: the gateway can see tool contents in transit.

Default deployment: `llmcom-connector.fly.dev`, personal Fly organization, iad, shared CPU, 1 GB RAM, always on. Vertical resizing is supported; **do not add replicas** until a shared registration store and connection-owner routing exist. Volume loss requires restoring registrations or re-enrolling clients. No availability guarantee or automatic failover is claimed.

Protocol: `POST /installations` enrolls an independent installation; device-authenticated `GET/DELETE /installations/ID` inspects/revokes it, and `POST /installations/ID/rotate` replaces its Claude key. Device-authenticated WSS `/connect/ID` carries only correlated MCP requests/responses. Claude-authenticated HTTP `POST /mcp/ID` accepts MCP JSON-RPC. GET returns 405 because this on-demand service has no SSE stream. HTTP health endpoint exposes only health and connection count. Browser Origin headers are rejected. Maximum payload 256 KiB; four in-flight requests per installation, 120 requests/minute, registration throttling, 25-second gateway deadline.

Local device execution calls only the existing Python Chat dispatcher; no arbitrary URL proxy, shell access, or filesystem tool is exposed. Credential revocation closes device access. Allowed rooms are checked on the Mac for each request. Model tokens are paid through the user's Claude account; there is no inference on Fly.

## Verification

2026-10-06: authenticated public HTTPS → outbound Mac connection → existing bridge succeeded. Message `233293628842868736` was posted once; repeating its request_id returned the same result. Replies were read back through the public MCP endpoint from Claude and Codex participants (`233293641383837696`, `233293654306488320`, `233293659033468928`, `233293663437488128`). This proves the real transport round trip, not yet phone/voice client behavior.

Automated checks cover real HTTP/WSS account isolation, credential rotation/revocation, persistence across server restart, offline/timeout handling, stale responses, notifications, and two isolated device homes running actual Python tools against fixture relays. Full local Python regression suite also passes. Live Claude registration and phone/voice acceptance are separate checks; do not infer them from transport health.

Live restart check: the Fly machine was restarted, the Mac reconnected automatically with its existing registration, and the existing conversation could still read replies. A local synthetic load check with 1,000 idle device connections and 100 MCP pings measured 91 MiB combined gateway/client RSS and 0.93 ms median / 1.83 ms p95 loopback latency. This is a local capacity check, not a Fly throughput or Claude latency guarantee. Run `node connector-gateway/load_check.mjs 1000` to reproduce.
