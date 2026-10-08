# STV count viz

Animates the single transferable vote (STV) count of every Scottish council election in
`data/scottish_vote_tables/`. It is plain HTML and JavaScript with no build step or dependencies.

## Run it

The page reads the repo's CSV files, and browsers block that for pages opened straight from disk.
Start a static web server in the **repo root** (the folder that holds `data/` and `viz/`), then open
<http://localhost:8000/viz/>. Any one of these commands works:

| Tool     | Command                          |
| -------- | -------------------------------- |
| Python 3 | `python3 -m http.server 8000`    |
| Node.js  | `npx http-server -p 8000`        |
| Node.js  | `npx serve -l 8000`              |
| PHP      | `php -S localhost:8000`          |
| Ruby 2.x | `ruby -run -e httpd . -p 8000`   |

The first `npx` run downloads the server package. Ruby 3 needs `gem install webrick` before its
command works. In VS Code, the Live Server extension also works if the repo root is the open folder.

Each count has its own link, such as <http://localhost:8000/viz/#glasgow_2017_ward2>.

## Reading the chart

The page opens on an "About the data" introduction; pick a ward to watch its count. Bars take their
party's color: Labour, Conservative, Liberal Democrat, Green and SNP have their own, and every
other label, independents included, shares the independents' teal. Later candidates sharing a color
get lighter shades, in ballot order (alphabetical by surname).

Each chunk of a bar shows the candidate who last passed those votes on. The vote tables only record
each round's totals, so they can't show who the voters first chose: a vote can pass through several
candidates before it settles.

When a candidate is elected, their bar squashes down into a strip along its bottom, and the rest
turns gray. When their surplus moves on, the gray bar and its strip squash back to the quota,
keeping the same mix of colors, and the surplus above the quota, now in the winner's own color,
flies to the candidates it transfers to. Votes that can't transfer collect in a "Non-transferable"
row at the bottom, hatched in the color of the candidate whose transfer lost them. Hover over or tap
a row for a table of who last passed its votes on.

The page rebuilds each count from its vote table, which lists every candidate's total after each
round. Each round moves one candidate's votes: a winner's surplus, which cuts them back to the
quota, or all the votes of the candidate eliminated. The quota is the votes divided by one more than
the seats, rounded down, plus one. The rises in other totals are the transfers, and whatever they
don't cover is non-transferable. When a winner's surplus moves, the winner keeps the same share of
every part of their bar. `node viz/check.mjs` checks that every count rebuilds and fills its seats,
that each table's first round matches its ballots in `data/scot-elex/`, and that no vote goes
missing.

## Controls

- **Replay** restarts the count. **Pause** stops between steps, and **Previous step** and **Next
  step** move one step at a time. Click any step in the list to jump straight to it, paused.
- **Speed** changes how fast the count plays, from the next step on.
- **Order** sorts candidates alphabetically (the default), by first-place votes, or by party and
  then first-place votes.
- **Download MP4** replays the count and saves it as a video at the chosen speed, with no
  screen-sharing prompt. Browsers that can't encode MP4, such as Firefox, offer WebM instead. Keep
  the tab in front while it records, because browsers pause animations in background tabs.

## Update the election list

`elections.csv` lists every vote table with its election file, seats, and ward name. After changing
the data, rebuild the list and re-run the checks:

```sh
python3 viz/make_index.py
node viz/check.mjs
```

## Files

| File            | What it holds                                                           |
| --------------- | ----------------------------------------------------------------------- |
| `index.html`    | The page's markup and templates.                                        |
| `style.css`     | The page's styles.                                                      |
| `app.mjs`       | Everything on screen: the list, chart, controls, popup and recording.   |
| `count.mjs`     | Rebuilds each count from its vote table, and reads the data files.      |
| `check.mjs`     | Hand-worked checks, plus every election: count, ballots, no lost votes. |
| `make_index.py` | Builds `elections.csv`, the list of elections.                          |
