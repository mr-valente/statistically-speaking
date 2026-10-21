"""Hosted behavior against a stand-in for the shared account service's private API."""
import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.support import PREFIX, ServerTest, free_port

SECRET = "deployment-fixture-" + "x" * 40
COOKIE = "__Host-athenaeum_account"
APP = "statistically-speaking"
USERS = {
    "alice-token": {"id": "alice", "kind": "google", "name": "Alice", "email": "alice@example.test"},
    "bob-token": {"id": "bob", "kind": "google", "name": "Bob", "email": "bob@example.test"},
    "guest-token": {"id": "guest-1", "kind": "guest", "name": "Gus", "email": None},
}
X = "/x/full-monty"


class Accounts:
    """The two private endpoints an app calls, with the app-key check the real service makes."""

    def __init__(self):
        self.port, self.records, self.users = free_port(), [], dict(USERS)
        key = hmac.new(SECRET.encode(), f"athenaeum-account-api-v1:{APP}".encode(), hashlib.sha256).hexdigest()
        service = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.headers["X-Athenaeum-App"] != APP or self.headers["Authorization"] != "Bearer " + key:
                    return self.reply(401, {})
                if self.path == "/internal/identity":
                    return self.reply(200, {"user": service.users.get(payload["token"])})
                service.records.append(payload)
                self.reply(200, {"status": "recorded"})

            def reply(self, status, data):
                body = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class HostedTests(ServerTest):
    def setUp(self):
        self.accounts = Accounts()
        self.addCleanup(self.accounts.close)
        self.extra_env = {"ACCOUNT_SERVICE_URL": f"http://127.0.0.1:{self.accounts.port}", "ATHENAEUM_APP_ID": APP}
        super().setUp()

    def signed_in(self, token):
        return self.browser({COOKIE: token})

    def act(self, browser, session_id, action, **extra):
        return browser.json("POST", f"{X}/s/{session_id}/act", payload={"action": action, **extra})

    def test_shared_sign_in_and_finalized_results(self):
        # Anonymous entry points go to the shared sign-in with the return path kept.
        status, headers, _ = self.browser().get("/join?code=ABC123")
        self.assertEqual((status, headers["location"]), (303, "/account/login?return_to=%2Fstatistically-speaking%2Fjoin%3Fcode%3DABC123"))
        status, headers, _ = self.browser().get("/admin")
        self.assertEqual((status, headers["location"]), (303, "/account/login?return_to=%2Fstatistically-speaking%2Fadmin"))
        self.assertIn("Statistically Speaking", self.browser().get("/")[2])  # the landing page stays public

        # A Google teacher needs no name form; a Google student joins by code alone.
        teacher = self.signed_in("alice-token")
        status, headers, _ = teacher.get("/admin")
        self.assertEqual((status, headers["location"]), (303, f"https://valentemath.com{PREFIX}/admin/dashboard"))
        status, headers, _ = teacher.post(f"{X}/create", form={"label": ""})
        session_id = headers["location"].rsplit("/", 1)[-1]
        code = __import__("re").search(r'class="code code-large">([A-Z0-9]{6})<', teacher.get(f"{X}/t/{session_id}")[2]).group(1)
        bob = self.signed_in("bob-token")
        self.assertEqual(bob.post("/session/join", form={"join_code": code})[0], 303)
        gus = self.signed_in("guest-token")
        self.assertEqual(gus.post("/session/join", form={"join_code": code})[0], 303)
        status, body = bob.json("GET", f"{X}/s/{session_id}/state")
        self.assertEqual(body["you"]["name"], "Bob")

        # Bob's seat follows his account to another browser; the game state comes with it.
        teacher.post(f"{X}/t/{session_id}/pairs", form={"mode": "newcomers"})
        other = self.signed_in("bob-token")
        status, body = other.json("GET", f"{X}/s/{session_id}/state")
        self.assertEqual((status, body["you"]["name"], body["table"]["index"]), (200, "Bob", 1))

        # Play one game through; only the Google-linked contestant's revealed game is published.
        tables = teacher.json("GET", f"{X}/t/{session_id}/state")[1]["tables"][0]
        host, contestant = (bob, gus) if tables["first"] == "Bob" else (gus, bob)
        self.act(host, session_id, "hide", door=1)
        self.act(contestant, session_id, "pick", door=2)
        self.act(host, session_id, "open", door=3)
        g = self.act(contestant, session_id, "decide", decision="switch")[1]["game"]
        self.assertTrue(g["won"])
        for _ in range(100):
            if self.accounts.records:
                break
            time.sleep(0.2)
        published = [r for r in self.accounts.records if r["activity"] == "full_monty"]
        if contestant is bob:
            self.assertEqual(len(published), 1)
            self.assertEqual((published[0]["user_id"], published[0]["metrics"]), ("bob", {"decision": "switch", "won": True, "first_pick_right": False}))
            self.assertEqual(published[0]["context"]["classroom_id"], session_id)
        else:
            self.assertEqual(published, [])  # a guest's result is not published
        # The app account page is served when hosted.
        status, _, page = bob.get("/account")
        self.assertEqual(status, 200)
        self.assertIn("Bob", page)


if __name__ == "__main__":
    unittest.main()
