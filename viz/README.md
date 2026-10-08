# STV count viz

Animates every Scottish council STV count in `data/scottish_vote_tables/`. It is plain HTML and
JavaScript with no build step or dependencies.

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

Each chunk of a bar shows the candidate who last passed those votes on, not who the voters first
chose. A winner's bar turns grey, with a strip along its bottom showing where its votes started:
each colour is the candidate those voters ranked first. Votes that can't transfer collect in a "Non-
transferable" row at the bottom, hatched in the colour of the candidate whose transfer lost them.
Hover over or tap a row for a table of who last passed its votes on.

Vote tables only hold each round's totals, so the page replays the ballots from `data/scot-elex/`
in the order the table records. A surplus moves the same fraction of every ballot the winner holds,
as Scotland's rules do. The replay reproduces every vote table in the repo to within 0.05 votes. If
a future table doesn't match, the strip is left out.

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

`elections.csv` lists every vote table with its election file, seats, and ward name. Rebuild it
after changing the data:

```sh
python3 viz/make_index.py
```
