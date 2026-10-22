"""Full Monty game logic: the doors, the rotation, the record, and the plain-English numbers."""
import unittest

from app.experiences.full_monty import logic


class Doors(unittest.TestCase):
    def test_host_may_open_only_a_goat_the_contestant_did_not_pick(self):
        self.assertEqual(logic.legal_opens(boat=1, pick=1), [2, 3])
        self.assertEqual(logic.legal_opens(boat=1, pick=2), [3])
        self.assertEqual(logic.legal_opens(boat=3, pick=2), [1])
        for boat in logic.DOORS:
            for pick in logic.DOORS:
                for d in logic.legal_opens(boat, pick):
                    self.assertNotIn(d, (boat, pick))

    def test_switching_wins_exactly_when_the_first_pick_was_wrong(self):
        for boat in logic.DOORS:
            for pick in logic.DOORS:
                for opened in logic.legal_opens(boat, pick):
                    final, won = logic.outcome(boat, pick, opened, "switch")
                    self.assertEqual(won, pick != boat)
                    self.assertNotIn(final, (pick, opened))
                    final, won = logic.outcome(boat, pick, opened, "stay")
                    self.assertEqual((final, won), (pick, pick == boat))

    def test_monty_follows_the_rules(self):
        for _ in range(50):
            boat = logic.monty_hides()
            self.assertIn(boat, logic.DOORS)
            for pick in logic.DOORS:
                self.assertIn(logic.monty_opens(boat, pick), logic.legal_opens(boat, pick))


class Rotation(unittest.TestCase):
    def test_two_partners_alternate(self):
        self.assertEqual([logic.roles_for(i, ["a", "b"]) for i in (1, 2, 3, 4)],
                         [("a", "b"), ("b", "a"), ("a", "b"), ("b", "a")])

    def test_three_take_turns_hosting_playing_and_watching(self):
        games = [logic.roles_for(i, ["a", "b", "c"]) for i in range(1, 7)]
        self.assertEqual(games[:3], [("a", "b"), ("b", "c"), ("c", "a")])
        self.assertEqual(games[3:], games[:3])
        for host, contestant in games:
            self.assertNotEqual(host, contestant)
        self.assertEqual({h for h, _ in games}, {"a", "b", "c"})
        self.assertEqual({c for _, c in games}, {"a", "b", "c"})


class Numbers(unittest.TestCase):
    def test_no_effect_surprise_is_the_upper_binomial_tail(self):
        self.assertIsNone(logic.no_effect_surprise(0, 0))
        self.assertEqual(logic.no_effect_surprise(0, 4), 1.0)
        self.assertAlmostEqual(logic.no_effect_surprise(4, 4), 1 / 16)
        self.assertAlmostEqual(logic.no_effect_surprise(3, 4), 5 / 16)
        self.assertAlmostEqual(logic.no_effect_surprise(68, 100), 0.000204, places=6)

    def test_plain_english(self):
        self.assertIn("Nobody has switched yet", logic.describe_surprise("switch", 0, 0))
        self.assertIn("more than half the time", logic.describe_surprise("switch", 1, 4))
        self.assertIn("about 31% of the time", logic.describe_surprise("switch", 3, 4))
        text = logic.describe_surprise("switch", 68, 100)
        self.assertIn("If switching made no difference, winning at least 68 of 100", text)
        self.assertIn("1 in 4,893", text)
        self.assertIn("less than once in a million", logic.describe_surprise("stay", 60, 60))


if __name__ == "__main__":
    unittest.main()
