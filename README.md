# Brief - RSS/Article Reader with TTS

A command-line tool that lets you collect, manage, and read news articles and RSS feeds.  
It supports:

- Subscribing to RSS feeds
- Fetching and saving articles
- Adding articles by direct URL
- Listing, reading, and removing saved articles
- Text-to-speech (TTS) playback using Festival + MPV
- Command-driven interactive shell (like `sqlite3` or `ftp` CLI utilities)

This is ideal for users who want a lightweight, voice-assisted RSS/article reader.

---

## Requirements

The script checks for and optionally installs the following dependencies:

- [`git`](https://git-scm.com/)
- [`festival`](https://www.cstr.ed.ac.uk/projects/festival/) – TTS engine
- [`xsel`](https://linux.die.net/man/1/xsel) – X11 clipboard tool
- [`lame`](http://lame.sourceforge.net/) – MP3 encoder
- [`mpv`](https://mpv.io/) – multimedia player

Python dependencies:

- `feedparser` – for parsing RSS feeds
- `newspaper3k` – for downloading and parsing full articles

Install Python requirements:

- `pip install feedparser newspaper3k`

---

## Getting Started

Clone the repository and run the script:

- `git clone https://github.com/yourusername/brief`
- `cd brief`
- `python3 brief.py`

When you start Brief, it will:

1. Check for required system packages (`git`, `festival`, `xsel`, `lame`, `mpv`).
2. Prompt you to install missing ones (if using a system with `apt`).
3. Create a SQLite database (`news.db`) to store feeds and articles.

---

## Usage

When launched, Brief enters an **interactive shell**:

Welcome to brief - RSS/Article Reader with TTS
Type cmd to view commands and help or ? for help

### Available Commands

#### Article Commands
- `article list`
List all saved articles

- `article read <ids/ranges>`
Read specified articles (example: article read 1-3,5,7-10)

- `article read *`
Read ALL articles

- `article read speed <value>`
Set playback speed (e.g., article read speed 1.5)

- `article <ids/ranges> -`
Remove specific articles

- `article * -`
Remove ALL articles

#### RSS Commands
- `rss add <feed_url>`
Add a new RSS feed

- `rss list`
List all RSS feeds

- `rss fetch <feed_id> <number>`
Fetch <number> of articles from given feed

- `rss fetch * <number>`
Fetch from ALL feeds

- `rss - <feed_id>`
Remove a feed by ID

#### URL Commands
- `url add <article_url>`
Add an article manually via its direct URL

#### Utility Commands
- `cmd`
List all available commands

- `help`
Show help for commands

- `exit`
Exit the program

---

## Text-to-Speech (TTS)

Articles are read aloud using **Festival** and **MPV**.  
Playback speed can be adjusted via:

- `article read speed 1.5`

Default is `0.5x` (slower than normal); values >1.0 make speech faster.

---

## Database

Brief uses **SQLite** (`news.db`) to store:

- RSS Feeds (`rss_feeds` table)
- Saved Articles (`article` table)

IDs are automatically re-numbered when feeds/articles are removed.

---

## Notes

- **Linux only (tested with apt-based systems)**: The dependency installer assumes Debian/Ubuntu (`apt`).  
  If you're on Fedora, Arch, macOS, or BSD, you'll need to manually install the packages.
- Festival voices can be changed/configured in your system's Festival installation.
- `mpv3` script (`~/.local/bin/mpv3`) is expected to exist to handle TTS playback.  
  Update the `MPV3_SCRIPT` path in the code if needed.

---

## Example Session

- `rss add https://news.ycombinator.com/rss`
Added RSS feed: https://news.ycombinator.com/rss

- `rss list`
https://news.ycombinator.com/rss

- `rss fetch 1 3`
Fetching 3 entries from feed ID 1: https://news.ycombinator.com/rss
Saved article: Interesting Tech Post
Saved article: Another Great Story
Saved article: Latest Updates

- `article list`
Interesting Tech Post (source: https://news.ycombinator.com/rss)
Another Great Story (source: https://news.ycombinator.com/rss)
Latest Updates (source: https://news.ycombinator.com/rss)

`article read 1-2`
Reading article 1 / 2 (ID 1)...

---

## License

This project is licensed under the MIT License. See the LICENSE file for details.

---

## Author & Contact

**galaxy-cli**

GitHub: [https://github.com/galaxy-cli/brief](https://github.com/galaxy-cli/brief)
