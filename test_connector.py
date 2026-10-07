import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import connector

class ConnectorTests(unittest.TestCase):
    def test_setup_credentials_stay_private_and_escaped(self):
        with tempfile.TemporaryDirectory() as d:
            config={'gateway':'https://example.com','id':'a'*32,'claudeKey':'b'*43,'channels':['bridge']}
            file=connector.setup_page(Path(d),config)
            self.assertEqual(file.stat().st_mode&0o777,0o600)
            self.assertIn('type="password"',file.read_text())
            self.assertIn('Bearer '+config['claudeKey'],file.read_text())
    def test_enable_rejects_untrusted_gateway_before_any_setup(self):
        with tempfile.TemporaryDirectory() as d, patch('pathlib.Path.home',return_value=Path(d)):
            for url in ['http://example.com','https://user:password@example.com','https://example.com/path','https://example.com?token=x']:
                with self.assertRaises(ValueError):connector.main(['enable','--channel','bridge','--gateway',url,'--no-open'])
    def test_status_unconfigured_is_safe(self):
        with tempfile.TemporaryDirectory() as d, patch('pathlib.Path.home',return_value=Path(d)),patch('builtins.print') as output:
            connector.main(['status'])
            self.assertEqual(json.loads(output.call_args[0][0]),{'enabled':False})
    def test_repeated_enable_restarts_existing_service_without_bootout_race(self):
        with tempfile.TemporaryDirectory() as d, patch('pathlib.Path.home',return_value=Path(d)),patch('connector.time.sleep'),patch('connector.subprocess.run') as run:
            run.return_value.returncode=0
            folder=Path(d)/'connector';folder.mkdir()
            connector.launch(folder,folder/'config.json')
            run.reset_mock()
            connector.launch(folder,folder/'config.json')
            commands=[c.args[0] for c in run.call_args_list]
            self.assertTrue(any('kickstart' in c for c in commands))
            self.assertFalse(any('bootout' in c or 'bootstrap' in c for c in commands))
    def test_disable_stops_local_access_even_if_gateway_unreachable(self):
        with tempfile.TemporaryDirectory() as d, patch('pathlib.Path.home',return_value=Path(d)),patch('connector.subprocess.run') as run,patch('connector.api',side_effect=ValueError('offline')):
            folder=Path(d)/'.config/agentworkforce/connector';folder.mkdir(parents=True)
            file=folder/'config.json';file.write_text(json.dumps({'id':'x','gateway':'https://example.com','deviceKey':'test'}))
            with self.assertRaises(ValueError):connector.main(['disable'])
            self.assertTrue(any('bootout' in c.args[0] for c in run.call_args_list))
            self.assertTrue(file.exists())

    def test_phone_setup_adds_room_preserves_existing_and_reuses_registration(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            home=Path(d); folder=home/'.config/agentworkforce/connector';folder.mkdir(parents=True)
            stack=home/'stack';(stack/'node_modules/ws').mkdir(parents=True);(stack/'node_modules/ws/package.json').write_text('{}')
            (folder.parent/'stack.json').write_text('{}')
            (stack/'llmcom.py').write_text('import sys, argparse\ndef main():\n    pass # preserve-custom-extension\n')
            config={'id':'a'*32,'gateway':'https://example.com','deviceKey':'d'*43,'claudeKey':'c'*43,'channels':['bridge']}
            (folder/'config.json').write_text(json.dumps(config))
            with patch('pathlib.Path.home',return_value=home),patch('onboard.STACK',stack),patch('onboard.install_node'),patch('shutil.copy2'),patch('connector.launch'),patch('connector.api',return_value={'connected':True}) as api,patch('desktop_mcp.runtime',return_value=[{'name':'bridge'}]) as runtime,patch('builtins.print'):
                connector.main(['enable','--channel','myphone','--add-channels','--no-open'])
            saved=json.loads((folder/'config.json').read_text())
            self.assertIn("sys.argv[1]=='phone'",(stack/'llmcom.py').read_text())
            self.assertIn('preserve-custom-extension',(stack/'llmcom.py').read_text())
            self.assertEqual(saved['channels'],['bridge','myphone'])
            self.assertEqual(saved['id'],config['id'])
            self.assertEqual(saved['setupChannel'],'myphone')
            runtime.assert_any_call('channel-create','myphone')
            self.assertFalse(any(c.kwargs.get('method')=='POST' for c in api.call_args_list))
            page=(folder/'claude-setup.html').read_text()
            self.assertIn('join myphone as my-phone',page)
            self.assertIn('https://llmcom-connector.fly.dev/setup',page)

    def test_openai_page_uses_shared_url_private_pairing_and_selected_room(self):
        with tempfile.TemporaryDirectory() as d:
            page=connector.openai_setup_page(Path(d),{'serverUrl':'https://example.com/mcp','pairingCode':'private-code'}, {'channels':['bridge','myphone'],'setupChannel':'myphone'})
            text=page.read_text()
            self.assertEqual(page.stat().st_mode&0o777,0o600)
            self.assertIn('Server URL:',text)
            self.assertIn('value="https://example.com/mcp"',text)
            self.assertIn('type="password"',text)
            self.assertIn('Join myphone as phone-openai',text)
            self.assertNotIn('Bearer',text)

    def test_existing_phone_command_upgrades_without_losing_custom_commands(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);folder=home/'.config/agentworkforce/connector';folder.mkdir(parents=True)
            stack=home/'stack';(stack/'node_modules/ws').mkdir(parents=True);(stack/'node_modules/ws/package.json').write_text('{}')
            (folder.parent/'stack.json').write_text('{}')
            old="import sys, argparse\ndef main():\n    if len(sys.argv)>1 and sys.argv[1]=='phone':\n        pass # old-phone\n    if len(sys.argv)>1 and sys.argv[1]=='connector':\n        pass\n    pass # custom-command\n"
            (stack/'llmcom.py').write_text(old)
            config={'id':'a'*32,'gateway':'https://example.com','deviceKey':'d'*43,'claudeKey':'c'*43,'channels':['myphone']}
            (folder/'config.json').write_text(json.dumps(config))
            with patch('pathlib.Path.home',return_value=home),patch('onboard.STACK',stack),patch('onboard.install_node'),patch('shutil.copy2'),patch('connector.launch'),patch('connector.api',return_value={'connected':True}),patch('desktop_mcp.runtime',return_value=[{'name':'myphone'}]),patch('builtins.print'):
                for _ in range(2):connector.main(['enable','--channel','myphone','--no-open'])
            updated=(stack/'llmcom.py').read_text()
            self.assertIn("phone.add_argument('--client'",updated)
            self.assertEqual(updated.count("sys.argv[1]=='phone'"),1)
            self.assertIn('custom-command',updated)
            self.assertNotIn('old-phone',updated)
