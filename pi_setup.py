"""Install only the LLMCom extension loader in a selected harness agent directory."""
import json
import shutil
from pathlib import Path

def install_extension(harness, agent_dir=None, stack=None):
    if harness not in ('pi', 'omo'):
        raise ValueError('Harness must be pi or omo')
    root = Path(agent_dir).expanduser().resolve() if agent_dir else Path.home() / ('.pi' if harness == 'pi' else '.omo') / 'agent'
    stack = Path(stack).resolve() if stack else Path(__file__).resolve().parent
    target = root / 'extensions' / 'llmcom.ts'
    content = 'import extension from ' + json.dumps(str(stack / 'pi-extension.ts')) + ';\nexport default function(pi) { extension(pi, { vendor: ' + json.dumps(harness) + ' }); }\n'
    if target.exists() and target.read_text() != content:
        backup = target.with_suffix('.ts.previous')
        if backup.exists():
            raise ValueError('Existing extension and backup differ; inspect before replacing: ' + str(target))
        backup.write_bytes(target.read_bytes())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    skill_source = stack / 'LLMCOM-SKILL.md'
    if skill_source.exists():
        skill = root / 'skills/llmcom'
        skill.mkdir(parents=True, exist_ok=True)
        card = skill / 'SKILL.md'
        if card.exists() and 'EXP31 LLMCom skill' not in card.read_text():
            raise ValueError('Preserving unrelated llmcom skill: ' + str(card))
        shutil.copy2(skill_source, card)
        if (stack / 'references').exists():
            shutil.copytree(stack / 'references', skill / 'references', dirs_exist_ok=True)
    return {'installed': str(target), 'harness': harness, 'next': 'Reload extensions or open a new conversation; run llmcom join CHANNEL through its own shell tool. Existing conversations and listeners were not restarted.'}
