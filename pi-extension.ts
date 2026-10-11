// Shared pi / omo extension. No relay credentials or shell-command execution here.
import { openBridge } from './pi-bridge.mjs';
export default function (pi, options = {}) {
  let bridge;
  const keys = ['LLMCOM_SESSION_ID', 'LLMCOM_SOCKET', 'LLMCOM_TOKEN', 'LLMCOM_VENDOR'];
  async function stop() {
    const previous = bridge; bridge = undefined;
    for (const key of keys) delete process.env[key];
    if (previous) await previous.close();
  }
  async function start(_event, ctx) {
    await stop();
    const sessionId = ctx.sessionManager.getSessionId();
    bridge = await openBridge(sessionId, text => {
      if (ctx.sessionManager.getSessionId() !== sessionId) throw new Error('Session changed; rejoin required');
      // Literal collaborator text, never extension commands or prompt expansion.
      const wasIdle = ctx.isIdle();
      pi.sendUserMessage(text, { deliverAs: 'followUp', expandPromptTemplates: false });
      return { wasIdle };
    });
    process.env.LLMCOM_SESSION_ID = sessionId;
    process.env.LLMCOM_SOCKET = bridge.door.socket;
    process.env.LLMCOM_TOKEN = bridge.door.token;
    process.env.LLMCOM_VENDOR = options.vendor || process.env.LLMCOM_HARNESS || (process.env.OMO_CODING_AGENT_DIR ? 'omo' : 'pi');
  }
  pi.on('session_start', start);
  // Upstream pi emits session_switch; Omo emits session_start on switches.
  pi.on('session_switch', start);
  pi.on('session_shutdown', stop);
}
