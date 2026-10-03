"""Ship only explicitly listed runtime files, never private local state."""
import ast
from pathlib import Path
import shutil
from hatchling.builders.hooks.plugin.interface import BuildHookInterface

class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        root = Path(self.root)
        tree = ast.parse((root / 'onboard.py').read_text())
        files = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'FILES' for t in n.targets))
        target = root / 'src/llmcom/_stack'
        if target.exists(): shutil.rmtree(target)
        target.mkdir(parents=True)
        for name in files:
            shutil.copy2(root / name, target / name)
        for folder, pattern in [('references', '*.md'), ('flows', '*.ts')]:
            for path in (root / folder).glob(pattern):
                destination = target / folder / path.name
                destination.parent.mkdir(exist_ok=True)
                shutil.copy2(path, destination)
        build_data['force_include'][str(target)] = 'llmcom/_stack'
