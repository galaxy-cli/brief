import cmd
import sqlite3
import feedparser
from newspaper import Article
import subprocess
import tempfile
import os
from urllib.parse import urlparse
import re
import sys
import itertools
import importlib.util
#######################################################################
PIP_PACKAGE_TO_MODULE = {
    "feedparser": "feedparser",
    "newspaper3k": "newspaper",
    "lxml_html_clean": "lxml_html_clean", 
    "pyyaml": "yaml",
    "cssselect": "cssselect",
    "Pillow": "PIL"
}

def check_apt_dependencies(packages):
    missing = []
    for pkg in packages:
        result = subprocess.run(['dpkg', '-s', pkg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            missing.append(pkg)
    return missing

def check_pip_dependencies(packages):
    missing = []
    for pkg in packages:
        module_name = PIP_PACKAGE_TO_MODULE.get(pkg, pkg)
        if importlib.util.find_spec(module_name) is None:
            missing.append(pkg)
    return missing

def install_packages():
    apt_packages = [
        "git",
        "festival",
        "xsel",
        "python3-pip",
        "libxml2-dev",
        "libxslt1-dev",
        "python3-dev",
        "libjpeg-dev",
        "zlib1g-dev",
        "build-essential",
        "python3-gi",
        "python3-gi-cairo",
        "gir1.2-gtk-4.0"
    ]
    pip_packages = [
        "feedparser",
        "newspaper3k",
        "lxml_html_clean",
        "pyyaml",
        "cssselect",
        "Pillow"
    ]

    missing_apt = check_apt_dependencies(apt_packages)
    if missing_apt:
        print(f"Missing apt packages: {', '.join(missing_apt)}")
        yn = input("Install missing apt packages now? (Y/n) ").strip().lower()
        if yn in ["", "y", "yes"]:
            try:
                subprocess.run(['sudo', 'apt', 'update'], check=True)
                subprocess.run(['sudo', 'apt', 'install', '-y'] + missing_apt, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Failed to install apt packages: {e}")
                sys.exit(1)
        else:
            print("Cannot continue without required apt packages")
            sys.exit(1)

    missing_pip = check_pip_dependencies(pip_packages)
    if missing_pip:
        print(f"Missing pip packages: {', '.join(missing_pip)}")
        yn = input("Install missing pip packages now? (Y/n) ").strip().lower()
        if yn in ["", "y", "yes"]:
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install'] + missing_pip, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Failed to install pip packages: {e}")
                sys.exit(1)
        else:
            print("Cannot continue without required pip packages")
            sys.exit(1)
########################################################################
# --- BreifShell ---
DB_FILENAME = "news.db"
TTS_SCRIPT = os.path.expanduser("~/.local/bin/tts")
print("Welcome to brief - RSS/Article Reader with TTS") 
class BriefShell(cmd.Cmd):
    intro = "Type `cmd` to view commands and `help` or `?` for help"
    prompt = "> "
    def __init__(self):
        super().__init__()
        self.conn = sqlite3.connect(DB_FILENAME)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
        self.playback_speed = 0.5

    def create_tables(self):
        c = self.conn.cursor()
        try:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS rss_feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS article (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    content TEXT,
                    source TEXT,
                    fetched_date TEXT,
                    publish_date TEXT
                );
            """)
            self.conn.commit()
        finally:
            c.close()

    @staticmethod
    def parse_id_string(id_string):
        def parse_range(part):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = map(int, part.split("-", 1))
                    if start > end:
                        print(f"Ignoring invalid range: {part}")
                        return []
                    return range(start, end + 1)
                except ValueError:
                    print(f"Ignoring invalid range: {part}")
                    return []
            else:
                try:
                    return [int(part)]
                except ValueError:
                    print(f"Ignoring invalid ID: {part}")
                    return []
        parts = id_string.replace(',', ' ').split()
        ids = set(itertools.chain.from_iterable(map(parse_range, parts)))
        return sorted(ids)

    def renumber_rss_feed_ids(self):
        try:
            c = self.conn.cursor()
            c.execute("SELECT id FROM rss_feeds ORDER BY id ASC")
            rows = c.fetchall()
            for new_id, row in enumerate(rows, start=1):
                old_id = row['id']
                if old_id != new_id:
                    c.execute("UPDATE rss_feeds SET id = ? WHERE id = ?", (new_id, old_id))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error renumbering rss feed IDs: {e}")
            self.conn.rollback()

    def reset_sqlite_autoincrement_for_rss(self):
        try:
            c = self.conn.cursor()
            c.execute("SELECT MAX(id) AS max_id FROM rss_feeds")
            row = c.fetchone()
            max_id = row['max_id'] if row and row['max_id'] is not None else 0
            if max_id == 0:
                # If no rows, reset sequence to 0
                c.execute("DELETE FROM sqlite_sequence WHERE name='rss_feeds'")
            else:
                c.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'rss_feeds'", (max_id,))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error resetting autoincrement: {e}")
            self.conn.rollback()
########################################################################
    # --- article ---
    @staticmethod
    def write_temp_file(content):
        tf = tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', suffix=".txt")
        tf.write(content)
        tf.close()
        return tf.name

    @staticmethod
    def article_summary(a):
        site_name = urlparse(a['source']).hostname or "(unknown website)"
        site_name = site_name[4:] if site_name.startswith("www.") else site_name
        return f"{a['id']}. {a['title']} (source: {site_name})"

    @staticmethod
    def parse_id_string(id_string):
        def parse_part(part):
            part = part.strip()
            if '-' in part:
                try:
                    start, end = map(int, part.split('-', 1))
                    return range(start, end + 1) if start <= end else []
                except ValueError:
                    return []
            else:
                try:
                    return [int(part)]
                except ValueError:
                    return []
        parts = id_string.replace(',', ' ').split()
        ids = set(itertools.chain.from_iterable(map(parse_part, parts)))
        return sorted(ids)

    def do_article(self, arg):
        arg = arg.strip()
        if not arg:
            print("Usage: article list | article read ... | article open ... | article read speed <value> | article - <ids/ranges>")
            return
        arg = ' '.join(arg) if isinstance(arg, list) else arg
        args = arg.split()
        cmd = args[0]

        def renumber_article_ids():
            c = self.conn.cursor()
            c.execute("SELECT id FROM article ORDER BY id ASC")
            rows = c.fetchall()
            for new_id, row in enumerate(rows, start=1):
                old_id = row['id']
                if old_id != new_id:
                    c.execute("UPDATE article SET id = ? WHERE id = ?", (new_id, old_id))
            self.conn.commit()

        def reset_sqlite_autoincrement():
            c = self.conn.cursor()
            c.execute("DELETE FROM sqlite_sequence WHERE name = 'article'")
            self.conn.commit()

        def delete_articles(article_ids):
            c = self.conn.cursor()
            removed_any = False
            for art_id in article_ids:
                c.execute("DELETE FROM article WHERE id = ?", (art_id,))
                if c.rowcount > 0:
                    removed_any = True
                    print(f"Deleted article ID {art_id}")
                else:
                    print(f"No article found with ID {art_id}")
            if removed_any:
                self.conn.commit()
                renumber_article_ids()
                reset_sqlite_autoincrement()

        # Delete articles
        if cmd == "-":
            if len(args) < 2:
                print("Usage: article - <ids/ranges> or article - * to delete articles")
                return
            c = self.conn.cursor()
            if args[10] == "*":
                confirm = input("Are you sure to delete ALL articles? (y/n) ").lower()
                if confirm != "y":
                    print("Operation cancelled.")
                    return
                c.execute("SELECT id FROM article ORDER BY id ASC")
                articles_to_delete = [r['id'] for r in c.fetchall()]
                if not articles_to_delete:
                    print("No articles to delete.")
                    return
            else:
                articles_to_delete = self.parse_id_string(' '.join(args[1:]))
                if not articles_to_delete:
                    print("No valid article IDs to delete.")
                    return
            delete_articles(articles_to_delete)
            return

        # List articles
        if cmd == "list":
            c = self.conn.cursor()
            c.execute("SELECT id, title, source FROM article ORDER BY id ASC")
            articles = c.fetchall()
            if not articles:
                print("No articles saved yet")
                return
            print('\n'.join(map(self.article_summary, articles)))
            return

        # Read article
        if cmd == "read":
            delete_after_read = False
            if len(args) > 1 and args[-1] == "-":
                delete_after_read = True
                args = args[:-1]
            if len(args) > 1 and args[1].lower() == "speed":
                if len(args) < 3:
                    print("Usage: article read speed <value>")
                    return
                try:
                    speed = float(args)
                    if speed <= 0:
                        raise ValueError()
                    self.playback_speed = speed
                    print(f"Playback speed set to {speed}x")
                except ValueError:
                    print("Invalid speed value. Please enter a positive number.")
                return
            ids_args = args[1:]
            if not ids_args:
                print("Usage: article read <ids/ranges> | article read *")
                return
            c = self.conn.cursor()
            if ids_args == "*":
                c.execute("SELECT id FROM article ORDER BY id ASC")
                articles_to_read = [r['id'] for r in c.fetchall()]
                if not articles_to_read:
                    print("No articles available to read.")
                    return
            else:
                articles_to_read = self.parse_id_string(' '.join(ids_args))
                if not articles_to_read:
                    print("No valid article IDs to read.")
                    return
            if not hasattr(self, 'playback_speed'):
                self.playback_speed = 1.0
            total = len(articles_to_read)
            for idx, article_id in enumerate(articles_to_read, 1):
                c.execute("SELECT title, source, content, publish_date FROM article WHERE id = ?", (article_id,))
                row = c.fetchone()
                if not row:
                    print(f"No article found with ID {article_id}")
                    continue
                title, source, content, _ = row
                site_name = urlparse(source).hostname or "(unknown website)"
                site_name = site_name[4:] if site_name.startswith("www.") else site_name
                if not content or content.strip() == "":
                    print(f"Article ID {article_id} content empty")
                    continue
                print(f"Title: {title}")
                print(f"Website: {site_name}")
                print(f"Reading article {idx} / {total} (ID {article_id})...")
                temp_filename = self.write_temp_file(content)
                try:
                    subprocess.run(["xdg-open", temp_filename], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                    subprocess.run([
                        TTS_SCRIPT,
                        "--file",
                        temp_filename,
                        "--speed", str(self.playback_speed)
                    ])
                except subprocess.CalledProcessError as e:
                    print(f"TTS playback failed for article {article_id}: {e}")
                finally:
                    os.remove(temp_filename)
                if delete_after_read:
                    delete_articles([article_id])
            return

        # Open article
        if cmd == "open":
            ids_args = args[1:]
            if not ids_args:
                print("Usage: article open <ids/ranges>")
                return
            c = self.conn.cursor()
            if ids_args == "*":
                c.execute("SELECT id FROM article ORDER BY id ASC")
                articles_to_open = [r['id'] for r in c.fetchall()]
                if not articles_to_open:
                    print("No articles to open.")
                    return
            else:
                articles_to_open = self.parse_id_string(' '.join(ids_args))
                if not articles_to_open:
                    print("No valid article IDs to open.")
                    return
            total = len(articles_to_open)
            for idx, article_id in enumerate(articles_to_open, 1):
                c.execute("SELECT title, source, content FROM article WHERE id = ?", (article_id,))
                row = c.fetchone()
                if not row:
                    print(f"No article found with ID {article_id}")
                    continue
                title, source, content = row
                if not content or content.strip() == "":
                    print(f"Article ID {article_id} content empty")
                    continue
                print(f"Opening article {idx} / {total} (ID {article_id}): {title}")
                temp_filename = self.write_temp_file(content)
                try:
                    subprocess.run(["xdg-open", temp_filename], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                except subprocess.CalledProcessError as e:
                    print(f"Failed to open article {article_id}: {e}")
            return

        print(f"Unknown article command '{cmd}'. Available commands: list, read, open, -")
########################################################################
    # --- rss ---
    def do_rss(self, arg):
        arg = arg.strip()
        if not arg:
            print("Usage: rss add <url> | rss fetch <num> <feed_id|*> | rss list | rss order <feed_id> <feed_id> | rss - <ids>")
            return
        arg = ' '.join(arg) if isinstance(arg, list) else arg
        args = arg.split()
        cmd = args[0]

        c = self.conn.cursor()

        # Delete RSS feeds
        if cmd == "-":
            if len(args) < 2:
                print("Usage: rss - <ids> (comma separated supported)")
                return
            feed_ids_raw = [s.strip() for s in ' '.join(args[1:]).split(',') if s.strip()]
            feed_ids = []
            for id_str in feed_ids_raw:
                try:
                    feed_ids.append(int(id_str))
                except ValueError:
                    print(f"Invalid feed ID: {id_str}")
            if not feed_ids:
                print("No valid feed IDs provided to remove.")
                return
            removed_any = False
            for feed_id in feed_ids:
                c.execute("DELETE FROM rss_feeds WHERE id = ?", (feed_id,))
                if c.rowcount > 0:
                    print(f"Removed RSS feed ID {feed_id}")
                    removed_any = True
                else:
                    print(f"No RSS feed found with ID {feed_id}")
            if removed_any:
                self.conn.commit()
                self.renumber_rss_feed_ids()
                self.reset_sqlite_autoincrement_for_rss()
            return

        # Add RSS feed
        if cmd == "add":
            if len(args) < 2:
                print("Usage: rss add <url>")
                return
            url = args[1]
            feed = feedparser.parse(url)
            if feed.bozo or not hasattr(feed, 'feed') or not feed.feed:
                print(f"Invalid RSS feed URL or unable to parse feed: {url}")
                return
            try:
                c.execute("SELECT id FROM rss_feeds WHERE url = ?", (url,))
                if c.fetchone() is not None:
                    print("You have already added this RSS feed")
                    return
                c.execute("INSERT INTO rss_feeds (url) VALUES (?)", (url,))
                self.conn.commit()
                print(f"Added RSS feed: {url}")
            except sqlite3.Error as e:
                print(f"Database error: {e}")
            return

        # Fetch RSS feed articles
        if cmd == "fetch":
            if len(args) != 3:
                print("Usage: rss fetch <num> <feed_id|*>")
                return
            num_str, feed_id_str = args[1], args[2]
            try:
                num_to_fetch = int(num_str)
                if num_to_fetch < 1:
                    raise ValueError()
            except ValueError:
                print("Specify a number greater than 0, e.g. rss fetch 5 1 or rss fetch 3 *")
                return

            def fetch_from_feed(feed_id, feed_url):
                parsed = feedparser.parse(feed_url)
                count = 0
                for entry in parsed.entries[:num_to_fetch]:
                    url = entry.link
                    if url:
                        c.execute("SELECT id FROM article WHERE url = ?", (url,))
                        if c.fetchone():
                            print(f"Already have article: {url}")
                            continue
                        try:
                            article = Article(url)
                            article.download()
                            article.parse()
                            title = article.title
                            content = article.text
                            fetched_date = article.publish_date.isoformat() if article.publish_date else None
                            c.execute("""
                            INSERT INTO article (url, title, content, source, fetched_date)
                            VALUES (?, ?, ?, ?, ?)
                            """, (url, title, content, feed_url, fetched_date))
                            self.conn.commit()
                            print(f"Saved article: {title}")
                            count += 1
                        except Exception as e:
                            print(f"Failed to parse article {url}: {e}")
                if count == 0:
                    print("No new articles were added.")
                else:
                    print(f"Finished fetching {count} new articles for feed ID {feed_id}.")

            if feed_id_str == "*":
                c.execute("SELECT id, url FROM rss_feeds ORDER BY id ASC")
                feeds = c.fetchall()
                if not feeds:
                    print("No RSS feeds to fetch from")
                    return
                for feed in feeds:
                    print(f"Fetching {num_to_fetch} entries from feed ID {feed['id']}: {feed['url']}")
                    fetch_from_feed(feed['id'], feed['url'])
            else:
                try:
                    feed_id = int(feed_id_str)
                except ValueError:
                    print("Feed ID must be an integer or '*'.")
                    return
                c.execute("SELECT url FROM rss_feeds WHERE id = ?", (feed_id,))
                feed = c.fetchone()
                if not feed:
                    print(f"No RSS feed found with ID {feed_id}")
                    return
                print(f"Fetching {num_to_fetch} entries from feed ID {feed_id}: {feed['url']}")
                fetch_from_feed(feed_id, feed['url'])
            return

        # List RSS feeds
        if cmd == "list":
            c.execute("SELECT id, url FROM rss_feeds ORDER BY id ASC")
            feeds = c.fetchall()
            if not feeds:
                print("No RSS feeds added yet")
                return
            for f in feeds:
                print(f"{f['id']}. {f['url']}")
            return

        # Sort order of RSS feed
        if cmd == "order":
            if len(args) != 3:
                print("Usage: rss order <from_id> <to_id>")
                return
            try:
                from_id, to_id = int(args[1]), int(args[2])
            except ValueError:
                print("Feed IDs must be integers.")
                return
            c.execute("SELECT id FROM rss_feeds WHERE id IN (?, ?)", (from_id, to_id))
            rows = c.fetchall()
            if len(rows) != 2:
                print("Both feed IDs must exist.")
                return
            try:
                TEMP_ID_1 = -9999
                TEMP_ID_2 = -9998
                c.execute("UPDATE rss_feeds SET id = ? WHERE id = ?", (TEMP_ID_1, from_id))
                if from_id < to_id:
                    c.execute("""
                        UPDATE rss_feeds
                        SET id = id - 1
                        WHERE id > ? AND id <= ?
                    """, (from_id, to_id))
                elif from_id > to_id:
                    c.execute("""
                        UPDATE rss_feeds
                        SET id = id + 1
                        WHERE id >= ? AND id < ?
                    """, (to_id, from_id))
                c.execute("UPDATE rss_feeds SET id = ? WHERE id = ?", (to_id, TEMP_ID_1))
                self.conn.commit()
                print(f"Moved RSS feed ID {from_id} to position {to_id}")
                self.renumber_rss_feed_ids()
                self.reset_sqlite_autoincrement_for_rss()
            except sqlite3.Error as e:
                print(f"Database error while reordering: {e}")
                self.conn.rollback()
            return

    print("Unknown rss command. Available: add, fetch, list, order, -")
########################################################################
    # --- url ---
    def do_url(self, arg):
        """URL command with subcommands: url add <article_url>"""
        arg = ' '.join(arg) if isinstance(arg, list) else arg
        args = arg.split()
        if not args:
            print("Usage: url add <article_url>")
            return
        cmd = args[0]

        # Add URL
        if cmd == "add":
            if len(args) < 2:
                print("Usage: url add <article_url>")
                return
            url = args[1]
            c = self.conn.cursor()
            c.execute("SELECT id FROM article WHERE url = ?", (url,))
            if c.fetchone():
                print(f"Already have article: {url}")
                return
            try:
                article = Article(url)
                article.download()
                article.parse()
                title = article.title
                content = article.text
                fetched_date = article.publish_date.isoformat() if article.publish_date else None
                c.execute("""
                    INSERT INTO article (url, title, content, source, fetched_date)
                    VALUES (?, ?, ?, ?, ?)
                """, (url, title, content, url, fetched_date))
                self.conn.commit()
                print(f"Saved article: {title}")
            except Exception as e:
                print(f"Failed to parse article {url}: {e}")
        else:
            print("Unknown url command. Available: add")
########################################################################
    # --- cmd ---
    def do_cmd(self, arg):
        """Lists all available commands"""
        commands = ["article\n", "rss\n", "url\n", "exit"]
        print(''.join(commands))

    # --- help ---
    def do_help(self, arg):
        """Shows help for commands"""
        if arg:
            return super().do_help(arg)
        else:
            commands = [cmd[3:] for cmd in dir(self) if cmd.startswith('do_')]
            max_len = max(len(cmd) for cmd in commands)
            for cmd in sorted(commands):
                func = getattr(self, 'do_' + cmd)
                doc = func.__doc__.strip().split('\n')[0] if func.__doc__ else ''
                print(f"{cmd.ljust(max_len)} {doc}")

    # --- exit ---
    def do_exit(self, arg):
        """Exit the CLI"""
        print("Goodbye!")
        self.conn.close()
        return True
########################################################################
if __name__ == '__main__':
    install_packages()
    shell = BriefShell()
    while True:
        try:
            shell.cmdloop()
            break
        except KeyboardInterrupt:
            print("\nPress 'exit' to quit.")