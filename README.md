# Brief

A minimal, lightning-fast CLI RSS reader and article scraper that pipes full-text content into a clean visual window (`yad`) and fluidly converts text to speech (`ftts`).

## Features

* **Memory Pipes**: Streams article data straight to UI windows without creating temporary files on your disk.
* **Implicit Commands**: Type `read 1` or `read *` directly—no action keywords needed.
* **Batch Operations**: Read arrays or entire lists sequentially, with automatic deletion modifiers (e.g., `read * -`).
* **Instant Skip**: Closing the text window instantly terminates the speech background worker and queues up the next story.

---

## Dependencies

Ensure you have the core Python modules and Linux utility tools installed before starting:

```bash
pip install feedparser newspaper3k
sudo apt install yad
```

---

## Installation & Shortcuts

Run the script seamlessly from any folder on your machine by setting up a terminal shell alias. 

1. Open your configuration profile:
   ```bash
   nano ~/.bashrc
   ```
2. Paste your direct executable link at the bottom of the file (replace with your exact path):
   ```bash
   alias brief="\$HOME/.venv/bin/python3 /path/to/your/brief_script.py"
   ```
3. Reload your terminal settings:
   ```bash
   source ~/.bashrc
   ```

---

## Command Reference ⌨

Launch the shell by typing `brief` in your terminal workspace.

### RSS Feeds (`rss`)
* `rss add <URL>` — Add a new feed to the local SQLite storage.
* `rss list` — View all subscribed feed URLs.
* `rss fetch <NUM> <IDs/*>` — Fetch the top X articles from chosen feeds or all (`*`).
* `rss - <IDs>` — Permanently unsubscribe from a feed database index.

### Reading Articles (`read`)
* `read list` — Display all gathered articles sequentially.
* `read <ID>` — Launch visual reader window and start the speech text engine.
* `read *` — Queue and read all unread collected articles back-to-back.
* `read show <ID>` — Open the reading display window quietly without triggering audio.
* `read <ID> -` — Read the article and immediately delete it upon closing the browser window.
* `read - <IDs>` — Force drop target article indexes out of the database cache.

### Web Links (`url`)
* `url add <URL>` — Instantly scrape a single detached web article link outside of your RSS lists.