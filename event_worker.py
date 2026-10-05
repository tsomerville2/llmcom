"""Supervised relay process feeding the persistent webhook outbox."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
from event_delivery import Outbox


class RelayWorker:
    def __init__(self, store, script=None, node=None):
        self.store=store
        self.outbox=Outbox(store)
        home=Path.home()
        script=script or Path(__file__).with_name('event_relay.mjs')
        node=node or home/'.local/share/agentworkforce/node/bin/node'
        environment=dict(os.environ);environment.pop('NODE_OPTIONS',None)
        self.process=subprocess.Popen([str(node),str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=environment)
        self.events=queue.Queue(maxsize=1000)
        self.stopped=threading.Event()
        self.channels=None
        self.connected=False
        self.gap_observed=False
        self.reader=threading.Thread(target=self.read,daemon=True);self.reader.start()

    def read(self):
        for line in self.process.stdout:
            try:
                event=json.loads(line)
                if not isinstance(event,dict):continue
            except ValueError:continue
            while not self.stopped.is_set():
                try:self.events.put(event,timeout=.2);break
                except queue.Full:continue
            if self.stopped.is_set():break

    def tick(self):
        if self.process.poll() is not None:
            raise RuntimeError('Relay reader exited; event service must be restarted by its supervisor.')
        rows=self.store.db.execute('SELECT DISTINCT channel FROM subscriptions WHERE expires>?',(self.store.clock(),)).fetchall()
        channels=sorted(row[0] for row in rows if self.store.matching(row[0]))
        if channels!=self.channels:
            self.process.stdin.write(json.dumps(channels)+'\n');self.process.stdin.flush();self.channels=channels
        for _ in range(100):
            try:event=self.events.get_nowait()
            except queue.Empty:break
            if event.get('status')=='connected':
                self.connected=True;continue
            if event.get('status')=='disconnected':
                self.connected=False;self.gap_observed=True;continue
            try:self.outbox.enqueue(event['channel'],event['message_id'],event['sender'],event['text'],event['timestamp'])
            except (KeyError,ValueError,TypeError):continue
        self.outbox.deliver_one()

    def close(self):
        self.stopped.set()
        self.process.terminate()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.reader.join(timeout=1)
        self.process.stdin.close();self.process.stdout.close()
