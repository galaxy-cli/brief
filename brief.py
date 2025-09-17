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
import datetime
from dateutil import parser as dateutil_parser


PIP_PACKAGE_TO_MODULE = {"feedparser": "feedparser", "newspaper3k": "newspaper", "lxml_html_clean": "lxml_html_clean",  "pyyaml": "yaml", "cssselect": "cssselect", "Pillow": "PIL", "python-dateutil": "dateutil"}

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
    apt_packages = ["git", "festival", "xsel","python3-pip", "libxml2-dev", "libxslt1-dev", "python3-dev", "libjpeg-dev", "zlib1g-dev", "build-essential", "python3-gi", "python3-gi-cairo", "gir1.2-gtk-4.0"]
    pip_packages = ["feedparser","newspaper3k", "lxml_html_clean", "pyyaml", "cssselect", "Pillow", "python-dateutil"]

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

    def reset_sqlite_autoincrement(self):
        try:
            c = self.conn.cursor()
            c.execute("SELECT MAX(id) AS max_id FROM article")
            row = c.fetchone() 
            max_id = row['max_id'] if row and row['max_id'] is not None else 0
            if max_id == 0:
                c.execute("DELETE FROM sqlite_sequence WHERE name='article'")
            else:
                c.execute("UPDATE sqlite_sequence SET seq = ? WHERE name='article'", (max_id,))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error resetting autoincrement: {e}")
            self.conn.rollback()

    def delete_rows_with_confirmation(self, table_name, display_columns, id_str, renumber_func=None, reset_func=None):
        c = self.conn.cursor()
        if id_str == "*":
            c.execute(f"SELECT id, url FROM {table_name} ORDER BY id ASC")
            rows_to_delete = c.fetchall()
            if not rows_to_delete:
                print(f"No records found to delete in {table_name}.")
                return False
        else:
            ids = self.parse_id_string(id_str)
            if not ids:
                print("No valid ID provided to delete")
                return False
            placeholders = ','.join('?' * len(ids))
            c.execute(f"SELECT id, url FROM {table_name} WHERE id IN ({placeholders}) ORDER BY id ASC", ids)
            rows_to_delete = c.fetchall()
            if not rows_to_delete:
                print(f"No records found with the specified ID in {table_name}")
                return False
        print(f"Records to be deleted from {table_name}:")
        for row in rows_to_delete:
            print(f"{row['id']}. {row['url']}")
        confirm = input("Are you sure you want to delete these records? [Y/n] ").strip().lower()
        if confirm != 'y':
            print("Deletion cancelled")
            return False
        removed_any = False
        for row in rows_to_delete:
            c.execute(f"DELETE FROM {table_name} WHERE id = ?", (row['id'],))
            if c.rowcount > 0:
                print(f"Deleted record ID {row['id']}")
                removed_any = True
            else:
                print(f"Record with ID {row['id']} was not found or already deleted")
        if removed_any:
            self.conn.commit()
            if renumber_func:
                renumber_func()
            if reset_func:
                reset_func()
        return removed_any

    @staticmethod
    def renumber_ids(table_name):
        c = shell.conn.cursor()
        c.execute(f"SELECT id FROM {table_name} ORDER BY publish_date ASC")
        rows = c.fetchall()
        offset = 10000
        for row in rows:
            old_id = row['id']
            c.execute(f"UPDATE {table_name} SET id = ? WHERE id = ?", (old_id + offset, old_id))
        for new_id, row in enumerate(rows, start=1):
            temp_id = row['id'] + offset
            c.execute(f"UPDATE {table_name} SET id = ? WHERE id = ?", (new_id, temp_id))
        shell.conn.commit()


    @staticmethod
    def write_temp_file(content):
        tf = tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', suffix=".txt")
        tf.write(content)
        tf.close()
        return tf.name

    @staticmethod
    def parse_publish_date(date_source):
        if hasattr(date_source, 'published_parsed') and date_source.published_parsed:
            try:
                dt = datetime.datetime(*date_source.published_parsed[:6]).date()
                return dt
            except Exception:
                pass
        if hasattr(date_source, 'published'):
            try:
                dt = dateutil_parser.parse(date_source.published).date()
                return dt
            except Exception:
                pass
        if hasattr(date_source, 'publish_date') and date_source.publish_date:
            try:
                dt = date_source.publish_date.date()
                return dt
            except Exception:
                pass
        return None

    @staticmethod
    def article_summary(a):
        site_name = urlparse(a['source']).hostname or "(unknown website)"
        site_name = site_name[4:] if site_name.startswith("www.") else site_name
        pub = a['publish_date'] if 'publish_date' in a.keys() else None
        pubtxt = ""
        if pub:
            try:
                dt = datetime.datetime.strptime(pub, "%Y-%m-%d")
                pubtxt = f"{dt.strftime('%m/%d/%Y')}) "
            except Exception:
                pubtxt = f"{pub} "
        return f"{a['id']}. {a['title']} (publication: {pubtxt}(source: {site_name})"





    # --- article ---
    def do_article(self, arg):
        """News article commands"""
        arg = arg.strip()
        if not arg:
            print("Usage: `article list` | `article read NUM [NUM-NUM] *` | `article open NUM [NUM-NUM]` | `article speed NUM` | `article - NUM [NUM-NUM]| *` ")
            return
        args = arg.split()
        cmd = args[0]

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
                self.renumber_ids("article")
                self.reset_sqlite_autoincrement()

        # List article
        if cmd == "list":
            if hasattr(self, "renumber_ids"):
                self.renumber_ids("article")
            if hasattr(self, "reset_sqlite_autoincrement"):
                self.reset_sqlite_autoincrement()
            c = self.conn.cursor()
            c.execute("SELECT id, title, source, publish_date FROM article ORDER BY publish_date ASC")
            articles = c.fetchall()
            if not articles:
                print("No articles saved yet")
                return
            print('\n'.join(map(self.article_summary, articles)))

        # Read article
        elif cmd == "read":
            delete_after_read = False
            if len(args) > 1 and args[-1] == "-":
                delete_after_read = True
                args = args[:-1]
            ids_args = args[1:]
            c = self.conn.cursor()
            if ids_args == ["*"]:
                c.execute("SELECT id FROM article ORDER BY publish_date ASC")
                articles_to_read = [r['id'] for r in c.fetchall()]
            else:
                id_list = []
                for part in ids_args:
                    if '-' in part:
                        try:
                            start, end = map(int, part.split('-', 1))
                            id_list.extend(range(start, end + 1))
                        except ValueError:
                            continue
                    else:
                        try:
                            id_list.append(int(part))
                        except ValueError:
                            continue
                articles_to_read = id_list
            if not articles_to_read:
                print("No valid article IDs to read")
                return
            total = len(articles_to_read)
            deleted_count = 0
            for idx, article_id in enumerate(articles_to_read, 1):
                c.execute("SELECT title, source, content, publish_date, url FROM article WHERE id = ?", (article_id,))
                row = c.fetchone()
                if not row:
                    print(f"No article found with ID {article_id}")
                    continue
                title, source, content, publish_date, url = row
                site_name = urlparse(source).hostname or "(unknown website)"
                if site_name.startswith("www."):
                    site_name = site_name[4:]
                if publish_date:
                    try:
                        dt = datetime.datetime.strptime(publish_date, "%Y-%m-%d")
                        publish_str = dt.strftime("%m/%d/%Y")
                    except Exception:
                        publish_str = publish_date
                else:
                    publish_str = "(unknown)"
                print(f"\nTitle: {title}")
                print(f"Date: {publish_str}")
                print(f"Website: {site_name}")
                if source != url:
                    print(f"Feed: {source}")
                print(f"Reading article {idx} / {total} (ID {article_id})...")
                temp_filename = self.write_temp_file(content)
                try:
                    subprocess.run(["xdg-open", temp_filename], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                    subprocess.run([
                        TTS_SCRIPT,
                        "--file", temp_filename,
                        "--speed", str(self.playback_speed)
                    ])
                except subprocess.CalledProcessError as e:
                    print(f"TTS playback failed for article {article_id}: {e}")
                finally:
                    os.remove(temp_filename)
                if delete_after_read:
                    c.execute("DELETE FROM article WHERE id = ?", (article_id,))
                    self.conn.commit()
                    deleted_count += 1
            if delete_after_read:
                self.renumber_ids("article")
                self.reset_sqlite_autoincrement()
                print(f"Deleted {deleted_count} article(s)")
            return



        # Open article
        elif cmd == "open":
            ids_args = args[1:]
            if not ids_args:
                print("Usage: `article open NUM [NUM-NUM]`")
                return
            c = self.conn.cursor()
            if ids_args == "*":
                c.execute("SELECT id FROM article ORDER BY id ASC")
                articles_to_open = [r['id'] for r in c.fetchall()]
                if not articles_to_open:
                    print("No articles to open")
                    return
            else:
                articles_to_open = self.parse_id_string(' '.join(ids_args))
                if not articles_to_open:
                    print("No valid article IDs to open")
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

        # Spead article
        elif cmd == "speed":
            args = arg.strip().split()
            if len(args) < 2:
                print("Usage: `article speed NUM`")
                return
            try:
                speed = float(args[1])
                if speed <= 0:
                    raise ValueError()
                self.playback_speed = speed
                print(f"Playback speed set to {speed}x")
            except ValueError:
                print("Invalid speed value. Please enter a positive number")

        # Delete articles
        elif cmd == "-":
            if len(args) < 2:
                print("Usage: `article - NUM [NUM-NUM] *`")
                return
            id_str = ' '.join(args[1:]).strip()
            self.delete_rows_with_confirmation(
                table_name="article",
                display_columns=["id", "title"],
                id_str=id_str,
                renumber_func=self.renumber_ids("article"),
                reset_func=getattr(self, "reset_sqlite_autoincrement", None)
            )
            return

        else:
            print(f"Unknown article command '{cmd}'. Available commands: `list`, `read`, `open`, `-`")




    # --- rss ---
    def do_rss(self, arg):
        """RSS feed commands"""
        arg = arg.strip()
        args = arg.split()
        if not arg:
            print("Usage: `rss fetch NUM [NUM-NUM] *` | `rss add URL [URL URL]` | `rss list` | `rss - NUM [NUM-NUM] *`")
            return
        cmd = args[0]
        c = self.conn.cursor()
        
        # Fetch updated articles from RSS feed
        if cmd == "fetch":
            if len(args) < 3:
                print("Usage: `rss fetch NUM [NUM...|*]`")
                return
            try:
                num_to_fetch = int(args[1])
                if num_to_fetch < 1:
                    raise ValueError()
            except ValueError:
                print("Specify a number greater than 0, e.g. rss fetch 5 1 2 or rss fetch 3 *")
                return
            feed_ids = args[2:]
            if feed_ids == ["*"]:
                positions = [int(p) for p in feed_positions]
                placeholders = ','.join('?' for _ in positions)
                c.execute(f"SELECT id, url FROM rss_feeds WHERE id IN ({placeholders}) ORDER BY id ASC", positions)
                feeds = c.fetchall()
            else:
                feed_ids_int = []
                try:
                    feed_ids_int = [int(fid) for fid in feed_ids]
                except ValueError:
                    print("Feed IDs must be integers or *")
                    return
                placeholders = ','.join('?' for _ in feed_ids_int)
                c.execute(f"SELECT id, url FROM rss_feeds WHERE id IN ({placeholders}) ORDER BY id ASC", feed_ids_int)
                feeds = c.fetchall()
            if not feeds:
                print("No matching RSS feeds found to fetch from")
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
                            publish_date_obj = self.parse_publish_date(entry)
                            publish_date = publish_date_obj.isoformat() if publish_date_obj else None
                            c.execute("""
                            INSERT INTO article (url, title, content, source, fetched_date, publish_date)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """, (url, title, content, feed_url, fetched_date, publish_date))
                            self.conn.commit()
                            print(f"Saved article: {title}")
                            count += 1
                        except Exception as e:
                            print(f"Failed to parse article {url}: {e}")
                if count == 0:
                    print(f"No new articles were added for feed ID {feed_id}")
                else:
                    print(f"Finished fetching {count} new articles for feed ID {feed_id}.")
            for feed in feeds:
                print(f"Fetching {num_to_fetch} entries from feed ID {feed['id']}: {feed['url']}")
                fetch_from_feed(feed['id'], feed['url'])
            return

        # Add RSS feed
        elif cmd == "add":
            if len(args) < 2:
                print("Usage: rss add URL [URL...]")
                return
            urls_to_add = args[1:]
            for url in urls_to_add:
                feed = feedparser.parse(url)
                if feed.bozo or not hasattr(feed, 'feed') or not feed.feed:
                    print(f"Invalid RSS feed URL or unable to parse feed: {url}")
                    continue
                try:
                    c.execute("SELECT id FROM rss_feeds WHERE url = ?", (url,))
                    if c.fetchone() is not None:
                        print(f"You have already added this RSS feed: {url}")
                        continue
                    c.execute("INSERT INTO rss_feeds (url) VALUES (?)", (url,))
                    inserted_id = c.lastrowid
                    c.execute("UPDATE rss_feeds SET id = ? WHERE id = ?", (inserted_id, inserted_id))
                    self.conn.commit()
                    print(f"Added RSS feed: {url}")
                except sqlite3.Error as e:
                    print(f"Database error adding {url}: {e}")
            return

        # List RSS feed
        elif cmd == "list":
            c.execute("SELECT id, url FROM rss_feeds ORDER BY id ASC")
            feeds = c.fetchall()
            for feed in feeds:
                print(f"{feed['id']}. {feed['url']}")
            return

        # Delete RSS feeds
        elif cmd == "-":
            if len(args) < 2:
                print("Usage: `rss - ID` (comma separated supported) or `rss - *`")
                return
            id_str = ' '.join(args[1:]).strip()
            self.delete_rows_with_confirmation(
                table_name="rss_feeds",
                display_columns=["id", "url"],
                id_str=id_str,
                renumber_func=self.renumber_ids("rss_feeds"),
                reset_func=getattr(self, "reset_sqlite_autoincrement", None)
            )
            return

        else:
            print("Unknown `rss` command. Available: `fetch`, `add`, `list`, `-`")




    # --- url ---
    def do_url(self, arg):
        """URL commands"""
        arg = ' '.join(arg) if isinstance(arg, list) else arg
        args = arg.split()
        if not args:
            print("Usage: `url add URL`")
            return
        cmd = args[0]

        # Add URL
        if cmd == "add":
            if len(args) < 2:
                print("Usage: `url add URL`")
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
                publish_date_obj = self.parse_publish_date(article)
                publish_date = publish_date_obj.isoformat() if publish_date_obj else None
                c.execute("""
                INSERT INTO article (url, title, content, source, fetched_date, publish_date)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (url, title, content, url, fetched_date, publish_date))
                self.conn.commit()
                print(f"Saved article: {title}")
            except Exception as e:
                print(f"Failed to parse article {url}: {e}")
        else:
            print("Unknown `url` command. Available: `add`")




    # --- cmd ---
    def do_cmd(self, arg):
        """Lists all available commands"""
        commands = ["article\n", "rss\n", "url"]
        print(''.join(commands))




    # --- help ---
    def do_help(self, arg):
        """Shows help for commands"""
        if arg:
            return super().do_help(arg)
        else:
            commands = [cmd[3:] for cmd in dir(self) if cmd.startswith('do_')]
            order = ['article', 'rss', 'url', 'cmd', 'help', 'exit']
            def sort_key(cmd):
                try:
                    return order.index(cmd)
                except ValueError:
                    return len(order) + ord(cmd[0])
            commands_sorted = sorted(commands, key=sort_key)
            max_len = max(len(cmd) for cmd in commands_sorted)
            for cmd in commands_sorted:
                func = getattr(self, 'do_' + cmd)
                doc = func.__doc__.strip().split('\n')[0] if func.__doc__ else ''
                print(f"{cmd.ljust(max_len)} {doc}")



    # --- exit ---
    def do_exit(self, arg):
        """Exit the shell"""
        print("Goodbye!")
        self.conn.close()
        return True




if __name__ == '__main__':
    install_packages()
    shell = BriefShell()
    while True:
        try:
            shell.cmdloop()
            break
        except KeyboardInterrupt:
            print("\nPress 'exit' to quit")