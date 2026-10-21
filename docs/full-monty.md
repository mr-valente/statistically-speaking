# Full Monty: design note

**What students should leave with:** the first pick is right one time in three, and nothing the host does changes that. Switching wins exactly when the first pick was wrong, so it wins two times in three. The reason the host matters is that the host *knows*: a host who must open a goat door is handing over information.

**How the experience gets there:** by playing, not by being told. Pairs run the game on their phones for ten to fifteen minutes. Each game lands in a class record on the projector. The record does the arguing.

## The shape of a session

| Minutes | Segment | What happens |
|---:|---|---|
| 0–5 | Join | Students scan the QR code and answer the first question: switch, stay, or no difference? Most rooms say *no difference*. The projector shows only how many have answered. |
| 5–8 | Seat and explain | Seat everyone. Two rules of the room: the host always knows where the car is, and the host must open a door with a goat that the contestant did not pick. The phones enforce the second one. |
| 8–22 | Play | Partners alternate. The teacher watches the two columns on the projector and switches the **rule** when one is short: a few minutes of *everyone stays*, then *everyone switches*, then back to *contestants choose*. |
| 22–30 | Read the record | The stay column settles near one third, the switch column near two thirds, and the first-pick line says *right about one time in three*. Ask the hosts: when the contestant picked the car, how many goats could you open? When they missed, how many? |
| 30–35 | End | End the session. Students answer the question again, then see their own games. The projector shows beliefs before and after. |

## Why these pieces

- **Students host.** The crux of the problem is that the host knows and is constrained. A student who has had to find a goat door to open, and who has twice had a choice of two goats and once had no choice at all, has felt the mechanism. The app refuses an illegal door and says why, which is the lesson in one line.
- **Hosts hide the car by hand.** Tapping a door to hide the car makes the host a player, not a button. Human placement is not quite uniform, but the contestant cannot see it, so the first pick is still right about a third of the time and the record still separates cleanly. The export records the car's door, so a class can look for a favourite door afterwards.
- **The House.** An odd student out plays against the server, which hides and opens at random. The game is the same; the student just never hosts.
- **The rule.** Left to themselves, contestants drift toward switching once it starts working, and the stay column stops filling. A session-wide rule the teacher can flip at any moment keeps both columns growing without taking the decision away for the whole lesson. Each game records the rule in force when its decision was made.
- **Beliefs before and after.** The question is cheap, the answer is memorable, and the before-and-after bar on the projector shows the room changing its mind on evidence. The "before" answer closes when a student is seated, so it is never contaminated by play.
- **The chart.** Both win rates after each game, with 1/3, 1/2 and 2/3 ruled across. Early wobble, then settling, is the law of large numbers in one picture.
- **One plain-English line.** "If switching made no difference, winning at least 68 of 100 would happen about 0.02% of the time, roughly 1 in 4,893." It is the same move as Bernoulli's "a fair coin does this about 1 in 9 times": a P-value with no name yet.

## Ideas not built

Ranked by how much they would add for the cost.

1. **More doors.** Ten doors, host opens eight. The intuition pump that makes the three-door answer obvious. Cheap to add to the logic; the host's phone would open the goat doors in one tap instead of eight. Best as a second phase of the same session, after the record has settled.
2. **Monty Fall.** A host who does not know where the car is and opens a door at random; games where the car is revealed are dropped. Switching no longer helps. The sharpest way to show that the host's knowledge is the whole story, and a natural second experience in the suite.
3. **Table leaderboard on the projector.** Games played per table, to keep the pace up. Easy, but it rewards speed, which is not the point.
4. **A single-player simulator.** Play 100 games against the House in a minute with one strategy. Useful for homework or an absent student; it loses the partner mechanism that makes the class version work.
