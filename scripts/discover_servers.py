"""Read service paths and locate project databases without emitting credentials."""
import json
import logging
import shlex
import sys
import hashlib
import base64
import socket

from .server_access import connect, read_credentials

REMOTE_SCRIPT = r'''
import json, os, re, subprocess, pwd
from pathlib import Path

def run(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=12)
        return p.stdout if p.returncode == 0 else ''
    except Exception:
        return ''

def relevant(text):
    return any(term in text.lower() for term in ('calendar', 'r_cal', 'calbot', 'roksi'))

services = []
roots = set()
for scope in ([], ['--user']):
    names = {'calendar-server.service', 'calendar-web.service', 'calendar-bot.service'}
    for action in ('list-units', 'list-unit-files'):
        listing = run(['systemctl', *scope, action, '--type=service', '--no-legend', '--no-pager'])
        for line in listing.splitlines():
            bits = line.split()
            if bits and relevant(bits[0]):
                names.add(bits[0])
    for name in sorted(names):
        raw = run(['systemctl', *scope, 'show', name, '--no-pager',
                   '--property=LoadState,ActiveState,FragmentPath,WorkingDirectory,ExecStart'])
        props = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
        if props.get('LoadState') != 'loaded':
            continue
        wd = props.get('WorkingDirectory', '')
        if wd.startswith('/'):
            roots.add(wd)
        executable = re.search(r'path=([^ ;]+)', props.get('ExecStart', ''))
        services.append({'scope': 'user' if scope else 'system', 'unit': name,
                         'state': props.get('ActiveState'), 'file': props.get('FragmentPath'),
                         'working_directory': wd,
                         'executable': executable.group(1) if executable else None})

# User units belonging to other users need not be visible to this SSH session.
# Parse only path directives; never return Environment or arbitrary ExecStart args.
unit_dirs = [Path('/etc/systemd/system'), Path('/etc/systemd/user'),
             Path('/root/.config/systemd/user')]
try:
    unit_dirs.extend(p / '.config/systemd/user' for p in Path('/home').iterdir() if p.is_dir())
except OSError:
    pass
files = []
for directory in unit_dirs:
    try:
        candidates = list(directory.glob('*.service'))
    except OSError:
        continue
    for path in candidates:
        try:
            content = path.read_text()
        except (OSError, UnicodeError):
            continue
        if not relevant(path.name) and not any(t in content for t in ('CalendarServer', 'CalendarBot', 'CalendarWeb')):
            continue
        wd = re.search(r'^WorkingDirectory=(.+)$', content, re.M)
        wd = wd.group(1).strip().strip('"') if wd else None
        if wd and wd.startswith('/'):
            roots.add(wd)
        unit = {'file': str(path), 'working_directory': wd}
        if os.geteuid() == 0 and '.config/systemd/user' in str(path):
            owner = path.parts[2] if str(path).startswith('/home/') else 'root'
            try:
                uid = pwd.getpwnam(owner).pw_uid
                raw = run(['runuser', '-u', owner, '--', 'env', f'XDG_RUNTIME_DIR=/run/user/{uid}',
                           f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus',
                           'systemctl', '--user', 'show', path.name, '--no-pager',
                           '--property=LoadState,ActiveState,SubState,WorkingDirectory'])
                props = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
                unit['runtime_state'] = props.get('ActiveState', 'unavailable')
                unit['runtime_substate'] = props.get('SubState', 'unavailable')
                unit['runtime_working_directory'] = props.get('WorkingDirectory')
            except (KeyError, OSError):
                pass
        files.append(unit)

databases = []
for root in sorted(roots):
    try:
        for parent, dirs, names in os.walk(root, followlinks=False):
            depth = len(Path(parent).relative_to(root).parts)
            dirs[:] = [d for d in dirs if d not in ('.git', '.venv', 'venv', 'node_modules', '__pycache__')]
            if depth >= 4:
                dirs[:] = []
            for name in names:
                if name.endswith(('.db', '.sqlite', '.sqlite3')):
                    path = Path(parent) / name
                    databases.append({'path': str(path), 'bytes': path.stat().st_size})
    except OSError:
        pass
print(json.dumps({'services': services, 'unit_files': files, 'databases': databases}))
'''


def main():
    logging.disable(logging.CRITICAL)
    import paramiko
    failed = False
    servers = ('main_server', 'bot_server')
    if '--server' in sys.argv:
        selected = sys.argv[sys.argv.index('--server') + 1]
        if selected not in servers:
            return 1
        servers = (selected,)
    for server in servers:
        try:
            if '--host-keys' in sys.argv:
                credentials = read_credentials(server)
                with socket.create_connection((credentials.ip, 22), timeout=15) as sock:
                    transport = paramiko.Transport(sock)
                    try:
                        transport.start_client(timeout=15)
                        key = transport.get_remote_server_key()
                        digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
                        print(json.dumps({'server': server, 'key_type': key.get_name(),
                                          'fingerprint': 'SHA256:' + digest}), flush=True)
                    finally:
                        transport.close()
                continue
            with connect(server) as client:
                stdin, stdout, stderr = client.exec_command('python3 -c ' + shlex.quote(REMOTE_SCRIPT), timeout=60)
                stdin.close()
                raw = stdout.read(2_000_000)
                if stdout.channel.recv_exit_status() != 0:
                    raise RuntimeError('remote_discovery_failed')
                result = json.loads(raw)
            print(json.dumps({'server': server, **result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            failed = True
            if isinstance(exc, paramiko.AuthenticationException):
                reason = 'authentication_failed'
            elif isinstance(exc, paramiko.BadHostKeyException):
                reason = 'host_key_mismatch'
            elif isinstance(exc, paramiko.SSHException):
                reason = 'host_key_not_trusted' if 'known_hosts' in str(exc) else 'ssh_failed'
            elif isinstance(exc, OSError):
                reason = 'network_or_filesystem_error'
            else:
                reason = 'credentials_or_remote_discovery_error'
            print(json.dumps({'server': server, 'error': reason}), flush=True)
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
