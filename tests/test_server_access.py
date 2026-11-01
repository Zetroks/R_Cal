import json
import sqlite3
import subprocess
import sys

import pytest
from scripts.server_access import read_credentials
from scripts.inspect_remote_schema import REMOTE_SCRIPT


def test_credentials_preserve_password_without_exposing_repr(tmp_path):
    path = tmp_path / 'fixture.json'
    path.write_text(json.dumps({'main_server': {'ip': ' example.test ', 'login': ' user ',
                                               'password': ' synthetic password '}}), encoding='utf-8')
    credentials = read_credentials('main_server', path)
    assert credentials.ip == 'example.test'
    assert credentials.login == 'user'
    assert credentials.password == ' synthetic password '
    assert 'password' not in repr(credentials)
    assert 'example.test' not in repr(credentials)


@pytest.mark.parametrize('content', ['{"sensitive fake secret":', '{}', '{"main_server": {}}'])
def test_invalid_credentials_errors_are_sanitized(tmp_path, content):
    path = tmp_path / 'fixture.json'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(RuntimeError) as error:
        read_credentials('main_server', path)
    assert str(error.value) == 'Credentials file is missing, invalid, or incomplete'


def test_schema_inspection_does_not_output_data_or_change_database(tmp_path):
    path = tmp_path / 'fixture.db'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, password TEXT)')
        con.execute("INSERT INTO users VALUES (1, 'synthetic-sensitive-value')")
    before = path.read_bytes()
    result = subprocess.run([sys.executable, '-c', REMOTE_SCRIPT, str(path)],
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report['integrity'] == 'ok'
    assert [column['name'] for column in report['tables']['users']] == ['id', 'password']
    assert 'synthetic-sensitive-value' not in result.stdout
    assert path.read_bytes() == before
