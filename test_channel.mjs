import test from 'node:test';
import assert from 'node:assert/strict';
import { ensureChannel } from './channel.mjs';

test('setup/join reuse an existing room without creating it again',async()=>{
  const room={name:'team'};
  const client={channels:{list:async()=>[room],create:async()=>{throw new Error('should not create')}}};
  assert.deepEqual(await ensureChannel(client,'team'),{record:room,created:false});
});
test('joining a missing room creates it',async()=>{
  let room;let creates=0;
  const client={channels:{list:async()=>room?[room]:[],create:async({name})=>{creates++;return room={name}}}};
  assert.equal((await ensureChannel(client,'new-team')).created,true);
  assert.equal((await ensureChannel(client,'new-team')).created,false);
  assert.equal(creates,1);
});
test('a concurrent creator is reused; a genuine error is reported',async()=>{
  let lists=0;
  const client={channels:{list:async()=>++lists===1?[]:[{name:'team'}],create:async()=>{throw new Error('conflict')}}};
  assert.equal((await ensureChannel(client,'team')).created,false);
  const denied={channels:{list:async()=>[],create:async()=>{throw new Error('denied')}}};
  await assert.rejects(()=>ensureChannel(denied,'team'),/denied/);
});
