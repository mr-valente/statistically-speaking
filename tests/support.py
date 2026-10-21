"""Test support: an in-process app on a disposable database, and a real server under the hosted prefix."""
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlencode

_temp = tempfile.TemporaryDirectory()
# The in-process app always uses its own database, whatever the surrounding environment names.
os.environ["DB_PATH"] = str(Path(_temp.name) / "app.db")
os.environ["SESSION_SECRET"] = "in-process-fixture-" + "x" * 40
for _name in ("SESSION_SECRET_FILE", "ROOT_PATH", "APP_ENV", "ACCOUNT_SERVICE_URL", "ATHENAEUM_APP_ID"):
    os.environ.pop(_name, None)

PREFIX = "/statistically-speaking"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Browser:
    """One browser's cookies, talking to the app the way the proxy does."""

    def __init__(self, port, cookies=None):
        self.port, self.cookies, self.csrf = port, dict(cookies or {}), ""

    def request(self, method, path, form=None, payload=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        sent = {"Host": "valentemath.com", "X-Forwarded-Proto": "https", **(headers or {})}
        if self.cookies:
            sent["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        body = None
        if form is not None:
            sent["Content-Type"] = "application/x-www-form-urlencoded"
            body = urlencode(form, doseq=True)
        elif payload is not None:
            sent["Content-Type"] = "application/json"
            body = json.dumps(payload)
        conn.request(method, path, body=body, headers=sent)
        response = conn.getresponse()
        text = response.read().decode()
        self.raw_cookies = [v for k, v in response.getheaders() if k.lower() == "set-cookie"]
        for raw in self.raw_cookies:
            name, _, value = raw.split(";", 1)[0].partition("=")
            self.cookies[name] = value
        conn.close()
        token = re.search(r'data-csrf="([^"]+)"', text) or re.search(r'name="csrf_token" value="([^"]+)"', text)
        if token and response.status == 200 and "account_csrf" not in text:
            self.csrf = token.group(1)
        return response.status, dict((k.lower(), v) for k, v in response.getheaders()), text

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def json(self, method, path, payload=None):
        status, _, text = self.request(method, path, payload=payload)
        return status, json.loads(text) if text.startswith(("{", "[")) else text

    def teacher(self, name="Ms. Monty"):
        status, _, _ = self.post("/admin/login", form={"teacher_name": name})
        assert status == 303, status
        return self

    def student(self, code, name):
        status, _, _ = self.post("/session/join", form={"join_code": code, "player_name": name})
        assert status == 303, status
        return self


class ServerTest(unittest.TestCase):
    """A real server under /statistically-speaking with a disposable database."""
    extra_env = {}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.port = free_port()
        self.env = dict(os.environ, APP_ENV="production", ROOT_PATH=PREFIX,
                        SESSION_SECRET="deployment-fixture-" + "x" * 40,
                        DB_PATH=str(self.data / "app.db"), PORT=str(self.port),
                        FORWARDED_ALLOW_IPS="127.0.0.1", **self.extra_env)
        self.env.pop("SESSION_SECRET_FILE", None)
        self.start()
        self.addCleanup(self.stop)

    def start(self):
        with open(self.data / "server.log", "a") as log:
            self.process = subprocess.Popen([sys.executable, "-m", "app"], env=self.env, stdout=log, stderr=log,
                                            cwd=Path(__file__).resolve().parents[1])
        for _ in range(200):
            if self.process.poll() is not None:
                self.fail("Server exited during startup: " + (self.data / "server.log").read_text()[-2000:])
            try:
                if Browser(self.port).get("/_health")[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.05)
        self.fail("Server did not become ready")

    def stop(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def browser(self, cookies=None):
        return Browser(self.port, cookies)
