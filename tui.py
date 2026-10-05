"""Small dependency-free terminal interface to discovery and invitations."""
import json
from discovery import discover, invitation, check_connection


def run(config_dir, read=input, write=print):
    info = discover(config_dir)
    records = info['conversations']
    if not records:
        write('No joined conversations found. Run llmcom setup --help, then join from your warmed chat.')
        return
    write('LLMCom — select the conversation you want to share')
    for i, record in enumerate(records, 1):
        write(f"{i}. {record['name']} ({record['vendor']}) — {', '.join(record.get('channels') or [])}")
    choice = read('Conversation number (q to quit): ').strip()
    if choice.lower() == 'q': return
    if not choice.isdigit() or not 1 <= int(choice) <= len(records):
        raise ValueError('Choose one of the listed conversation numbers.')
    selected = dict(info, conversations=[records[int(choice)-1]])
    relay = info['relay']
    write(f"Chat computer: {info['conversationComputer']}\nRelay SSH: {relay['hostname']}:{relay['sshPort']}\nWorkspace: {info['workspace']}")
    write('1. Show connection details\n2. Print an invitation\n3. Check SSH and relay connection\nq. Quit')
    action = read('Action: ').strip()
    if action == 'q': return
    if action == '1':
        write(json.dumps(selected, indent=2)); return
    if action == '3':
        write(json.dumps(check_connection(selected), indent=2)); return
    if action != '2': raise ValueError('Choose a listed action.')
    channels = selected['conversations'][0].get('channels') or []
    if not channels: raise ValueError('This conversation has no recorded channels.')
    for i, channel in enumerate(channels, 1): write(f'{i}. {channel}')
    choice = read('Channel number: ').strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(channels):
        raise ValueError('Choose one of the listed channel numbers.')
    write(invitation(selected, channels[int(choice)-1]))
