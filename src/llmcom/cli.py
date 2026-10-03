"""PyPI console entry points use the same bundled bootstrap as the source kit."""
from pathlib import Path
import runpy
import sys

def _run(name):
    sys.dont_write_bytecode = True
    sys.argv[0] = name
    runpy.run_path(str(Path(__file__).parent / '_stack/awstack'),
                   init_globals={'_LLMCOM_FRIENDLY': name == 'llmcom'}, run_name='__main__')

def main():
    _run('llmcom')

def awstack():
    _run('awstack')
