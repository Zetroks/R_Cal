"""Update the bot checkout as the service user, without root or shell commands."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def prepare_update():
    def run(args, timeout=120):
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f"Step {args[0]} failed (exit {result.returncode}). "
                               + (result.stdout + '\n' + result.stderr)[-1500:])
        return result.stdout.strip()

    try:
        # Check tracked changes; ignored .env and state files are expected.
        if run(['git', 'status', '--porcelain', '--untracked-files=no']):
            return 1, 'Bot checkout has local changes; update stopped.'
        before = run(['git', 'rev-parse', '--short', 'HEAD'])
        run(['git', 'pull', '--ff-only'])
        after = run(['git', 'rev-parse', '--short', 'HEAD'])
        # Always retry installation: a preceding attempt may have pulled code
        # successfully and then failed while installing its dependencies.
        run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements-bot.txt'], timeout=600)
        run([sys.executable, '-m', 'compileall', '-q', 'CalendarBot'])
        run([sys.executable, '-c', 'from CalendarBot.bot import build_app; build_app()'])
        return 0, f'Bot checkout ready: {before} -> {after}'
    except subprocess.TimeoutExpired:
        return 1, 'Bot update timed out; restart cancelled.'
    except Exception as exc:
        return 1, str(exc)


def restart(unit):
    env = os.environ.copy()
    uid = os.getuid()
    env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'
    env['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path=/run/user/{uid}/bus'
    result = subprocess.run(['systemctl', '--user', '--no-block', 'restart', unit],
                            env=env, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError('Could not schedule bot restart: ' + result.stderr[-1000:])
