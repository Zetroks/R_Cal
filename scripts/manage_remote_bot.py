"""Inspect/bootstrap the bot as its service user; never emit environment or raw errors."""
import argparse
import json
import logging
import shlex

from .server_access import connect

REMOTE = r'''
import json, os, pwd, subprocess, sys
root = '/opt/r_cal'
owner = 'botuser'
uid = pwd.getpwnam(owner).pw_uid
prefix = ['runuser', '-u', owner, '--'] if os.geteuid() == 0 else []
env = os.environ.copy()
env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'
env['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path=/run/user/{uid}/bus'
def run(args, timeout=60):
    p = subprocess.run(prefix + args, cwd=root, env=env, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('Remote step failed: ' + args[0] + ' (code ' + str(p.returncode) + ')')
    return p.stdout.strip()
try:
    status = run(['git', 'status', '--porcelain', '--untracked-files=no'])
    result = {'project': root, 'service_user': owner, 'tracked_changes': bool(status),
              'commit': run(['git', 'rev-parse', '--short', 'HEAD'])}
    if sys.argv[1] == 'install':
        if status:
            raise RuntimeError('Bot checkout has tracked changes; stopping')
        run(['git', 'pull', '--ff-only'])
        python = root + '/.venv/bin/python'
        code = 'from CalendarBot.self_update import prepare_update; import sys; result=prepare_update(); sys.exit(result[0])'
        run([python, '-c', code], timeout=900)
        result['commit'] = run(['git', 'rev-parse', '--short', 'HEAD'])
        run(['systemctl', '--user', 'restart', 'calendar-bot'])
        import time
        time.sleep(3)
    result['state'] = run(['systemctl', '--user', 'is-active', 'calendar-bot'])
    print(json.dumps(result))
except Exception as exc:
    # Our own error text identifies only a step; never output subprocess stderr.
    text = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
    print(json.dumps({'error': text}))
    sys.exit(1)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'install'))
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        with connect('bot_server') as client:
            stdin, stdout, stderr = client.exec_command('python3 -c ' + shlex.quote(REMOTE) + ' ' + args.action,
                                                       timeout=1000)
            stdin.close()
            raw = stdout.read(1_000_000)
            code = stdout.channel.recv_exit_status()
        print(json.dumps(json.loads(raw), ensure_ascii=False))
        return code
    except Exception:
        print('Remote bot operation failed; connection details suppressed.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
