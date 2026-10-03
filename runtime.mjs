import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const stackDir = path.join(os.homedir(), '.local/share/agentworkforce/stack');
export const configDir = path.join(os.homedir(), '.config/agentworkforce');
export const stateDir = path.join(os.homedir(), '.local/state/agentworkforce');
export function readConfig() {
  return JSON.parse(fs.readFileSync(path.join(configDir, 'stack.json'), 'utf8'));
}
export function credentials() {
  return JSON.parse(fs.readFileSync(path.join(configDir, 'workspace.json'), 'utf8'));
}
export function privateJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temporary = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(temporary, file);
  fs.chmodSync(file, 0o600);
}
export function toolEnvironment({ agent = true } = {}) {
  const config = readConfig();
  const secret = credentials();
  const env = {
    ...process.env,
    PATH: `${path.join(stackDir, '../node/bin')}:${os.homedir()}/bin:${process.env.PATH}`,
    RELAY_BASE_URL: config.baseUrl,
    RELAY_API_KEY: secret.apiKey,
    RELAY_WORKSPACE_KEY: secret.apiKey,
    TRAJECTORIES_DATA_DIR: path.join(stateDir, 'trajectories'),
    DO_NOT_TRACK: '1',
  };
  if (agent) {
    const identity = process.env.AWSTACK_IDENTITY || config.identity;
    if (secret.agents?.[identity]) env.RELAY_AGENT_TOKEN = secret.agents[identity].token;
  }
  return env;
}
