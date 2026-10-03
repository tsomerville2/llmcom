import { flow } from '@relayflows/surface';

export default flow('exp31-crawl', { budget: { wallclock: '2m' } }, async (f) => {
  const health = await f.run('awstack status', { timeout: '15s' })
    .gate({ type: 'subprocess_gate', command: 'node -e "const x=JSON.parse(process.env.INPUT); if(x.healthHttp!==200 || !x.channels.includes(\"team\")) process.exit(1)"' });
  const history = await f.run('ai-hist stats --json', { timeout: '30s' });
  const decision = await f.run('trail status', { timeout: '15s' })
    .gate({ type: 'subprocess_gate', command: 'test -n "$INPUT"' });
  console.log(JSON.stringify({ health: JSON.parse(health), history: JSON.parse(history), trajectory: decision }));
  f.done('success');
});
