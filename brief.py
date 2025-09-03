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

########################################################################
def check_apt_dependencies(packages):
    missing = []
    return missing

def check_pip_dependencies(packages):
    missing = []
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
        "build-essential"
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
        yn = input("Install missing apt packages now? (y/n) ").strip()
        if yn.lower() in ["", "y", "yes"]:
            subprocess.run(['sudo', 'apt', 'update'])
            subprocess.run(['sudo', 'apt', 'install', '-y'] + missing_apt)
        else:
            print("Cannot continue without required apt packages")
            sys.exit(1)
    else:
        pass
    missing_pip = check_pip_dependencies(pip_packages)
    if missing_pip:
        print(f"Missing pip packages: {', '.join(missing_pip)}")
        yn = input("Install missing pip packages now? [Y/n] ").strip()
        if yn.lower() in ["", "y", "yes"]:
            subprocess.run([sys.executable, '-m', 'pip', 'install'] + missing_pip)
        else:
            print("Cannot continue without required pip packages")
            sys.exit(1)
    else:
        pass
########################################################################
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
        c.execute("""
            CREATE TABLE IF NOT EXISTS rss_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS article (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                title TEXT,
                content TEXT,
                source TEXT,
                fetched_date TEXT,
                publish_date TEXT
            )
        """)
        self.conn.commit()

    @staticmethod
    def parse_id_string(id_string):
        ids = set()
        parts = [part.strip() for part in id_string.split(',')]
        for part in parts:
            if '-' in part:
                try:
                    start, end = map(int, part.split('-', 1))
                    if start > end:
                        print(f"Ignoring invalid range: {part}")
                        continue
                    ids.update(range(start, end + 1))
                except ValueError:
                    print(f"Ignoring invalid range: {part}")
            else:
                try:
                    i = int(part)
                    ids.add(i)
                except ValueError:
                    print(f"Ignoring invalid article ID: {part}")
        return sorted(ids)

    def renumber_rss_feed_ids(self):
        c = self.conn.cursor()
        c.execute("SELECT id FROM rss_feeds ORDER BY id ASC")
        rows = c.fetchall()
        for new_id, row in enumerate(rows, start=1):
            old_id = row['id']
            if old_id != new_id:
                c.execute("UPDATE rss_feeds SET id = ? WHERE id = ?", (new_id, old_id))
        self.conn.commit()

    def reset_sqlite_autoincrement_for_rss(self):
        c = self.conn.cursor()
        c.execute("SELECT MAX(id) AS max_id FROM rss_feeds")
        row = c.fetchone()
        max_id = row['max_id'] if row and row['max_id'] is not None else 0
        c.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'rss_feeds'", (max_id,))
        self.conn.commit()
########################################################################
    # --- Article ---
    def do_article(self, arg):
        """
    Manage article:
article list                        - list all articles
article read <ids/ranges>           - read specified articles and ranges (e.g., 1-3,5,7-10)
article read speed <value>          - set playback speed
article read <ids/ranges> -         - read then remove specified articles
article read * -                    - read all articles then delete all (with confirmation)
article - <ids/ranges>              - delete specified articles without reading
article - *                         - delete all articles (with confirmation)
        """
        arg = arg.strip()
        if not arg:
            print("Usage: article list | article read ... | article read speed <value> | article - <ids/ranges>")
            return

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

        if cmd == "-":
            if len(args) < 2:
                print("Usage: article - <ids/ranges> or article - * to delete articles")
                return
            c = self.conn.cursor()
            if args[1] == "*":
                confirm = input("Are you sure to delete ALL articles? (y/n) ").lower()
                if confirm != "y":
                    print("Operation cancelled.")
                    return
                c.execute("SELECT id FROM article ORDER BY id ASC")
                rows = c.fetchall()
                articles_to_delete = [r['id'] for r in rows]
                if not articles_to_delete:
                    print("No articles to delete.")
                    return
            else:
                id_string = ' '.join(args[1:])
                articles_to_delete = self.parse_id_string(id_string)
                if not articles_to_delete:
                    print("No valid article IDs to delete.")
                    return
            delete_articles(articles_to_delete)
            return

        if cmd == "list":
            c = self.conn.cursor()
            c.execute("SELECT id, title, source FROM article ORDER BY id ASC")
            articles = c.fetchall()
            if not articles:
                print("No articles saved yet")
                return
            for a in articles:
                site_name = urlparse(a['source']).hostname or "(unknown website)"
                if site_name.startswith("www."):
                    site_name = site_name[4:]
                print(f"{a['id']}. {a['title']} (source: {site_name})")
            return

        if cmd == "read":
            # Detect and remove trailing '-' flag
            delete_after_read = False
            if len(args) > 1 and args[-1] == "-":
                delete_after_read = True
                args = args[:-1]

            # Handle speed command first
            if len(args) > 1 and args[1].lower() == "speed":
                if len(args) < 3:
                    print("Usage: article read speed <value>")
                    return
                try:
                    speed = float(args[2])
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
            if ids_args[0] == "*":
                c.execute("SELECT id FROM article ORDER BY id ASC")
                rows = c.fetchall()
                articles_to_read = [r['id'] for r in rows]
                if not articles_to_read:
                    print("No articles available to read.")
                    return
            else:
                id_string = ' '.join(ids_args)
                articles_to_read = self.parse_id_string(id_string)
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
                title = row['title']
                source = row['source']
                site_name = urlparse(source).hostname or "(unknown website)"
                if site_name.startswith("www."):
                    site_name = site_name[4:]
                content = row['content']
                if not content or content.strip() == "":
                    print(f"Article ID {article_id} content empty")
                    continue
                print(f"Title: {title}")
                print(f"Website: {site_name}")
                print(f"Reading article {idx} / {total} (ID {article_id})...")
                with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', suffix=".txt") as tf:
                    tf.write(content)
                    temp_filename = tf.name
                try:
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

        print(f"Unknown article command '{cmd}'. Available commands: list, read, -")
