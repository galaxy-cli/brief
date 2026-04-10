# brief
A lightweight CLI RSS and Article reader with built-in Text-to-Speech (TTS).

## Features
- **RSS Management:** Add, list, and fetch articles from your favorite feeds.
- **Article Reader:** Scrape and store full article content for offline reading.
- **TTS Playback:** Listen to articles using the `festival` engine.
- **Custom View:** Open articles in a dedicated "Reader Mode" window using `yad`.
- **Anti-Bot Bypass:** Uses `cloudscraper` to handle sites that block standard bots.

## Getting Started

### Prerequisites
- **Python 3.12+**
- **System Tools:** `festival`, `yad`, `xsel` (for clipboard support)
```
sudo apt update && sudo apt install festival yad xsel
```
## Installation
1. Clone the repository and navigate into it.
2. Install Python dependencies:
```
pip install -r requirements.txt
```
## Usage
Run the script to enter the interactive shell:
```
python3 brief.py
```
## Common Commandsrss list: 
View your saved feeds.
- `rss list`: View your saved feeds.
- `rss add [URL]`: Add a new feed.
- `rss fetch [NUM] [ID]`: Fetch the latest NUM articles from feed ID.
- `article list`: View downloaded articles.
- `article read [ID]`: Open and listen to article ID.
- `url add [URL]`: Scrape a single article directly from a URL.