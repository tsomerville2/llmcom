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

if __name__ == '__main__':unittest.main()
