import tempfile
import unittest
from pathlib import Path
from pi_setup import install_extension
class ExtensionInstall(unittest.TestCase):
    def test_scoped_install_and_repeat(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root)/'agent'
            result = install_extension('omo', target, Path(root)/'stack')
            loader = Path(result['installed'])
            self.assertIn('"omo"', loader.read_text())
            self.assertEqual(install_extension('omo', target, Path(root)/'stack'),result)
            self.assertFalse(loader.with_suffix('.ts.previous').exists())
    def test_preserves_existing_loader(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'extensions/llmcom.ts';p.parent.mkdir();p.write_text('custom')
            install_extension('pi',root)
            self.assertEqual(p.with_suffix('.ts.previous').read_text(),'custom')
