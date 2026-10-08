# STV count viz

Animates the single transferable vote (STV) count of every Scottish council election in
`data/scot-elex/`, counting each one from its ballots. It is plain HTML and JavaScript with no build
step or dependencies.

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
party's colour: Labour, Conservative, Liberal Democrat, Green and SNP have their own, and every
other label, independents included, shares the independents' teal. Later candidates sharing a colour
get lighter shades, in ballot order (alphabetical by surname).

The page follows every ballot through the count, so each chunk of a bar shows which candidate those
voters ranked first, even after their votes have passed through other candidates. When votes move,
they fly from the candidate passing them on, coloured by the same first choices. A winner's bar
turns grey, with a strip along its bottom showing their voters' first choices. Votes that can't
transfer collect in a "Non-transferable" row at the bottom, hatched in the colour of the voters'
first choice. Hover over or tap a row for a table of its votes by first choice.

The page counts each election itself from the ballots in `data/scot-elex/`, following Scotland's
rules. The quota is the votes divided by one more than the seats, rounded down, plus one. Surpluses
move one at a time, earliest winner first, then the largest; every ballot the winner holds moves on
at a transfer value rounded down to five decimal places. With no surplus waiting, the candidate in
last place is eliminated and all their ballots move on. Ties go by the earliest round where the
candidates differed. Because every ballot keeps its first preference as it moves, the page knows
where each vote started.

The published vote tables in `data/scottish_vote_tables/` serve as a check: the page's counts match
all 1,070 of them exactly, round by round. `node viz/check.mjs` re-runs that comparison using the
page's own code, along with its built-in self-checks, and fails if anything differs.

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

`elections.csv` lists every election with its election file, seats, ward name, and full candidate
names. The names come from the vote tables, because the election files cut some short at hyphens and
accents. After changing the data, rebuild the list and re-check the counts:

```sh
python3 viz/make_index.py
node viz/check.mjs
```
