"""Deployment regressions using a real server, a URL prefix, and a disposable SQLite database."""
import json
import re
import unittest

from tests.support import PREFIX, ServerTest

X = "/x/full-monty"


class FullMontyTests(ServerTest):
    # ── Fixtures ────────────────────────────────────────────────────────────

    def session(self, teacher, label="P3"):
        status, headers, _ = teacher.post(f"{X}/create", form={"label": label})
        self.assertEqual(status, 303)
        location = headers["location"]
        self.assertTrue(location.startswith(f"https://valentemath.com{PREFIX}{X}/t/"), location)
        session_id = location.rsplit("/", 1)[-1]
        status, _, page = teacher.get(f"{X}/t/{session_id}")
        self.assertEqual(status, 200)
        code = re.search(r'class="code code-large">([A-Z0-9]{6})<', page).group(1)
        return session_id, code

    def state(self, session_id, browser=None):
        status, body = (browser or self.browser()).json("GET", f"{X}/s/{session_id}/state")
        self.assertEqual(status, 200)
        return body

    def act(self, browser, session_id, action, **extra):
        return browser.json("POST", f"{X}/s/{session_id}/act", payload={"action": action, **extra})

    def vote(self, browser, session_id, phase, choice):
        return browser.json("POST", f"{X}/s/{session_id}/vote", payload={"phase": phase, "choice": choice})

    def seat(self, teacher, session_id, mode="newcomers"):
        status, _, _ = teacher.post(f"{X}/t/{session_id}/pairs", form={"mode": mode})
        self.assertEqual(status, 303)

    def tables(self, teacher, session_id):
        status, body = teacher.json("GET", f"{X}/t/{session_id}/state")
        self.assertEqual(status, 200)
        return body

    # ── Tests ───────────────────────────────────────────────────────────────

    def test_health_and_prefixed_pages(self):
        browser = self.browser()
        status, _, body = browser.get("/_health")
        self.assertEqual((status, json.loads(body)), (200, {"status": "ok"}))
        status, headers, page = browser.get("/")
        self.assertEqual(status, 200)
        self.assertIn(f'href="https://valentemath.com{PREFIX}/static/show.css"', page)
        self.assertIn(f'href="https://valentemath.com{PREFIX}/join"', page)
        self.assertNotIn('href="/join"', page)
        self.assertIn("script-src 'self'", headers["content-security-policy"])
        self.assertNotIn("<script>", page)
        self.assertNotIn(" style=", page)  # the style policy allows only the app's stylesheets
        self.assertIn("Statistically Speaking", page)
        self.assertIn("Full Monty", page)
        self.assertIn("Three doors. One car. Should you switch?", page)
        self.assertEqual(browser.get("/join")[0], 200)
        self.assertEqual(browser.get("/admin")[0], 200)
        status, headers, _ = browser.get(f"{X}/new")
        self.assertEqual((status, headers["location"]), (303, f"https://valentemath.com{PREFIX}/admin/"))
        self.assertEqual(browser.get("/account")[0], 404)  # no shared accounts when standalone
        for path in ("/static/design/tokens.css", "/static/show.js", "/static/fm-student.js", "/static/favicon.svg"):
            self.assertEqual(browser.get(path)[0], 200, path)

    def test_cookie_contract(self):
        browser = self.browser()
        browser.post("/admin/login", form={"teacher_name": "Cookie Monster"})
        raw = next(c for c in browser.raw_cookies if c.startswith("statistically_speaking_session="))
        attrs = {a.strip().split("=")[0].lower(): a.strip() for a in raw.split(";")[1:]}
        self.assertEqual(attrs["path"].lower(), f"path={PREFIX}")
        self.assertIn("httponly", attrs)
        self.assertIn("secure", attrs)
        self.assertEqual(attrs["samesite"].lower(), "samesite=lax")

    def test_ownership(self):
        teacher = self.browser().teacher("Owner")
        session_id, code = self.session(teacher)
        other = self.browser().teacher("Owner")  # same name, different browser: a different teacher
        status, headers, _ = other.get(f"{X}/t/{session_id}")
        self.assertEqual((status, headers["location"]), (303, f"https://valentemath.com{PREFIX}/admin/dashboard"))
        self.assertEqual(other.json("GET", f"{X}/t/{session_id}/state")[0], 404)
        maya = self.browser().student(code, "Maya")
        status, _, page = self.browser().post("/session/join", form={"join_code": code, "player_name": "Maya"})
        self.assertEqual(status, 400)
        self.assertIn("already taken", page)
        self.assertEqual(maya.post("/session/join", form={"join_code": code, "player_name": "Maya"})[0], 303)
        self.assertEqual(self.state(session_id)["session"]["players"], 1)
        # A student cannot run teacher actions.
        status, headers, _ = maya.post(f"{X}/t/{session_id}/pairs", form={"mode": "newcomers"})
        self.assertEqual((status, headers["location"]), (303, f"https://valentemath.com{PREFIX}/admin/"))
        self.assertIsNone(self.state(session_id, maya)["table"])

    def test_full_classroom_flow(self):
        teacher = self.browser().teacher()
        session_id, code = self.session(teacher)
        maya = self.browser().student(code, "Maya")
        theo = self.browser().student(code, "Theo")
        zed = self.browser().student(code, "Zed")
        students = {"Maya": maya, "Theo": theo, "Zed": zed}

        # The lobby: the first question is open, the second is not, and nobody is seated.
        st = self.state(session_id, maya)
        self.assertEqual((st["session"]["status"], st["table"], st["game"], st["you"]["name"]), ("lobby", None, None, "Maya"))
        self.assertEqual(self.vote(maya, session_id, "before", "same")[0], 200)
        self.assertEqual(self.vote(theo, session_id, "before", "switch")[0], 200)
        self.assertEqual(self.vote(maya, session_id, "before", "meh")[0], 409)
        self.assertEqual(self.vote(maya, session_id, "after", "switch")[0], 409)
        self.assertEqual(self.act(maya, session_id, "pick", door=1)[0], 409)
        self.assertEqual(self.state(session_id, maya)["you"]["votes"], {"before": "same"})
        self.assertEqual(self.state(session_id)["record"]["votes"]["before"], {"switch": 1, "stay": 0, "same": 1, "total": 2})

        # Seating: three students make one pair and one table against the House.
        self.seat(teacher, session_id)
        ts = self.tables(teacher, session_id)
        self.assertEqual(ts["session"]["status"], "active")
        self.assertEqual(len(ts["tables"]), 2)
        human = next(t for t in ts["tables"] if not t["house"])
        house = next(t for t in ts["tables"] if t["house"])
        host, contestant = students[human["first"]], students[human["second"]]
        solo = students[house["first"]]
        self.assertEqual(ts["unpaired"], [])
        self.assertEqual(self.vote(maya, session_id, "before", "stay")[0], 409)  # closed once seated

        # Game 1 at the human table: the host hides, the contestant picks, the host opens a goat.
        hs, cs = self.state(session_id, host), self.state(session_id, contestant)
        self.assertEqual((hs["game"]["status"], hs["game"]["role"], cs["game"]["role"]), ("hiding", "host", "contestant"))
        self.assertEqual(cs["table"]["partner"], human["first"])
        self.assertEqual(self.act(contestant, session_id, "pick", door=1)[0], 409)
        self.assertEqual(self.act(host, session_id, "hide", door=4)[0], 409)
        status, body = self.act(host, session_id, "hide", door=2)
        self.assertEqual((status, body["game"]["status"], body["game"]["car"]), (200, "picking", 2))
        self.assertNotIn("car", self.state(session_id, contestant)["game"])  # the host's secret
        self.assertEqual(self.act(host, session_id, "hide", door=3)[0], 409)  # once
        status, body = self.act(contestant, session_id, "pick", door=1)
        self.assertEqual((status, body["game"]["status"]), (200, "opening"))
        self.assertEqual(self.state(session_id, host)["game"]["legal"], [3])
        self.assertIn("car", self.act(host, session_id, "open", door=2)[1]["error"])
        self.assertIn("contestant's door", self.act(host, session_id, "open", door=1)[1]["error"])
        status, body = self.act(host, session_id, "open", door=3)
        self.assertEqual((status, body["game"]["status"], body["game"]["opened"]), (200, "deciding", 3))
        self.assertEqual(self.act(host, session_id, "decide", decision="switch")[0], 409)  # not the host's call
        status, body = self.act(contestant, session_id, "decide", decision="switch")
        g = body["game"]
        self.assertEqual((status, g["status"], g["final"], g["won"], g["car"], g["rule"]), (200, "revealed", 2, True, 2, "choice"))
        self.assertEqual(self.state(session_id, contestant)["table"]["played"], 1)
        rec = self.state(session_id)["record"]["tallies"]
        self.assertEqual((rec["games"], rec["switch"], rec["first_pick_right"]), (1, {"n": 1, "wins": 1, "rate": 1.0, "surprise": 0.5}, 0))

        # Both partners tap next at once: one new game, with the roles swapped.
        old = self.state(session_id, host)["game"]["id"]
        self.assertEqual(self.act(host, session_id, "next", game=old)[1]["game"]["index"], 2)
        self.assertEqual(self.act(contestant, session_id, "next", game=old)[1]["game"]["index"], 2)
        self.assertIn("Finish this game first", self.act(contestant, session_id, "next")[1]["error"])
        self.assertEqual(self.state(session_id, host)["game"]["role"], "contestant")
        host, contestant = contestant, host

        # The rule forces a decision; a game records the rule in force when it was decided.
        status, _, _ = teacher.post(f"{X}/t/{session_id}/rule", form={"rule": "stay"})
        self.assertEqual(status, 303)
        self.assertEqual(self.state(session_id)["session"]["rule"], "stay")
        self.act(host, session_id, "hide", door=1)
        self.act(contestant, session_id, "pick", door=1)
        self.act(host, session_id, "open", door=3)
        self.assertIn("rule right now is to stay", self.act(contestant, session_id, "decide", decision="switch")[1]["error"])
        g = self.act(contestant, session_id, "decide", decision="stay")[1]["game"]
        self.assertEqual((g["decision"], g["won"], g["rule"]), ("stay", True, "stay"))
        teacher.post(f"{X}/t/{session_id}/rule", form={"rule": "choice"})

        # The House hosts the solo table: the car is hidden and a goat opened without a tap.
        ss = self.state(session_id, solo)
        self.assertEqual((ss["table"]["house"], ss["table"]["partner"], ss["game"]["status"], ss["game"]["host"]),
                         (True, "The House", "picking", "The House"))
        self.assertNotIn("car", ss["game"])
        status, body = self.act(solo, session_id, "pick", door=2)
        self.assertEqual((status, body["game"]["status"]), (200, "deciding"))
        self.assertNotIn(body["game"]["opened"], (2, body["game"].get("car")))
        g = self.act(solo, session_id, "decide", decision="switch")[1]["game"]
        self.assertEqual(g["won"], g["car"] != 2)
        self.assertEqual(self.act(solo, session_id, "next")[1]["game"]["status"], "picking")

        # Reshuffling retires the tables and drops the games in play; the record keeps the finished ones.
        self.act(host, session_id, "next")
        self.act(host, session_id, "hide", door=3)
        before = self.state(session_id)["record"]["tallies"]
        self.assertEqual(before["games"], 3)
        self.seat(teacher, session_id, "reshuffle")
        ts = self.tables(teacher, session_id)
        self.assertEqual([t["index"] for t in ts["tables"]], [3, 4])
        self.assertEqual(ts["summary"]["tallies"], before)
        self.assertEqual(self.state(session_id, maya)["game"]["index"], 1)

        # The projector sees the record and nothing personal; a late joiner waits to be seated.
        public = self.state(session_id)
        self.assertIsNone(public["you"])
        self.assertIsNone(public["table"])
        self.assertEqual(len(public["record"]["series"]), 3)
        late = self.browser().student(code, "Late")
        self.assertIsNone(self.state(session_id, late)["table"])
        self.assertEqual(self.tables(teacher, session_id)["unpaired"], ["Late"])
        self.assertEqual(self.vote(late, session_id, "before", "stay")[0], 200)
        self.seat(teacher, session_id)
        self.assertEqual(self.state(session_id, late)["table"]["house"], True)

        # The end: the second question opens, play closes, and everyone gets a summary.
        status, _, _ = teacher.post(f"{X}/t/{session_id}/end")
        self.assertEqual(status, 303)
        st = self.state(session_id, maya)
        self.assertEqual(st["session"]["status"], "ended")
        self.assertEqual(self.act(maya, session_id, "next")[0], 409)
        self.assertEqual(self.vote(maya, session_id, "before", "stay")[0], 409)
        self.assertEqual(self.vote(maya, session_id, "after", "switch")[0], 200)
        you = self.state(session_id, maya)
        self.assertEqual(you["you"]["votes"], {"before": "same", "after": "switch"})
        # Two revealed games at the human table, one at the House table.
        self.assertEqual(you["summary"]["played"] + you["summary"]["hosted"], 1 if solo is maya else 2)
        self.assertIsNone(self.state(session_id)["summary"])
        self.assertEqual(self.state(session_id)["record"]["votes"]["after"]["total"], 1)
        status, _, page = self.browser().post("/session/join", form={"join_code": code, "player_name": "Later"})
        self.assertEqual(status, 400)

        # Exports: one row per game, revealed or dropped; one row per student for the beliefs.
        status, headers, body = teacher.get(f"{X}/t/{session_id}/export")
        self.assertEqual((status, headers["content-type"]), (200, "text/csv; charset=utf-8"))
        rows = body.strip().splitlines()
        self.assertEqual(rows[0].split(",")[:6], ["table", "game", "host", "contestant", "status", "car"])
        self.assertEqual(sum(1 for r in rows[1:] if ",revealed," in r), 3)
        self.assertGreaterEqual(sum(1 for r in rows[1:] if ",void," in r), 2)
        status, _, body = teacher.get(f"{X}/t/{session_id}/export/votes")
        self.assertEqual(status, 200)
        self.assertEqual(len(body.strip().splitlines()), 1 + 4)
        self.assertIn("Maya,same,switch", body)

    def test_dispatch_and_presenter(self):
        teacher = self.browser().teacher("Dispatcher")
        session_id, code = self.session(teacher)
        maya = self.browser().student(code, "Maya")
        status, headers, _ = maya.get(f"/s/{session_id}")
        self.assertEqual((status, headers["location"]), (303, f"https://valentemath.com{PREFIX}{X}/s/{session_id}"))
        self.assertEqual(maya.get(f"{X}/s/{session_id}")[0], 200)
        status, headers, _ = teacher.get(f"/admin/s/{session_id}")
        self.assertEqual(headers["location"], f"https://valentemath.com{PREFIX}{X}/t/{session_id}")
        status, _, page = self.browser().get(f"{X}/p/{session_id}")
        self.assertEqual(status, 200)
        self.assertIn(code, page)
        self.assertIn(f"{PREFIX}/join", page)
        self.assertIn(f'src="https://valentemath.com{PREFIX}/join/qr/{code}.svg"', page)
        self.assertEqual(self.browser().get(f"/join/qr/{code}.svg")[0], 200)
        self.assertEqual(self.browser().get(f"{X}/t/{session_id}")[0], 303)  # not logged in
        status, headers, _ = self.browser().get(f"{X}/s/{session_id}")
        self.assertEqual((status, headers["location"]), (303, f"https://valentemath.com{PREFIX}/join"))

    def test_persistence_across_restart(self):
        teacher = self.browser().teacher("Persist")
        session_id, code = self.session(teacher)
        maya = self.browser().student(code, "Maya")
        self.seat(teacher, session_id)
        self.act(maya, session_id, "pick", door=1)
        self.stop()
        self.start()
        st = self.state(session_id, maya)
        self.assertEqual((st["session"]["join_code"], st["game"]["status"], st["game"]["pick"]), (code, "deciding", 1))
        self.assertEqual(teacher.get(f"{X}/t/{session_id}")[0], 200)


if __name__ == "__main__":
    unittest.main()
