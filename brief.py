#!/usr/bin/env python3
import cmd, sqlite3, subprocess, tempfile, os, sys, re, datetime
from urllib.parse import urlparse
from dateutil import parser as dateutil_parser
import cloudscraper
from newspaper import Article, Config

try:
    import feedparser
    from newspaper import Article
except ImportError:
    print("Error: Missing dependencies. Run 'pip install -r requirements.txt'")
    sys.exit(1)

DB_FILENAME = "news.db" 
TTS_SCRIPT = os.path.expanduser("~/.local/bin/ftts")

# --- BriefShell
class BriefShell(cmd.Cmd):
    intro, prompt = "Type `cmd` for commands.", "> "

    def __init__(self):
        super().__init__()
        self.last_list = []
        self.last_rss_list = []
        self.conn = sqlite3.connect(DB_FILENAME, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        
        # 1. Create the tables FIRST
        self.conn.execute("CREATE TABLE IF NOT EXISTS rss_feeds (id INTEGER PRIMARY KEY, url TEXT UNIQUE)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS article (id INTEGER PRIMARY KEY, url TEXT UNIQUE, title TEXT, content TEXT, source TEXT, fetched_date TEXT, publish_date TEXT)")
        
        # 2. NOW you can safely query the table
        rows = self.query("SELECT id FROM rss_feeds ORDER BY url ASC").fetchall()
        self.last_rss_list = [r['id'] for r in rows]

    def query(self, sql, params=()):
        with self.conn:
            return self.conn.execute(sql, params)

    def parse_ids(self, id_str):
        if id_str == "*":
            return self.last_list
        
        display_ids = []
        for part in id_str.replace(',', ' ').split():
            try:
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    display_ids.extend(range(start, end + 1))
                else:
                    display_ids.append(int(part))
            except ValueError: continue

        actual_db_ids = []
        for d_id in display_ids:
            if 0 < d_id <= len(self.last_list):
                actual_db_ids.append(self.last_list[d_id - 1])
        
        return actual_db_ids

    def parse_feed_ids(self, id_str):
        if id_str == "*":
            return self.last_rss_list
        
        # Standard range/comma parsing
        display_ids = []
        for part in id_str.replace(',', ' ').split():
            try:
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    display_ids.extend(range(start, end + 1))
                else:
                    display_ids.append(int(part))
            except: continue

        return [self.last_rss_list[d-1] for d in display_ids if 0 < d <= len(self.last_rss_list)]

    def delete_items(self, table, id_str):
        ids = self.parse_ids(id_str)
        if not ids: return
        print(f"Deleting IDs from {table}: {ids}")
        if input("Confirm? [y/N] ").lower() == 'y':
            self.query(f"DELETE FROM {table} WHERE id IN ({','.join(['?']*len(ids))})", ids)

    @staticmethod
    def parse_date(src):
        for attr in ['published_parsed', 'published', 'publish_date']:
            val = getattr(src, attr, None)
            if not val: continue
            try:
                return dateutil_parser.parse(str(val)).date() if not hasattr(val, 'tm_year') else datetime.datetime(*val[:6]).date()
            except: continue
        return None

    def article_summary(self, a):
        site = urlparse(a['source']).hostname.replace("www.", "")
        date_str = f"({a['publish_date']}) " if a['publish_date'] else ""
        return f"{a['id']}. {a['title']} {date_str}[{site}]"
   
    def save_article(self, url, source_url=None):
        """Bypasses 403 blocks by using cloudscraper to get HTML first."""
        try:
            if self.query("SELECT 1 FROM article WHERE url=?", (url,)).fetchone():
                print(f"  - Already have: {url}")
                return

            # 1. Use cloudscraper to bypass Cloudflare/WAF blocks
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                }
            )
            
            response = scraper.get(url, timeout=20)
            
            if response.status_code != 200:
                print(f"  ! Failed to download: Status {response.status_code}")
                return

            # 2. Pass the downloaded HTML to newspaper manually
            art = Article(url)
            art.set_html(response.text) # Manually setting the HTML skips newspaper's download()
            art.parse()
            
            # 3. Save as before
            extracted_date = self.parse_date(art)
            pub_date_str = extracted_date.isoformat() if extracted_date else None

            self.query("""INSERT INTO article 
                (url, title, content, source, publish_date) 
                VALUES (?, ?, ?, ?, ?)""", 
                (url, art.title, art.text, source_url or url, pub_date_str))
            
            print(f"  + Saved: {art.title[:50]}...")
            
        except Exception as e:
            print(f"  ! Failed to parse {url}: {e}")

    def write_temp_file(self, content):
        """Creates a temporary file with the article content and returns the path."""
        import tempfile
        tf = tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', suffix=".txt")
        tf.write(content)
        tf.close()
        return tf.name

    def refresh_rss_list(self):
        """Updates the internal ID mapping for RSS feeds."""
        rows = self.query("SELECT id FROM rss_feeds ORDER BY url ASC").fetchall()
        self.last_rss_list = [r['id'] for r in rows]

    # --- article ---
    def do_article(self, arg):
        """Usage: article [list|read|open|-] [IDs] [- (delete after read)]"""
        parts = arg.split()
        if not parts:
            print("Commands: list, read, open, -")
            return
        
        cmd = parts[0]
        args = " ".join(parts[1:])
        
        # 1. List - Restored functionality
        if cmd == "list":
            rows = self.query("SELECT * FROM article ORDER BY publish_date ASC").fetchall()
            self.last_list = [r['id'] for r in rows] # Save the order!
            
            for i, row in enumerate(rows, 1):
                # Create a copy to show the user a clean '1, 2, 3...'
                item = dict(row)
                item['id'] = i 
                print(self.article_summary(item))
            return

        # 2. Read & Open
        elif cmd in ["read", "open"]:
            cleanup_after = "-" in parts
            ids = self.parse_ids(args.replace("-", "").strip())
            
            for i, aid in enumerate(ids, 1):
                tmp = None  # <-- Initialize tmp to avoid NameError
                art = self.query("SELECT * FROM article WHERE id=?", (aid,)).fetchone()
                if not art: continue
                
                print(f"[{i}/{len(ids)}] {art['title']}")
                
                try:
                    tmp = self.write_temp_file(art['content'])
                    
                    # 1. Open window in background (Non-blocking)
                    subprocess.Popen([
                        "yad", "--text-info", 
                        "--title", art['title'], 
                        "--filename", tmp, 
                        "--width=800", "--height=600", 
                        "--wrap", "--center"
                    ], stderr=subprocess.DEVNULL)

                    # 2. Handle Read Mode (Blocking)
                    if cmd == "read":
                        subprocess.run([TTS_SCRIPT, "--file", tmp], stderr=subprocess.DEVNULL)
                    else:
                        import time
                        time.sleep(0.5) # Wait for YAD to read the file

                except KeyboardInterrupt:
                    print("\n[Stopped reading]")
                
                finally:
                    # Only attempt removal if tmp was successfully defined
                    if tmp and os.path.exists(tmp):
                        os.remove(tmp)
                    if cleanup_after: 
                        self.query("DELETE FROM article WHERE id=?", (aid,))
        # 3. Delete
        elif cmd == "-":
            self.delete_items("article", args)

    # --- rss ---
    def do_rss(self, arg):
        """Usage: rss [fetch NUM IDs|add URLs|list|- IDs]"""
        parts = arg.split()
        if not parts:
            print("Commands: fetch, add, list, -")
            return
        
        cmd = parts[0]S

        # 1. Fetch
        if cmd == "fetch" and len(parts) >= 3:
            num = int(parts[1])
            ids = self.parse_feed_ids(" ".join(parts[2:]))
            for fid in ids:
                f = self.query("SELECT * FROM rss_feeds WHERE id=?", (fid,)).fetchone()
                if not f: continue
                print(f"Fetching from: {f['url']}")
                entries = feedparser.parse(f['url']).entries[:num]
                for entry in entries:
                    self.save_article(entry.link, source_url=f['url'])

        # 2. Add
        elif cmd == "add":
            for url in parts[1:]:
                if not feedparser.parse(url).bozo:
                    self.query("INSERT OR IGNORE INTO rss_feeds (url) VALUES (?)", (url,))
                    print(f"Added: {url}")
            self.refresh_rss_list()

        # 3. List
        elif cmd == "list":
            rows = self.query("SELECT * FROM rss_feeds ORDER BY url ASC").fetchall()
            self.last_rss_list = [r['id'] for r in rows]
            if not rows:
                print("No feeds found in the database.")
            else:
                for i, r in enumerate(rows, 1):
                    print(f"{i}. {r['url']}")

        # 4. Delete RSS feeds
        elif cmd == "-":
            # 1. Translate display numbers (1, 2, 3...) to real DB IDs
            id_str = ' '.join(parts[1:]).strip()
            db_ids = self.parse_feed_ids(id_str)
            
            if not db_ids:
                print("No valid feed IDs to delete.")
                return

            # 2. Use a simplified confirmation and deletion
            print(f"Deleting feeds with DB IDs: {db_ids}")
            if input("Are you sure? [y/N] ").lower() == 'y':
                placeholders = ','.join('?' * len(db_ids))
                self.query(f"DELETE FROM rss_feeds WHERE id IN ({placeholders})", db_ids)
                print("Feeds deleted.")
                # 3. Refresh the internal tracker so the list stays in sync
                self.refresh_rss_list()

    # --- url ---
    def do_url(self, arg):
        """URL commands. Usage: `url add <URL>`"""
        parts = arg.split()
        if len(parts) < 2 or parts[0] != "add":
            print("Usage: `url add URL`")
            return

        url = parts[1]
        self.save_article(url)
   
    # --- cmd ---
    def do_cmd(self, arg):
        """Lists all available commands"""
        print("article, rss, url, cmd, help, exit")

    # --- help ---
    def do_help(self, arg):
        """Shows help for commands"""
        if arg:
            return super().do_help(arg)

        order = {k: i for i, k in enumerate(['article', 'rss', 'url', 'cmd', 'help', 'exit'])}
        
        cmds = [c[3:] for c in dir(self) if c.startswith('do_')]
        cmds.sort(key=lambda x: order.get(x, 99))

        for c in cmds:
            doc = (getattr(self, f'do_{c}').__doc__ or "").split('\n')[0]
            print(f"{c:<8} {doc}")

    # --- exit ---
    def do_exit(self, arg):
        """Exit the shell"""
        print("Goodbye!")
        self.conn.close()
        return True

    def do_EOF(self, arg):
        """Handle Ctrl+D to exit"""
        return self.do_exit(arg)

if __name__ == '__main__':
    try:
        BriefShell().cmdloop()
    except KeyboardInterrupt:
        print("\nUse 'exit' to quit. Goodbye!")
        sys.exit(0)