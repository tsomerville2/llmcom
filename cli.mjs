import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { stackDir, toolEnvironment, stateDir, readConfig, configDir } from './runtime.mjs';

const [name, ...args] = process.argv.slice(2);
const allowed = new Set(['agent-relay', 'ai-hist', 'ai-hist-mcp', 'trail', 'flows', 'relaycast-mcp']);
if (!allowed.has(name)) throw new Error(`Unknown stack tool: ${name}`);
let env = { ...process.env, PATH: `${path.join(stackDir, '../node/bin')}:${process.env.PATH}` };
if (['agent-relay', 'flows', 'relaycast-mcp'].includes(name)) {
  const mcp = name === 'agent-relay' && args[0] === 'mcp';
  env = toolEnvironment({ agent: !mcp && name !== 'relaycast-mcp' });
  if (name === 'agent-relay' && args[0] === 'node' && args[1] === 'up') {
    const file = path.join(configDir, 'node.json');
    if (fs.existsSync(file)) {
      const record = JSON.parse(fs.readFileSync(file));
      env.RELAY_NODE_TOKEN = record.token;
      env.RELAY_NODE_ID = record.id;
    }
  }
  if (mcp) {
    delete env.RELAY_AGENT_TOKEN;
    const role = readConfig().role;
    const session = process.env.CLAUDE_CODE_SESSION_ID || process.env.CODEX_THREAD_ID || `mcp-${process.pid}`;
    env.RELAY_AGENT_NAME = `${role}-${session.slice(0,18)}`;
  }
}
if (name === 'trail') env.TRAJECTORIES_DATA_DIR = path.join(stateDir, 'trajectories');
// Resolve each published binary by its npm .bin link; never interpolate arguments into a shell.
const child = spawn(path.join(stackDir, '../node/bin/node'), [path.join(stackDir, 'node_modules/.bin', name), ...args], {
  stdio: 'inherit', env,
});
child.on('error', (error) => { console.error(error.message); process.exitCode = 1; });
child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exitCode = code ?? 1;
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
