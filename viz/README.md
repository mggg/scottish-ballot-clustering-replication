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

## Controls

Replay restarts the current count, and the speed menu changes how fast it plays, from the next step
on. Record video replays the count and saves it as a video at the chosen speed, with no screen-sharing
prompt. It saves MP4 where the browser supports it (Safari, recent Chrome and Edge) and WebM otherwise
(Firefox). Keep the tab in front while it records, because browsers pause animations in background tabs.

## Update the election list

`elections.csv` lists every vote table with its election file, seats, and ward name. Rebuild it
after changing the data:

```sh
python3 viz/make_index.py
```
