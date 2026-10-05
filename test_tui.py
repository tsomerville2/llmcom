import unittest
from unittest.mock import patch
from tui import run

class TUITests(unittest.TestCase):
    def test_selects_other_conversation_and_channel(self):
        info={'conversationComputer':'sender-mac','workspace':'another-workspace','workspaceId':'ws-two',
              'conversations':[{'name':'first','vendor':'claude','channels':['one']},{'name':'second','vendor':'codex','channels':['two','three']}],
              'relay':{'hostname':'relay.example.org','sshPort':2222,'user':'operator','remotePort':8888,'remoteBind':'127.0.0.1','requiresJumpHost':False,'requiresProxyCommand':False},
              'networkRequirements':'Route to relay required.','accessRequirements':'Own authorized key required.'}
        replies=iter(['2','2','2']);output=[]
        with patch('tui.discover',return_value=info):run('/unused',read=lambda _:next(replies),write=output.append)
        invitation=output[-1]
        self.assertIn('channel three',invitation)
        self.assertIn('--workspace another-workspace',invitation)
        self.assertIn('--relay-port 8888',invitation)
        self.assertIn('relay.example.org',invitation)
        self.assertNotIn('bridge',invitation)

if __name__=='__main__':unittest.main()
