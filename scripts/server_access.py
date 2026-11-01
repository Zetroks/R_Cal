"""SSH access using ignored creds.json. Never print credentials or raw errors."""
import json
import base64
import hashlib
import hmac
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWN_HOSTS = ROOT / '.tmp_ssh' / 'known_hosts'
# Explicitly approved by the owner on first connection.
APPROVED_HOST_KEYS = {
    'main_server': 'SHA256:+RF+qhkJFim1yl+tbuKjAXtIcKzcNVx9mZ/mQuTVLOo',
    'bot_server': 'SHA256:LtlaxaNS49yVSP3o81+pcVt2OdZgPx+7VDQjFMl7+0s',
}


@dataclass(repr=False)
class Credentials:
    ip: str
    login: str
    password: str


def read_credentials(server, path=None):
    if server not in {"main_server", "bot_server"}:
        raise ValueError("Unknown server alias")
    try:
        data = json.loads(Path(path or ROOT / "creds.json").read_text(encoding="utf-8-sig"))
        entry = data[server]
        values = [entry[key] for key in ("ip", "login", "password")]
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError()
        return Credentials(values[0].strip(), values[1].strip(), values[2])
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError("Credentials file is missing, invalid, or incomplete") from None


@contextmanager
def connect(server, port=22, credentials_path=None):
    import paramiko
    credentials = read_credentials(server, credentials_path)
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    if KNOWN_HOSTS.exists():
        client.load_host_keys(str(KNOWN_HOSTS))

    class ApprovedKeyPolicy(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, ssh_client, hostname, key):
            digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
            if not hmac.compare_digest('SHA256:' + digest, APPROVED_HOST_KEYS[server]):
                raise paramiko.SSHException('Unapproved host key')
            KNOWN_HOSTS.parent.mkdir(exist_ok=True)
            ssh_client.get_host_keys().add(hostname, key.get_name(), key)
            ssh_client.save_host_keys(str(KNOWN_HOSTS))

    client.set_missing_host_key_policy(ApprovedKeyPolicy())
    try:
        client.connect(credentials.ip, port=port, username=credentials.login,
                       password=credentials.password, look_for_keys=False,
                       allow_agent=False, timeout=15, auth_timeout=15, banner_timeout=15)
        yield client
    finally:
        client.close()
