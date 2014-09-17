#!/usr/bin/python2.6
"""This script will parse RSS feeds from the Dutch government in an attempt to
find publications relevant to the field of digital civil rights and privacy.
Some of the feeds will be included completely, others will be filtered using a
list of keywords."""

from datetime import datetime
from time import mktime
from ConfigParser import SafeConfigParser
import cgi
import feedparser
import MySQLdb
import PyRSS2Gen
import sys

START_TIME = datetime.now()

CONFIG = SafeConfigParser()
CONFIG.read('newspeak.cfg')

KEYWORDS = []
with open('keywords.txt', 'r') as f:
    for line in f:
        line = line.partition('#')[0]
        if line != '':
            KEYWORDS.append(line.rstrip())

try:
    CONN = MySQLdb.connect(host = CONFIG.get('database', 'hostname'),
            user = CONFIG.get('database', 'username'),
            passwd = CONFIG.get('database', 'password'),
            db = CONFIG.get('database', 'database'),
            charset = CONFIG.get('database', 'charset'))

except MySQLdb.Error, e:
    print "Error %d: %s" % (e.args[0], e.args[1])
    sys.exit (1)

CURSOR = CONN.cursor()

def convert_unicode_to_html(string):
    """Converts unicode to HTML entities. For example '&' becomes '&amp;'."""
    string = cgi.escape(string).encode('ascii', 'xmlcharrefreplace')
    return string

def does_match_keyword(item):
    """Return TRUE if the string contains any of the given keywords."""
    for key in KEYWORDS:
        if hasattr(item, 'title'):
          if key in item['title'].lower():
            return True
        if hasattr(item, 'description'):
           if key in item['description'].lower():
             return True
    return False

def is_existing_item(link):
    """See if URI of item is already known in the database."""
    CURSOR.execute('''SELECT id FROM items WHERE link = %s''', link)
    return CURSOR.rowcount > 0

def insert_item_into_db(link, feed_id, title, description, updated_parsed,
        feed_format):
    """Add a new item to the database."""
    if feed_format == '0':
        CURSOR.execute('''INSERT INTO items (link, feed_id, title,
                description, time_published) VALUES (%s, %s, %s, %s,
                %s)''', (link, feed_id,
                    convert_unicode_to_html(description)[0:1000],
                    convert_unicode_to_html(title)[0:1000],
                    datetime.fromtimestamp(mktime(updated_parsed))))
    if feed_format == '1':
        CURSOR.execute('''INSERT INTO items (link, feed_id, title,
                description, time_published) VALUES (%s, %s, %s, %s,
                %s)''', (link, feed_id, convert_unicode_to_html(title)[0:1000],
                    convert_unicode_to_html(description)[0:1000],
                    datetime.fromtimestamp(mktime(updated_parsed))))

CURSOR.execute('''SELECT id, uri, filter, format, description FROM feeds
        WHERE active = '1'
        ORDER BY description, id''')
FEEDS = CURSOR.fetchall()

for feed in FEEDS:
    f = feedparser.parse('%s' % feed[1])
    if feed[2] == '1':
        for item in f.entries:
            if is_existing_item(item['link']) is not True:
                insert_item_into_db(item['link'], feed[0], item['title'],
                        item['description'], item['updated_parsed'], feed[3])
    elif feed[2] == '2':
        for item in f.entries:
            if does_match_keyword(item) is True:
                if is_existing_item(item['link']) is not True:
                    insert_item_into_db(item['link'], feed[0], item['title'],
                            item['description'], item['updated_parsed'],
                            feed[3])

CURSOR.execute('''SELECT items.link, items.title, items.description,
        items.time_published, feeds.description, feeds.format FROM items, feeds
        WHERE items.feed_id = feeds.id
        AND feeds.active = '1'
        ORDER BY items.time_published DESC
        LIMIT 50''')
PUBLISHED_ITEMS = CURSOR.fetchall()

FEED_ITEMS = [
    PyRSS2Gen.RSSItem(
            title = published_item[1],
            link = published_item[0],
            description = """%s (%s)""" % (published_item[2],
                published_item[4]),
            guid = published_item[0],
            pubDate = published_item[3]
            )
        for published_item in PUBLISHED_ITEMS
    ]

PUBLISHED_FEED = PyRSS2Gen.RSS2(
    title = CONFIG.get('rss', 'title'),
    link = CONFIG.get('rss', 'link'),
    description = CONFIG.get('rss', 'description'),
    managingEditor = CONFIG.get('rss', 'editor'),
    lastBuildDate = datetime.utcnow(),
    items = FEED_ITEMS
    )

PUBLISHED_FEED.write_xml(open(CONFIG.get('files', 'rss'), "w"))


CURSOR.close()
CONN.close()

HTML_FILE = CONFIG.get('files', 'html')
if HTML_FILE:
    with open(HTML_FILE, 'w') as f:
        TITLE = convert_unicode_to_html(CONFIG.get('rss', 'title'))
        MY_LINK = convert_unicode_to_html(CONFIG.get('rss', 'link'))
        MY_DESC = convert_unicode_to_html(CONFIG.get('rss', 'description'))
        f.write('''
<!DOCTYPE html><html><head>
<title>'''+TITLE+''' - Aggregated RSS feed</title>
<link rel="alternate" href="'''+MY_LINK+'" title="'+TITLE+'''" type="application/rss+xml"/>
<style type="text/css">
  body { font-family: Georgia; font-size: 16px; margin-left: 60px; }
  h1 { margin-bottom: 2px; }
  a { text-decoration: none; }
  p.slogan { margin-top: 0; }
</style>
</head><body>
<h1>'''+TITLE+'''</h1>
<p class="slogan">Aggregated RSS feed</p>
<p>'''+MY_DESC+'''</p>
<p><a href="'''+MY_LINK+'''">RSS feed</a>
based on '''+str(len(FEEDS))+''' sources:</p>
<table>
<thead><tr><th>uri</th><th>description</th></tr></thead>
<tbody>''')
        for feed in FEEDS:
            LINK = convert_unicode_to_html(feed[1])
            DESCRIPTION = convert_unicode_to_html(feed[4])
            f.write('''<tr>
<td><a href="'''+LINK+'">'+LINK+'</a></td><td>'+DESCRIPTION)
            if feed[2] == '2':
                f.write(' *')
            f.write('</td></tr>')
        f.write('''</tbody></table>
<p>* Filtered by the following keywords:</p><ul>''')
        for key in KEYWORDS:
            f.write('<li>'+key+'</li>')
        f.write('''</ul>
<p>Last check: '''+START_TIME.strftime("%Y-%m-%d %H:%M")+'''</p>
<footer>Powered by <a href="https://github.com/rejozenger/newspeak">newspeak</a>
</footer></body></html>''')
