# Brief

A self-contained, terminal-based RSS reader. Add feeds, pull in new articles,
and read them — either in a popup window or read aloud via text-to-speech —
all backed by a local SQLite database.

## Features

- **Self-contained**: no separate setup script or requirements file. On
  first run, `brief` creates its own virtual environment, installs its own
  dependencies into it, and re-launches itself inside it automatically.
- **RSS feed management**: add, list, and remove feeds.
- **Article fetching**: pulls the latest entries from a feed and extracts
  clean article text via `newspaper3k`, de-duplicated by URL.
- **Direct URL saving**: save a single article without going through a feed.
- **Flexible reading modes**: view an article in a popup window, optionally
  with it read aloud via a TTS script, with automatic cleanup afterward.
- **Flexible ID selection**: commands accept a single number, a range
  (`1-3`), a comma/space-separated list (`1,3,5`), or `*` for everything.
- **Persistent storage**: the database lives at a fixed location, so it
  doesn't matter what directory you launch `brief` from.

## Installation

```bash
git clone <this-repo-url>
cd brief
chmod +x brief
```

Put it somewhere on your `$PATH`, e.g.:
```bash
ln -s "$(pwd)/brief" ~/.local/bin/brief
```

That's it — no `pip install` step required up front. The first time you run
`brief`, it will:
1. Create a virtual environment at `~/.local/share/brief/venv`
2. Install its dependencies into it (`feedparser`, `newspaper3k`,
   `lxml_html_clean`)
3. Re-launch itself inside that environment

Every run after that starts straight into the shell. If the managed
environment is ever missing a dependency (e.g. interrupted install), `brief`
detects it automatically and reinstalls on the next run — no manual cleanup
needed.

## Usage

Run `brief` to drop into its interactive shell:

```
$ brief
Welcome to Brief - CLI RSS News
Type 'help' or '?' for commands.

(Brief)
```

### Feeds
| Command | Description |
|---|---|
| `rss list` | List all configured feeds, numbered |
| `rss add <URL> [URL...]` | Add one or more feed URLs |
| `rss fetch <N> <IDS>` | Fetch the latest N entries from the given feed(s) and save them as articles |
| `rss - <IDS>` | Remove feed(s) by ID (asks for confirmation) |

### Articles
| Command | Description |
|---|---|
| `read list` | List all saved articles, numbered |
| `read <IDS>` or `read *` | Read article(s) aloud via TTS while displaying the text in a popup |
| `read show <IDS>` | Display article(s) in a popup, without audio |
| `read <IDS> -` | Same as above, then delete the article(s) afterward |
| `read - <IDS>` | Delete article(s) without reading |
| `url add <URL>` | Download, parse, and save a single article directly |

### Other
| Command | Description |
|---|---|
| `help [command]` | Show help |
| `exit` (or Ctrl+D) | Quit |

### ID Selection Syntax
Anywhere a command takes `<IDS>`, it's referring to the position number from
the most recent `rss list` or `read list`:
- a single number: `3`
- a range: `1-3`
- several, comma- or space-separated: `1,3,5` or `1 3 5`
- everything: `*`

## Requirements

- Python 3 with the `venv` module available (on Debian/Ubuntu, if missing:
  `sudo apt install python3-venv`)
- [`yad`](https://github.com/v1cont/yad) for the popup reading window
  (`sudo apt install yad`)
- A text-to-speech script at `~/.local/bin/ftts`, used when reading an
  article aloud (`read <IDS>`). Reading via `read show <IDS>` works without
  it.

## Data Storage

Everything `brief` creates lives under `~/.local/share/brief/`:
- `venv/` — the managed Python environment
- `news.db` — the SQLite database of feeds and saved articles