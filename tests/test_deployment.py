"""Deployment regressions using a real server, a URL prefix, and a disposable SQLite database."""
import json
import re
import unittest

from tests.support import PREFIX, ServerTest

X = "/x/full-monty"


class FullMontyTests(ServerTest):
    # ── Fixtures ────────────────────────────────────────────────────────────

    def session(self, teacher, label="P3", survey=True):
        form = {"label": label, **({"survey": "on"} if survey else {})}
        status, headers, _ = teacher.post(f"{X}/create", form=form)
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

    def seating(self, browser, session_id, action, **extra):
        return browser.json("POST", f"{X}/s/{session_id}/seating", payload={"action": action, **extra})

    def vote(self, browser, session_id, phase, choice):
        return browser.json("POST", f"{X}/s/{session_id}/vote", payload={"phase": phase, "choice": choice})

    def teacher_state(self, teacher, session_id):
        status, body = teacher.json("GET", f"{X}/t/{session_id}/state")
        self.assertEqual(status, 200)
        return body

    def sit_together(self, session_id, asker, asked):
        """asker taps asked's name; asked says yes. Returns asked's state."""
        status, body = self.seating(asker, session_id, "ask", player=asked.me)
        self.assertEqual(status, 200, body)
        inbox = self.state(session_id, asked)["you"]["inbox"]
        req = next(r for r in inbox if r["from"] == asker.name)
        status, body = self.seating(asked, session_id, "accept", request=req["id"])
        self.assertEqual(status, 200, body)
        return body

    def students(self, session_id, code, *names):
        out = {}
        for name in names:
            b = self.browser().student(code, name)
            b.name, b.me = name, self.state(session_id, b)["you"]["id"]
            out[name] = b
        return out

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
        self.assertNotIn(" style=", page)  # the style policy allows only the app's stylesheet
        self.assertIn("Statistically Speaking", page)
        self.assertIn("Full Monty", page)
        self.assertIn("Three doors. Two goats. One boat.", page)
        status, _, join = browser.get("/join")
        self.assertEqual(status, 200)
        self.assertIn(f'href="https://valentemath.com{PREFIX}{X}/solo"', join)  # solo lives on the join page
        self.assertIn('data-dialog="solo-dialog"', join)                        # behind a picker when no show is named
        status, _, join = browser.get("/join?show=full-monty")
        self.assertIn(f'href="https://valentemath.com{PREFIX}{X}/solo" class="btn', join)  # straight to Monty from the card
        self.assertNotIn("solo-dialog", join)
        self.assertIn('name="show" value="full-monty"', join)
        status, _, join = browser.post("/session/join", form={"join_code": "NOPE00", "player_name": "Maya", "show": "full-monty"})
        self.assertEqual(status, 404)
        self.assertIn("No show found with code NOPE00", join)
        self.assertNotIn("solo-dialog", join)                                   # the error page keeps the context
        self.assertIn("solo-dialog", browser.get("/join?show=nope")[2])          # an unknown show falls back to the picker
        self.assertEqual(browser.get("/admin")[0], 200)
        status, _, solo = browser.get(f"{X}/solo")
        self.assertEqual(status, 200)
        self.assertIn("fm-solo.js", solo)
        self.assertNotIn(" style=", solo)
        status, headers, _ = browser.get(f"{X}/new")
        self.assertEqual((status, headers["location"]), (303, f"https://valentemath.com{PREFIX}/admin/"))
        self.assertEqual(browser.get("/account")[0], 404)  # no shared accounts when standalone
        for path in ("/static/show.css", "/static/show.js", "/static/fm-student.js", "/static/fm-solo.js", "/static/favicon.svg"):
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
        self.assertIn("already has that name", page)
        self.assertEqual(maya.post("/session/join", form={"join_code": code, "player_name": "Maya"})[0], 303)
        self.assertEqual(self.state(session_id)["session"]["players"], 1)
        # A student cannot run teacher actions.
        status, headers, _ = maya.post(f"{X}/t/{session_id}/start")
        self.assertEqual((status, headers["location"]), (303, f"https://valentemath.com{PREFIX}/admin/"))
        self.assertEqual(self.state(session_id, maya)["session"]["status"], "lobby")
        # Nobody outside the show can act in it.
        self.assertEqual(self.seating(self.browser(), session_id, "ask", player="x")[0], 403)

    def test_finding_tables(self):
        teacher = self.browser().teacher()
        session_id, code = self.session(teacher)
        s = self.students(session_id, code, "Maya", "Theo", "Zed", "Pia", "Omar")
        maya, theo, zed, pia, omar = (s[n] for n in ("Maya", "Theo", "Zed", "Pia", "Omar"))

        # Everyone starts out looking; the projector sees the room but nothing personal.
        public = self.state(session_id)
        self.assertEqual([p["name"] for p in public["room"]["looking"]], ["Maya", "Theo", "Zed", "Pia", "Omar"])
        self.assertEqual((public["room"]["tables"], public["you"]), ([], None))

        # Theo asks Maya; Maya sees it; yes makes table 1 with Theo in the first seat.
        self.assertEqual(self.seating(theo, session_id, "ask", player=theo.me)[1]["error"], "That's you.")
        self.assertEqual(self.seating(theo, session_id, "ask", player="nope")[0], 409)
        status, body = self.seating(theo, session_id, "ask", player=maya.me)
        self.assertEqual((status, body["you"]["asked"]["to"], body["table"]), (200, "Maya", None))
        inbox = self.state(session_id, maya)["you"]["inbox"]
        self.assertEqual([r["from"] for r in inbox], ["Theo"])
        body = self.seating(maya, session_id, "accept", request=inbox[0]["id"])[1]
        self.assertEqual((body["table"]["index"], body["table"]["members"], body["table"]["room"]), (1, ["Theo", "Maya"], True))
        self.assertEqual(body["you"]["inbox"], [])
        self.assertIsNone(self.state(session_id, theo)["you"]["asked"])
        self.assertEqual(self.seating(maya, session_id, "accept", request=inbox[0]["id"])[0], 409)  # gone

        # Zed asks to join Maya's table: a third seat. Pia asks after that and the table is full.
        body = self.sit_together(session_id, zed, maya)
        self.assertEqual(body["table"]["members"], ["Theo", "Maya", "Zed"])
        self.assertEqual(self.seating(pia, session_id, "ask", player=maya.me)[1]["error"], "That table is full.")
        self.assertEqual(self.seating(maya, session_id, "ask", player=pia.me)[1]["error"], "Your table is full.")

        # Asking someone who already asked you is a yes. Declining is a no.
        self.seating(pia, session_id, "ask", player=omar.me)
        body = self.seating(omar, session_id, "ask", player=pia.me)[1]
        self.assertEqual(body["table"]["members"], ["Pia", "Omar"])
        self.assertEqual(self.seating(omar, session_id, "leave")[1]["table"], None)
        self.assertEqual(self.state(session_id, pia)["table"]["members"], ["Pia"])
        self.seating(omar, session_id, "ask", player=pia.me)
        req = self.state(session_id, pia)["you"]["inbox"][0]
        self.assertEqual(self.seating(pia, session_id, "decline", request=req["id"])[0], 200)
        self.assertIsNone(self.state(session_id, omar)["you"]["asked"])
        self.assertEqual(self.state(session_id, omar)["table"], None)

        # Taking a request back, then a stale one: Omar asks Pia, Pia's table fills up, the request expires.
        self.seating(omar, session_id, "ask", player=pia.me)
        self.assertIsNone(self.seating(omar, session_id, "cancel")[1]["you"]["asked"])
        self.assertEqual(self.state(session_id, pia)["you"]["inbox"], [])

        # The teacher's broom seats whoever is still looking: Omar joins the table with room.
        status, _, _ = teacher.post(f"{X}/t/{session_id}/seat")
        self.assertEqual(status, 303)
        room = self.teacher_state(teacher, session_id)["room"]
        self.assertEqual(room["looking"], [])
        self.assertEqual([[m["name"] for m in t["members"]] for t in room["tables"]], [["Theo", "Maya", "Zed"], ["Pia", "Omar"]])

        # Nobody plays before the show starts; the first question stays open.
        self.assertEqual(self.state(session_id, maya)["game"], None)
        self.assertEqual(self.vote(maya, session_id, "before", "same")[0], 200)
        teacher.post(f"{X}/t/{session_id}/start")
        st = self.state(session_id, maya)
        self.assertEqual((st["session"]["status"], st["game"]["status"], st["game"]["host"], st["game"]["contestant"], st["game"]["role"]),
                         ("active", "hiding", "Theo", "Maya", "contestant"))
        self.assertEqual(self.state(session_id, zed)["game"]["role"], "watching")
        self.assertEqual(self.state(session_id, zed)["table"]["next"], {"host": "Maya", "contestant": "Zed"})
        self.assertIn("closed", self.vote(maya, session_id, "before", "switch")[1]["error"])

    def test_the_belief_question_can_be_switched_off(self):
        teacher = self.browser().teacher()
        session_id, code = self.session(teacher, survey=False)
        maya = self.students(session_id, code, "Maya")["Maya"]
        st = self.state(session_id, maya)
        self.assertFalse(st["session"]["survey"])
        status, body = self.vote(maya, session_id, "before", "switch")
        self.assertEqual(status, 409)
        self.assertIn("switched off", body["error"])
        self.assertFalse(self.teacher_state(teacher, session_id)["session"]["survey"])
        status, _, page = teacher.get(f"{X}/t/{session_id}")
        self.assertNotIn("What the room believes", page)
        self.assertNotIn("Beliefs CSV", page)
        self.assertIn('name="survey"', page)
        status, _, page = self.browser().get(f"{X}/p/{session_id}")
        self.assertEqual(status, 200)
        self.assertNotIn("answered the question", page)

        # The teacher switches it on mid-lobby; the question opens and the dashboard shows it.
        status, _, _ = teacher.post(f"{X}/t/{session_id}/survey", form={"survey": "on"})
        self.assertEqual(status, 303)
        self.assertTrue(self.state(session_id, maya)["session"]["survey"])
        self.assertEqual(self.vote(maya, session_id, "before", "switch")[0], 200)
        _, _, page = teacher.get(f"{X}/t/{session_id}")
        self.assertIn("What the room believes", page)
        self.assertIn("Beliefs CSV", page)

        # And off again: no field in the form means unchecked.
        teacher.post(f"{X}/t/{session_id}/survey", form={})
        self.assertFalse(self.state(session_id, maya)["session"]["survey"])
        self.assertEqual(self.vote(maya, session_id, "before", "stay")[0], 409)

    def test_full_classroom_flow(self):
        teacher = self.browser().teacher()
        session_id, code = self.session(teacher)
        s = self.students(session_id, code, "Maya", "Theo", "Zed")
        maya, theo, zed = s["Maya"], s["Theo"], s["Zed"]

        # The lobby: the first question is open, the second is not, and nobody is playing.
        st = self.state(session_id, maya)
        self.assertEqual((st["session"]["status"], st["table"], st["game"], st["you"]["name"]), ("lobby", None, None, "Maya"))
        self.assertEqual(self.vote(maya, session_id, "before", "same")[0], 200)
        self.assertEqual(self.vote(theo, session_id, "before", "switch")[0], 200)
        self.assertEqual(self.vote(maya, session_id, "before", "meh")[0], 409)
        self.assertEqual(self.vote(maya, session_id, "after", "switch")[0], 409)
        self.assertEqual(self.act(maya, session_id, "pick", door=1)[0], 409)
        self.assertEqual(self.state(session_id, maya)["you"]["votes"], {"before": "same"})
        self.assertEqual(self.state(session_id)["record"]["votes"]["before"], {"switch": 1, "stay": 0, "same": 1, "total": 2})

        # Maya and Theo sit together; Zed joins them. The teacher starts the show.
        self.sit_together(session_id, maya, theo)
        self.sit_together(session_id, zed, theo)
        status, _, _ = teacher.post(f"{X}/t/{session_id}/start")
        self.assertEqual(status, 303)
        ts = self.teacher_state(teacher, session_id)
        self.assertEqual(ts["session"]["status"], "active")
        self.assertEqual(len(ts["room"]["tables"]), 1)
        self.assertEqual(ts["room"]["tables"][0]["game"]["host"], "Maya")

        # Game 1: Maya hosts, Theo plays, Zed watches. The host hides, the contestant picks, the host opens a goat.
        host, contestant, watcher = maya, theo, zed
        hs, cs, ws = self.state(session_id, host), self.state(session_id, contestant), self.state(session_id, watcher)
        self.assertEqual((hs["game"]["status"], hs["game"]["role"], cs["game"]["role"], ws["game"]["role"]), ("hiding", "host", "contestant", "watching"))
        self.assertEqual(self.act(contestant, session_id, "pick", door=1)[0], 409)
        self.assertEqual(self.act(watcher, session_id, "hide", door=1)[0], 409)
        self.assertEqual(self.act(host, session_id, "hide", door=4)[0], 409)
        status, body = self.act(host, session_id, "hide", door=2)
        self.assertEqual((status, body["game"]["status"], body["game"]["boat"]), (200, "picking", 2))
        self.assertNotIn("boat", self.state(session_id, contestant)["game"])  # the host's secret
        self.assertNotIn("boat", self.state(session_id, watcher)["game"])
        self.assertEqual(self.act(host, session_id, "hide", door=3)[0], 409)  # once
        status, body = self.act(contestant, session_id, "pick", door=1)
        self.assertEqual((status, body["game"]["status"]), (200, "opening"))
        self.assertEqual(self.state(session_id, host)["game"]["legal"], [3])
        self.assertIn("boat", self.act(host, session_id, "open", door=2)[1]["error"])
        self.assertIn("contestant's door", self.act(host, session_id, "open", door=1)[1]["error"])
        status, body = self.act(host, session_id, "open", door=3)
        self.assertEqual((status, body["game"]["status"], body["game"]["opened"]), (200, "deciding", 3))
        self.assertEqual(self.act(host, session_id, "decide", decision="switch")[0], 409)  # not the host's call
        status, body = self.act(contestant, session_id, "decide", decision="switch")
        g = body["game"]
        self.assertEqual((status, g["status"], g["final"], g["won"], g["boat"], g["rule"]), (200, "revealed", 2, True, 2, "choice"))
        self.assertEqual(self.state(session_id, watcher)["game"]["boat"], 2)  # everyone sees the reveal
        self.assertEqual(self.state(session_id, contestant)["table"]["played"], 1)
        rec = self.state(session_id)["record"]["tallies"]
        self.assertEqual((rec["games"], rec["switch"], rec["first_pick_right"]), (1, {"n": 1, "wins": 1, "rate": 1.0, "surprise": 0.5}, 0))

        # Everyone taps next at once: one new game, with the roles walked around the table.
        old = self.state(session_id, host)["game"]["id"]
        self.assertEqual(self.act(watcher, session_id, "next", game=old)[1]["game"]["index"], 2)
        self.assertEqual(self.act(contestant, session_id, "next", game=old)[1]["game"]["index"], 2)
        self.assertIn("Finish this game first", self.act(contestant, session_id, "next")[1]["error"])
        g = self.state(session_id, theo)["game"]
        self.assertEqual((g["host"], g["contestant"], g["role"]), ("Theo", "Zed", "host"))
        host, contestant, watcher = theo, zed, maya

        # The house rule forces a decision; a game records the rule in force when it was decided.
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

        # Game 3: Zed hosts Maya. Zed leaves mid-game: the game is dropped and the pair plays on.
        self.act(maya, session_id, "next")
        g = self.state(session_id, maya)["game"]
        self.assertEqual((g["index"], g["host"], g["contestant"]), (3, "Zed", "Maya"))
        self.act(zed, session_id, "hide", door=3)
        before = self.state(session_id)["record"]["tallies"]
        self.assertEqual(before["games"], 2)
        body = self.seating(zed, session_id, "leave")[1]
        self.assertEqual((body["table"], body["game"]), (None, None))
        g = self.state(session_id, maya)["game"]
        self.assertEqual((g["index"], g["status"], g["host"], g["contestant"]), (4, "hiding", "Theo", "Maya"))
        self.assertEqual(self.state(session_id)["record"]["tallies"], before)
        self.assertEqual([p["name"] for p in self.state(session_id)["room"]["looking"]], ["Zed"])

        # A late joiner sits with Zed; their new table starts playing at once because the show is on.
        late = self.students(session_id, code, "Late")["Late"]
        self.assertEqual(self.vote(late, session_id, "before", "stay")[0], 200)
        body = self.sit_together(session_id, late, zed)
        self.assertEqual((body["table"]["index"], body["game"]["status"], body["game"]["host"]), (2, "hiding", "Late"))

        # The end: the second question opens, play closes, and everyone gets a summary.
        status, _, _ = teacher.post(f"{X}/t/{session_id}/end")
        self.assertEqual(status, 303)
        st = self.state(session_id, maya)
        self.assertEqual(st["session"]["status"], "ended")
        self.assertEqual(self.act(maya, session_id, "next")[0], 409)
        self.assertEqual(self.seating(maya, session_id, "ask", player=zed.me)[0], 409)
        self.assertEqual(self.vote(maya, session_id, "before", "stay")[0], 409)
        self.assertEqual(self.vote(maya, session_id, "after", "switch")[0], 200)
        you = self.state(session_id, maya)
        self.assertEqual(you["you"]["votes"], {"before": "same", "after": "switch"})
        self.assertEqual((you["summary"]["played"], you["summary"]["hosted"]), (0, 1))
        self.assertEqual(self.state(session_id, theo)["summary"]["played"], 1)
        self.assertIsNone(self.state(session_id)["summary"])
        self.assertEqual(self.state(session_id)["record"]["votes"]["after"]["total"], 1)
        status, _, page = self.browser().post("/session/join", form={"join_code": code, "player_name": "Later"})
        self.assertEqual(status, 400)

        # Exports: one row per game, revealed or dropped; one row per student for the beliefs.
        status, headers, body = teacher.get(f"{X}/t/{session_id}/export")
        self.assertEqual((status, headers["content-type"]), (200, "text/csv; charset=utf-8"))
        rows = body.strip().splitlines()
        self.assertEqual(rows[0].split(",")[:6], ["table", "game", "host", "contestant", "status", "boat"])
        self.assertEqual(sum(1 for r in rows[1:] if ",revealed," in r), 2)
        self.assertEqual(sum(1 for r in rows[1:] if ",void," in r), 3)
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
        s = self.students(session_id, code, "Maya", "Theo")
        self.sit_together(session_id, s["Maya"], s["Theo"])
        teacher.post(f"{X}/t/{session_id}/start")
        self.act(s["Maya"], session_id, "hide", door=1)
        self.act(s["Theo"], session_id, "pick", door=2)
        self.stop()
        self.start()
        st = self.state(session_id, s["Theo"])
        self.assertEqual((st["session"]["join_code"], st["game"]["status"], st["game"]["pick"], st["table"]["members"]),
                         (code, "opening", 2, ["Maya", "Theo"]))
        self.assertEqual(teacher.get(f"{X}/t/{session_id}")[0], 200)


if __name__ == "__main__":
    unittest.main()
