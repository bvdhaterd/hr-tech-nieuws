#!/usr/bin/env python3
"""
HR Tech Nieuws - RSS Fetcher
Haalt dagelijks nieuws op over investeringen, fusies & overnames en rechtszaken
in de HR technologie, Talent Acquisition en Recruitment technologie sector.
"""

import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
import requests

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'news.json')
MAX_AGE_DAYS = 30

QUERIES = {
    'investments': {
        'label': 'Investeringen',
        'en': [
            'HR technology funding',
            'HR tech investment round',
            'human resources software venture capital',
            'talent acquisition software funding',
            'recruitment technology investment',
            'TA tech funding round',
        ],
        'nl': [
            'HR software investering',
            'werving technologie investering',
            'recruitment software financiering',
        ],
    },
    'mergers_acquisitions': {
        'label': 'Fusies & Overnames',
        'en': [
            'HR technology acquisition',
            'HR tech merger',
            'human resources software acquired',
            'talent acquisition software acquisition',
            'recruitment technology merger',
            'TA platform acquired',
        ],
        'nl': [
            'HR technologie overname',
            'recruitment software overname',
            'HR software fusie',
        ],
    },
    'lawsuits': {
        'label': 'Rechtszaken',
        'en': [
            'HR technology lawsuit',
            'HR tech legal action',
            'human resources software court',
            'talent acquisition software lawsuit',
            'recruitment technology legal',
            'TA platform court case',
        ],
        'nl': [
            'personeelssoftware rechtszaak',
            'HR technologie rechtszaak',
            'recruitment software rechtbank',
        ],
    },
}

GOOGLE_NEWS_EN = 'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en'
GOOGLE_NEWS_NL = 'https://news.google.com/rss/search?q={query}&hl=nl&gl=NL&ceid=NL:nl'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; HRTechNewsBot/1.0)'
}


def build_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def parse_date(entry) -> Optional[datetime]:
    for field in ('published', 'updated'):
        raw = getattr(entry, field, None)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass
    return None


def fetch_feed(url: str) -> list:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        return feed.entries
    except Exception as e:
        print(f'  Fout bij ophalen {url}: {e}')
        return []


def entry_to_article(entry, category: str, language: str) -> Optional[dict]:
    url = getattr(entry, 'link', None)
    title = getattr(entry, 'title', '').strip()
    if not url or not title:
        return None

    pub_date = parse_date(entry)
    if pub_date is None:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    if pub_date < cutoff:
        return None

    # Snippet: strip alle HTML tags, decode HTML entities
    raw_summary = getattr(entry, 'summary', '') or ''
    snippet = re.sub(r'<[^>]+>', ' ', raw_summary)
    snippet = html.unescape(snippet)
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    # Google News summaries zijn vaak alleen de link-tekst; sla op als leeg
    if snippet.startswith('http') or len(snippet) < 20:
        snippet = ''
    if len(snippet) > 300:
        snippet = snippet[:297] + '...'

    source = ''
    if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
        source = entry.source.title
    elif hasattr(entry, 'tags') and entry.tags:
        source = entry.tags[0].get('term', '')
    if not source:
        source = url.split('/')[2].replace('www.', '')

    return {
        'id': build_id(url),
        'title': title,
        'source': source,
        'url': url,
        'published': pub_date.isoformat(),
        'snippet': snippet,
        'category': category,
        'language': language,
    }


def fetch_category(category: str, config: dict) -> list:
    articles = []
    seen_ids = set()

    for lang, template in [('en', GOOGLE_NEWS_EN), ('nl', GOOGLE_NEWS_NL)]:
        queries = config.get(lang, [])
        for query in queries:
            encoded = requests.utils.quote(query)
            url = template.format(query=encoded)
            print(f'  [{lang}] {query}')
            entries = fetch_feed(url)
            for entry in entries:
                article = entry_to_article(entry, category, lang)
                if article and article['id'] not in seen_ids:
                    seen_ids.add(article['id'])
                    articles.append(article)

    # Sorteer op publicatiedatum, nieuwste eerst
    articles.sort(key=lambda a: a['published'], reverse=True)
    return articles


def main():
    all_articles = []
    seen_ids = set()

    for category, config in QUERIES.items():
        print(f'\nCategorie: {config["label"]}')
        articles = fetch_category(category, config)
        for article in articles:
            if article['id'] not in seen_ids:
                seen_ids.add(article['id'])
                all_articles.append(article)
        print(f'  {len(articles)} artikelen gevonden (na deduplicatie per categorie)')

    # Globale deduplicatie al gedaan via seen_ids
    all_articles.sort(key=lambda a: a['published'], reverse=True)

    output = {
        'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'total': len(all_articles),
        'articles': all_articles,
    }

    out_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\nKlaar: {len(all_articles)} unieke artikelen opgeslagen in {out_path}')


if __name__ == '__main__':
    main()