########################################################################
    # --- RSS commands ---
    def do_rss(self, arg):
        "RSS feed commands"
        args = arg.split()
        if not args or args[0] == "":
            print("Usage: rss add <feed_url> | rss fetch <feed_id> <number> | rss list | rss - <id> [<id> ...]")
            return
        cmd = args[0]

        if cmd == "-":
            if len(args) < 2:
                print("Usage: rss - <feed_id> [<feed_id> ...] (comma separated also supported)")
                return
            
            feed_id_str = ' '.join(args[1:])
            feed_ids_raw = [s.strip() for s in feed_id_str.split(',') if s.strip()]
            
            feed_ids = []
            for id_str in feed_ids_raw:
                try:
                    feed_ids.append(int(id_str))
                except ValueError:
                    print(f"Invalid feed ID: {id_str}")
            if not feed_ids:
                print("No valid feed IDs provided to remove.")
                return
            
            c = self.conn.cursor()
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

        # add
        if cmd == "add":
            if len(args) < 2:
                print("Usage: rss add <feed_url>")
                return
            url = args[1]
            try:
                c = self.conn.cursor()
                c.execute("INSERT INTO rss_feeds (url) VALUES (?)", (url,))
                self.conn.commit()
                print(f"Added RSS feed: {url}")
            except sqlite3.OperationalError as e:
                print(f"Database write error: {e}")
            except sqlite3.Error as e:
                print(f"Database error: {e}")
            return

        # fetch
        if cmd == "fetch":
            if len(args) != 3:
                print("Usage: rss fetch <feed_id|*> <number_of_articles>")
                return
            
            feed_id_str = args[1]
            num_to_fetch_str = args[2]

            try:
                num_to_fetch = int(num_to_fetch_str)
                if num_to_fetch < 1:
                    raise ValueError()
            except ValueError:
                print("Please specify a number greater than 0, e.g. rss fetch 1 4 or rss fetch * 3")
                return

            c = self.conn.cursor()

            if feed_id_str == "*":
                c.execute("SELECT id, url FROM rss_feeds ORDER BY id ASC")
                feeds = c.fetchall()
                if not feeds:
                    print("No RSS feeds to fetch from")
                    return
                for feed in feeds:
                    print(f"Fetching {num_to_fetch} entries from feed ID {feed['id']}: {feed['url']}")
                    parsed = feedparser.parse(feed['url'])
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
                                """, (url, title, content, feed['url'], fetched_date))
                                self.conn.commit()
                                print(f"Saved article: {title}")
                                count += 1
                            except Exception as e:
                                print(f"Failed to parse article {url}: {e}")
                    if count == 0:
                        print("No new articles were added for this feed.")
                    else:
                        print(f"Finished fetching {count} new articles for this feed.")
                return
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
                parsed = feedparser.parse(feed['url'])
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
                            """, (url, title, content, feed['url'], fetched_date))
                            self.conn.commit()
                            print(f"Saved article: {title}")
                            count += 1
                        except Exception as e:
                            print(f"Failed to parse article {url}: {e}")
                if count == 0:
                    print("No new articles were added.")
                else:
                    print(f"Finished fetching {count} new articles.")
            return

        # List command
        if cmd == "list":
            c = self.conn.cursor()
            c.execute("SELECT id, url FROM rss_feeds ORDER BY id ASC")
            feeds = c.fetchall()
            if not feeds:
                print("No RSS feeds added yet")
                return
            for f in feeds:
                print(f"{f['id']}. {f['url']}")
            return

        print("Unknown rss command. Available: add, fetch, list, -")
########################################################################
    # --- Manual URL add command ---
    def do_url(self, arg):
        """URL command with subcommands: url add <article_url>"""
        args = arg.split()
        if not args:
            print("Usage: url add <article_url>")
            return
        cmd = args[0]
        
        # add
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
    # --- Lists all commands that can be done ---
    def do_cmd(self, arg):
        """Lists all available commands"""
        commands = ["article\n", "rss\n", "url\n", "exit"]
        print(''.join(commands))
########################################################################
    # --- Shows help commands ---
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
########################################################################
    # --- Exit the script ---
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