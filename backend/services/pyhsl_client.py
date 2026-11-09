"""Machine-token access to the local Run Control instance; never follows redirects."""
import http.client
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


class PyHslError(Exception):
    """Invalid discovery, authentication, response or other request failure."""


class PyHslUnavailable(PyHslError):
    """Run Control is absent or its instance could not be verified."""


class PyHslRefusal(PyHslError):
    """Run Control refused the request (HTTP 409)."""


def pyhsl_data_directory():
    override = os.environ.get('ROBOTCONTROL_PYHSL_DATA_DIR', '').strip()
    if override:
        return Path(override)
    base = Path(r'C:\PyHSL')
    try:
        data = json.loads((base / 'current.json').read_text(encoding='utf-8')).get('data')
        if isinstance(data, str) and data.strip():
            return Path(data)
    except (OSError, ValueError, AttributeError):
        pass
    return base / 'data'


class PyHslClient:
    def __init__(self, data_dir=None, *, timeout=2):
        self.data_dir = data_dir
        self.timeout = timeout

    def _request(self, url, path, *, token='', method='GET', data=None, timeout=None):
        connection = http.client.HTTPConnection('127.0.0.1', url.port or 80,
                                                timeout=timeout or self.timeout)
        try:
            headers = {'Authorization': f'Bearer {token}'} if token else {}
            body = json.dumps(data) if data is not None else None
            if body is not None:
                headers['Content-Type'] = 'application/json'
            connection.request(method, '/api/v1' + path, body, headers)
            response = connection.getresponse()
            # Replace the token before decoding or exposing any server text.
            raw = response.read().decode('utf-8')
            if token:
                raw = raw.replace(token, '[redacted]')
            if response.status == 409:
                try:
                    reason = json.loads(raw).get('error', 'Run Control refused the request')
                except (ValueError, AttributeError):
                    reason = raw
                raise PyHslRefusal(str(reason))
            if response.status != 200:
                raise PyHslError(f'Run Control returned HTTP {response.status}')
            return json.loads(raw)
        except TimeoutError:
            # It may be running and busy, so this is not the same as closed.
            raise PyHslError('Run Control did not answer in time') from None
        except (OSError, http.client.HTTPException):
            raise PyHslUnavailable('Run Control is unreachable') from None
        except (ValueError, UnicodeError):
            raise PyHslError('Run Control returned an invalid response') from None
        finally:
            connection.close()

    def _discover(self):
        folder = Path(self.data_dir or pyhsl_data_directory()) / 'sessions' / 'app'
        try:
            instance = json.loads((folder / 'instance.json').read_text(encoding='utf-8'))
            # Only these discovery fields are accessed. Bootstrap is never used.
            url = urlsplit(instance['url'])
            instance_id = instance['instance_id']
            if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost'}
                    or url.username is not None or url.password is not None
                    or url.path not in {'', '/'} or url.query or url.fragment
                    or not isinstance(instance_id, str) or not instance_id or not (0 < (url.port or 80) <= 65535)):
                raise PyHslError('Run Control discovery URL or identity is invalid')
        except OSError:
            raise PyHslUnavailable('Run Control discovery is unavailable') from None
        except (ValueError, KeyError, TypeError):
            raise PyHslError('Run Control discovery is invalid') from None
        health = self._request(url, '/health')
        if not isinstance(health, dict) or health.get('instance_id') != instance_id:
            raise PyHslUnavailable('Run Control instance does not match discovery')
        try:
            token = (folder / 'machine-token').read_text(encoding='utf-8').strip()
        except OSError:
            raise PyHslUnavailable('Run Control machine token is unavailable') from None
        except UnicodeError:
            raise PyHslError('Run Control machine token is invalid') from None
        if not token or not token.isascii() or any(c.isspace() for c in token):
            raise PyHslError('Run Control machine token is invalid')
        return url, token

    def get(self, path, *, timeout=None):
        url, token = self._discover()
        return self._request(url, path, token=token, timeout=timeout)

    def post(self, path, data, *, timeout=60):
        """Validate or start through the machine API; the monitor only reads."""
        url, token = self._discover()
        return self._request(url, path, token=token, method='POST', data=data, timeout=timeout)
