"""Full Monty game logic: the doors, the record, and the plain-English numbers."""
import unittest

from app.experiences.full_monty import logic


class Doors(unittest.TestCase):
    def test_host_may_open_only_a_goat_the_contestant_did_not_pick(self):
        self.assertEqual(logic.legal_opens(car=1, pick=1), [2, 3])
        self.assertEqual(logic.legal_opens(car=1, pick=2), [3])
        self.assertEqual(logic.legal_opens(car=3, pick=2), [1])
        for car in logic.DOORS:
            for pick in logic.DOORS:
                for d in logic.legal_opens(car, pick):
                    self.assertNotIn(d, (car, pick))

    def test_switching_wins_exactly_when_the_first_pick_was_wrong(self):
        for car in logic.DOORS:
            for pick in logic.DOORS:
                for opened in logic.legal_opens(car, pick):
                    final, won = logic.outcome(car, pick, opened, "switch")
                    self.assertEqual(won, pick != car)
                    self.assertNotIn(final, (pick, opened))
                    final, won = logic.outcome(car, pick, opened, "stay")
                    self.assertEqual((final, won), (pick, pick == car))

    def test_the_house_follows_the_rules(self):
        for _ in range(50):
            car = logic.house_hides()
            self.assertIn(car, logic.DOORS)
            for pick in logic.DOORS:
                self.assertIn(logic.house_opens(car, pick), logic.legal_opens(car, pick))


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
