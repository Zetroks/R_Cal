"""Read SQLite schema over SSH; output contains no rows or connection credentials.

Usage: python scripts/inspect_remote_schema.py --database /path/to/calendar.db
The SSH host must already be trusted in the user's known_hosts.
"""
import argparse
import json
import logging
import shlex
import sys

try:
    from .server_access import connect
except ImportError:
    from server_access import connect


REMOTE_SCRIPT = '''import json, sqlite3, sys
from pathlib import Path
path = Path(sys.argv[1]).resolve()
con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
con.execute('PRAGMA query_only=ON')
con.execute('BEGIN')
names = sorted(r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'"))
tables = {}
for name in names:
    quoted = name.replace('"', '""')
    tables[name] = [dict(zip(('cid','name','type','notnull','default','pk'), row))
                   for row in con.execute('PRAGMA table_info("' + quoted + '")')]
revisions = [r[0] for r in con.execute('SELECT version_num FROM alembic_version')] if 'alembic_version' in names else []
print(json.dumps({'tables': tables, 'alembic_revision': revisions,
                  'row_counts': {name: con.execute('SELECT count(*) FROM "' + name.replace('"','""') + '"').fetchone()[0]
                                 for name in names},
                  'integrity': con.execute('PRAGMA quick_check').fetchone()[0]}))
con.rollback()
con.close()
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', choices=('main_server', 'bot_server'), default='main_server')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--database', required=True, help='Absolute path on the remote Linux server')
    parser.add_argument('--summary', action='store_true', help='Compare with local models, without printing full schema')
    args = parser.parse_args(argv)
    # Paramiko errors/log records can include addresses. Do not emit them.
    logging.getLogger('paramiko').disabled = True
    logging.getLogger('paramiko.transport').disabled = True
    try:
        with connect(args.server, port=args.port) as client:
            command = 'python3 -c ' + shlex.quote(REMOTE_SCRIPT) + ' ' + shlex.quote(args.database)
            stdin, stdout, stderr = client.exec_command(command, timeout=45)
            stdin.close()
            raw = stdout.read(2_000_000)
            if stdout.channel.recv_exit_status() != 0:
                raise RuntimeError()
            result = json.loads(raw)
        if args.summary:
            from CalendarServer.database_models import Base
            actual, expected = set(result['tables']), set(Base.metadata.tables)
            missing_columns = {}
            for name in sorted(actual & expected):
                missing = set(Base.metadata.tables[name].columns.keys()) - {col['name'] for col in result['tables'][name]}
                if missing:
                    missing_columns[name] = sorted(missing)
            result = {'missing_tables': sorted(expected - actual), 'extra_tables': sorted(actual - expected),
                      'missing_columns': missing_columns, 'row_counts': result['row_counts'],
                      'alembic_revision': result['alembic_revision'], 'integrity': result['integrity']}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        print('Schema inspection failed. Check credentials, known_hosts, port, database path and read permissions.',
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
