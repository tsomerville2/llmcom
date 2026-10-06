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
