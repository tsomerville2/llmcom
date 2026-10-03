import assert from 'node:assert/strict';
import test from 'node:test';
import { assertUniqueName, channelInput } from './session.mjs';

test('a third conversation cannot reuse another conversation identity', () => {
  assert.throws(() => assertUniqueName('shared', 'third', [{ id: 'first', name: 'shared' }, { id: 'second', name: 'shared-2' }]), /--name shared-3/);
});
test('the owning conversation can reconnect using its identity', () => {
  assert.doesNotThrow(() => assertUniqueName('shared', 'first', [{ id: 'first', name: 'shared' }]));
});
test('a new conversation may use its own unique identity', () => {
  assert.doesNotThrow(() => assertUniqueName('unique', 'third', [{ id: 'first', name: 'shared' }]));
});
test('channel membership and sender identity filter broadcasts', () => {
  const session = {name:'mine',channels:['alpha']};
  const event = {channel:'#alpha',message:{id:'1',agentId:'other',agentName:'friend',text:'hello'}};
  assert.match(channelInput(event,session,'me').text,/llmcom say alpha/);
  assert.equal(channelInput({...event,channel:'beta'},session,'me'),null);
  assert.equal(channelInput({...event,message:{...event.message,agentId:'me'}},session,'me'),null);
});
