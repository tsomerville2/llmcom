#!/usr/bin/env python3
"""Export only distributable LLMCom source into its standalone repository."""
import argparse
import ast
from pathlib import Path
import shutil

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True)
args = parser.parse_args()
source = Path(__file__).resolve().parent
target = Path(args.output).expanduser().resolve()
if target == source or source in target.parents:
    parser.error('Choose a separate repository directory.')
tree = ast.parse((source / 'onboard.py').read_text())
files = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == 'FILES' for t in n.targets))
files += ['pyproject.toml', 'hatch_build.py', 'LICENSE', 'README.md', 'export-repo.py',
          'test_onboarding.py', 'test_session.mjs', 'test_listener.mjs']
paths = [Path(name) for name in files]
for folder, pattern in [('src/llmcom', '*.py'), ('references', '*.md'), ('flows', '*.ts'), ('.github/workflows', '*.yml')]:
    paths += [p.relative_to(source) for p in (source / folder).glob(pattern)]
for path in paths:
    destination = target / path
    if destination.is_symlink():
        raise SystemExit('Refusing to overwrite a symlink: ' + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / path, destination)
(target / '.gitignore').write_text('dist/\nsrc/llmcom/_stack/\nnode_modules/\n__pycache__/\n*.pyc\n.venv/\n.runtime/\n.agentworkforce/\n.trajectories/\n*.log\n.DS_Store\n')
print('Exported ' + str(len(paths)) + ' distributable source files to ' + str(target))
