import plistlib
from pathlib import Path
import tempfile
import unittest
from connection import service_mode

class ModeTests(unittest.TestCase):
    def test_names_do_not_choose_server(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(service_mode(directory,{'role':'bertha'}),'client')
            file=Path(directory)/'Library/LaunchAgents/com.exp31.agentworkforce.server.plist'
            file.parent.mkdir(parents=True)
            file.write_bytes(plistlib.dumps({'ProgramArguments':['node','/some/runtime/server.mjs']}))
            self.assertEqual(service_mode(directory,{'role':'any-host'}),'server')
            self.assertEqual(service_mode(directory,{'serviceMode':'client'}),'client')
            with self.assertRaises(ValueError):service_mode(directory,{'serviceMode':'typo'})


class TunnelTests(unittest.TestCase):
    def test_installer_uses_distinct_local_and_remote_ports(self):
        import os
        import subprocess
        import json
        with tempfile.TemporaryDirectory() as directory:
            environment=dict(os.environ,HOME=directory)
            script=Path(__file__).with_name('install-tools.py')
            subprocess.run(['/usr/bin/python3',str(script),'arbitrary-host','--ssh-host','relay.example','--port','9999','--relay-port','8877','--workspace','independent-team'],env=environment,check=True,capture_output=True)
            home=Path(directory)
            config=json.loads((home/'.config/agentworkforce/stack.json').read_text())
            self.assertEqual(config['relayPort'],8877)
            self.assertEqual(config['serviceMode'],'client')
            service=plistlib.loads((home/'Library/LaunchAgents/com.exp31.agentworkforce.tunnel.plist').read_bytes())
            self.assertIn('127.0.0.1:9999:127.0.0.1:8877',service['ProgramArguments'])

if __name__=='__main__': unittest.main()

class RouteTests(unittest.TestCase):
    def test_read_saved_tunnel_without_other_ssh_arguments(self):
        from connection import tunnel_route
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'Library/LaunchAgents/com.exp31.agentworkforce.tunnel.plist'
            file.parent.mkdir(parents=True)
            file.write_bytes(plistlib.dumps({'ProgramArguments':['/usr/bin/ssh','-i','/private/key','-L','127.0.0.1:9999:127.0.0.1:8899','relay']}))
            result=tunnel_route(directory,{'sshHost':'relay'})
            self.assertEqual(result['remotePort'],8899)
            self.assertNotIn('/private/key',str(result))
            self.assertIsNone(tunnel_route(directory,{'sshHost':'different'}))
