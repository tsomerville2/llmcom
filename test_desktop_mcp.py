import unittest
from desktop_mcp import dispatch

class DesktopTests(unittest.TestCase):
    def test_tools_are_honest_and_no_shell_interpolation(self):
        calls=[]
        call=lambda *args: calls.append(args) or {'sent':True}
        init=dispatch({'method':'initialize'})
        self.assertIn('do not',init['instructions'])
        dispatch({'method':'tools/call','params':{'name':'llmcom_say','arguments':{'channel':'design','text':'$(touch /tmp/never); hi'}}},call)
        self.assertEqual(calls,[('post','design','$(touch /tmp/never); hi')])
        with self.assertRaises(ValueError):
            dispatch({'method':'tools/call','params':{'name':'llmcom_say','arguments':{'channel':'bad;cmd','text':'hi'}}},call)
        self.assertEqual(len(calls),1)

    def test_history_bounds_and_cursor(self):
        calls=[]
        def call(*args):
            calls.append(args)
            return [{'id':'123','text':'reply','agentName':'peer'}]
        def request(args):
            return {'method':'tools/call','params':{'name':'llmcom_history','arguments':args}}
        result=dispatch(request({'channel':'fleethead','before':'123'}),call)
        self.assertIn('reply',result['content'][0]['text'])
        self.assertEqual(calls,[('history','fleethead','20','123')])
        for args in [{'channel':'bad room'},{'channel':'fleethead','limit':101},{'channel':'fleethead','limit':True},{'channel':'fleethead','before':'bad'}]:
            with self.assertRaises(ValueError): dispatch(request(args),call)
        self.assertEqual(len(calls),1)

if __name__ == '__main__':unittest.main()
