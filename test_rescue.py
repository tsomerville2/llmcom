"""Offline artifact integrity and safe-extraction checks, without model messages."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('rescue_test',SOURCE/'rescue.py')
rescue=importlib.util.module_from_spec(spec);spec.loader.exec_module(rescue)

class RescueTests(unittest.TestCase):
    def archive(self,root,members):
        path=root/'fixture.tar.xz'
        with tarfile.open(path,'w:xz') as t:
            for name,value,target in members:
                info=tarfile.TarInfo(name)
                if target is not None:info.type=tarfile.SYMTYPE;info.linkname=target;t.addfile(info)
                else:info.size=len(value);info.mode=0o755;t.addfile(info,io.BytesIO(value))
        return path

    def test_safe_npm_bin_link_and_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'out';out.mkdir()
            archive=self.archive(root,[('node/bin/node',b'fixture',None),('node_modules/pkg/bin/tool.js',b'fixture',None),('node_modules/.bin/tool',b'','../pkg/bin/tool.js')])
            rescue.safe_extract(archive,out)
            self.assertEqual((out/'node_modules/.bin/tool').read_bytes(),b'fixture')
            self.assertEqual((out/'node/bin/node').stat().st_mode & 0o777,0o755)

    def test_traversal_absolute_and_link_ancestors_are_rejected_before_writes(self):
        cases=[[('../escape',b'x',None)],[('/absolute',b'x',None)],
               [('node_modules/pkg',b'','../../escape')],
               [('node_modules/link',b'','pkg'),('node_modules/link/file',b'x',None)]]
        for members in cases:
            with self.subTest(members=members),tempfile.TemporaryDirectory() as d:
                root=Path(d);out=root/'out';out.mkdir()
                with self.assertRaises(ValueError):rescue.safe_extract(self.archive(root,members),out)
                self.assertEqual(list(out.iterdir()),[])

    def test_artifact_corruption_and_wrong_architecture_fail_without_runtime_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir();(source/'rescue').mkdir()
            lock=source/'package-lock.json';lock.write_text('{}')
            part=source/'rescue/part';part.write_bytes(b'fixture')
            data={'format':1,'nodeVersion':'22.23.3','nodeAbi':'127','lockSha256':rescue.sha(lock),'packages':1,'artifactFiles':{},
                  'platforms':{'darwin-arm64':{'sha256':rescue.sha(part),'parts':[{'file':'part','size':7,'sha256':rescue.sha(part)}]}}}
            (source/'rescue/manifest.json').write_text(json.dumps(data))
            with patch.object(rescue,'SOURCE',source),patch.object(rescue,'current_platform',return_value='darwin-x64'):
                with self.assertRaisesRegex(ValueError,'supports darwin-arm64'):rescue.install_runtime(root/'runtime')
                self.assertFalse((root/'runtime').exists())
            part.write_bytes(b'corrupt')
            with patch.object(rescue,'SOURCE',source),patch.object(rescue,'current_platform',return_value='darwin-arm64'):
                with self.assertRaisesRegex(ValueError,'checksum mismatch'):rescue.install_runtime(root/'runtime')
                self.assertFalse((root/'runtime').exists())

if __name__=='__main__':unittest.main()
