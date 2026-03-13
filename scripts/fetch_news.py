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

# ---------------------------------------------------------------------------
# Queries: bevatten nu actiewoorden (raises, acquires, lawsuit) zodat Google
# News direct meer event-gerichte resultaten teruggeeft.
# ---------------------------------------------------------------------------
QUERIES = {
    'investments': {
        'label': 'Investments',
        'en': [
            '"HR tech" raises million',
            '"HR technology" funding round',
            '"HR software" series funding',
            '"talent acquisition" software raises funding',
            '"talent acquisition platform" investment round',
            '"recruitment software" funding round',
            '"recruiting technology" raises investment',
            '"recruiting platform" raises million',
            '"workforce technology" funding raises',
            '"HR platform" series capital venture',
            '"payroll software" raises million',
            '"talent management" software raises funding',
            '"people analytics" funding raises',
            '"talent intelligence" funding investment',
            '"talent sourcing" platform funding raises',
            '"sourcing platform" raises investment',
            '"AI recruiting" raises funding',
            '"AI hiring" raises funding round',
            '"hiring platform" raises investment',
            '"background check" software funding raises',
            '"employee engagement" platform funding raises',
            '"onboarding software" raises funding',
            '"skills-based hiring" funding investment',
            '"workforce management software" funding',
            '"HR tech" seed round investment',
        ],
        'nl': [
            'HR software financieringsronde investering',
            'HR technologie investeringsronde miljoen',
            'recruitment technologie financiering investering',
        ],
    },
    'mergers_acquisitions': {
        'label': 'Mergers & Acquisitions',
        'en': [
            '"HR tech" acquires OR acquired',
            '"HR technology" acquires OR merger',
            '"HR software" acquisition merger',
            '"talent acquisition platform" acquired OR acquires',
            '"talent acquisition software" acquired OR merger',
            '"recruitment software" acquisition OR acquired',
            '"recruiting platform" acquired OR acquires',
            '"recruiting software" acquired OR acquires',
            '"workforce management" software acquired',
            '"payroll software" acquired OR acquires',
            '"applicant tracking" acquired OR acquires',
            '"HR platform" merger OR acquisition',
            '"talent management" software acquired OR acquires',
            '"talent intelligence" platform acquired',
            '"AI hiring" company acquired OR merger',
            '"background check" company acquired OR acquires',
            '"people analytics" platform acquired',
            '"HR tech" company merger deal',
        ],
        'nl': [
            'HR technologie overname fusie',
            'HR software overname overgenomen',
            'recruitment software fusie overname',
        ],
    },
    'lawsuits': {
        'label': 'Lawsuits',
        'en': [
            '"HR tech" lawsuit sued court',
            '"HR software" lawsuit OR litigation',
            '"HR technology" lawsuit OR court',
            '"talent acquisition" software lawsuit OR sued',
            '"recruitment software" lawsuit OR court',
            '"applicant tracking" lawsuit OR sued',
            '"hiring algorithm" lawsuit OR court',
            '"AI hiring" lawsuit OR court OR discrimination',
            '"AI recruiting" lawsuit OR court',
            '"background check" lawsuit OR FCRA',
            '"HR platform" lawsuit OR sued',
            '"payroll software" lawsuit OR court',
            '"workforce management" lawsuit OR court',
            '"talent management" software lawsuit',
            '"employee monitoring" software lawsuit',
            '"HR tech" discrimination OR settlement',
            '"recruiting software" discrimination OR lawsuit',
        ],
        'nl': [
            'HR software rechtszaak rechtbank',
            'HR technologie rechtszaak aanklacht',
            'recruitment software rechtbank zaak',
        ],
    },
}

# Google News RSS — &tbs=qdr:m beperkt resultaten tot de laatste ~30 dagen
GOOGLE_NEWS_EN = 'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en&tbs=qdr:m'
GOOGLE_NEWS_NL = 'https://news.google.com/rss/search?q={query}&hl=nl&gl=NL&ceid=NL:nl&tbs=qdr:m'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; HRTechNewsBot/1.0)'
}

# ---------------------------------------------------------------------------
# Relevantiefiltering
# ---------------------------------------------------------------------------

# Per categorie: minstens één van deze woorden moet voorkomen in titel+snippet
CATEGORY_KEYWORDS = {
    'investments': [
        'fund', 'raise', 'raised', 'raises', 'invest', 'series a', 'series b',
        'series c', 'series d', 'series e', 'seed round', 'seed funding', 'pre-seed',
        ' round', 'capital', 'backed', 'million', 'billion', 'valuation', 'unicorn',
        'venture', ' vc ', 'equity stake', 'growth round', 'bridge round',
    ],
    'mergers_acquisitions': [
        'acqui', 'merger', 'merges', 'merge ', 'buys ', 'bought', 'purchas',
        'takeover', 'take over', 'combines', 'combining', ' deal', 'divest',
        'spin-off', 'spin off',
    ],
    'lawsuits': [
        'lawsuit', 'sued ', 'sues ', 'court', 'legal action', 'settlement',
        'litigation', 'allegat', 'class action', 'class-action', 'injunction',
        'charges', 'complaint', 'ruling', 'verdict', 'plaintiff', 'defendant',
        'fcra', 'eeoc', 'discrimination', 'violation', 'fine', 'penalty', 'regulator',
    ],
}

# HR Tech context: minstens één van deze woorden moet voorkomen in titel+snippet
HR_TECH_KEYWORDS = [
    # Generieke HR tech termen
    'hr tech', 'hrtech', 'hr software', 'hr platform', 'hr system', 'hr tool',
    'hr technology', 'hr solution', 'hr startup', 'hr company', 'hr firm',
    'hris', 'hcm', 'human capital management', 'human resources software',
    'human resources technology',
    # ATS / Recruiting
    'applicant tracking', ' ats ', 'recruiting software', 'recruiting platform',
    'recruiting technology', 'recruiting tool', 'recruiting app', 'recruiting company',
    'recruitment software', 'recruitment platform', 'recruitment technology',
    'recruitment tool', 'recruitment solution', 'recruitment company',
    # Talent
    'talent acquisition platform', 'talent acquisition software',
    'talent acquisition technology', 'talent acquisition tool',
    'talent management software', 'talent management platform',
    'talent intelligence', 'talent sourcing platform', 'talent sourcing software',
    'talent sourcing tool', 'talent sourcing company',
    # AI / Hiring tech
    'ai hiring', 'ai-powered hiring', 'ai recruiting', 'ai-powered recruiting',
    'ai recruitment', 'ai-driven hr', 'ai for hr', 'hiring platform',
    'hiring software', 'hiring technology', 'hiring tool',
    # Workforce
    'workforce management software', 'workforce management platform',
    'workforce technology', 'workforce software', 'workforce platform',
    'workforce solution',
    # Payroll
    'payroll software', 'payroll platform', 'payroll technology', 'payroll solution',
    # Analytics / Intelligence
    'people analytics', 'hr analytics', 'workforce analytics',
    # Background checks
    'background check software', 'background screening software',
    'background check platform', 'background check company', 'background check provider',
    # Engagement / Experience
    'employee engagement software', 'employee engagement platform',
    'employee experience platform', 'employee experience software',
    # Performance / Learning
    'performance management software', 'performance management platform',
    'learning management system', ' lms ', 'e-learning platform',
    # Onboarding / Skills / Comp
    'onboarding software', 'onboarding platform', 'skills-based hiring',
    'compensation software', 'compensation management', 'total rewards platform',
    # Staffing / Scheduling
    'staffing software', 'staffing platform', 'staffing technology',
    'scheduling software', 'shift management software',
    # Bekende HR tech bedrijven (voor als bedrijfsnaam in titel staat zonder context-woorden)
    'workday', 'successfactors', 'oracle hcm', 'sap hr', ' adp ', 'bamboohr',
    'greenhouse', ' lever ', 'jobvite', 'icims', 'smartrecruiters', 'workable',
    'breezy', 'ashby', 'rippling', ' gusto', 'zenefits', 'paychex', 'ceridian',
    'dayforce', ' ukg ', 'kronos', 'cornerstone ondemand', ' saba ',
    'eightfold', 'seekout', 'beamery', ' phenom ', ' paradox ', 'hirevue',
    'pymetrics', 'modern hire', 'humanly', 'juicebox', 'findem', 'fetcher',
    ' dover ', ' gem ', 'hireez', 'entelo', 'manatal', 'homerun', 'recruitee',
    'personio', 'factorial', 'humaans', 'leapsome', ' lattice ', 'culture amp',
    ' glint ', '15five', 'betterworks', 'workera', 'degreed', '360learning',
    'docebo', ' absorb ', 'litmos', 'hibob', ' deel ', 'oyster hr',
    'velocity global', 'checkr', ' sterling ', 'first advantage', 'hireright',
    ' namely ', 'paycor', 'isolved', 'paylocity', 'paycom', 'workhuman',
    'textio', 'applied ', 'vervoe', 'codility', 'hackerrank', 'harver',
    'predictive index', ' shl ', 'taleo', 'jobdiva', 'bullhorn', 'avature',
    'jazzhr', 'jazz hr', 'teamtailor', 'pinpoint', 'textkernel', 'paradox ai',
    'eightfold ai', 'beamery', 'reejig', 'claro', 'gloat', 'fuel50',
    'internal mobility', 'skyhive', 'draup', 'allegis', 'korn ferry',
    'mercer', 'aon hewitt',
]

# Titels die overeenkomen met deze patronen worden uitgesloten
EXCLUDE_TITLE_PATTERNS = [
    r'^\d+\s+(best|top|great|ways|things|reasons)',          # "10 Best HR Software..."
    r'^(best|top)\s+\d+',                                    # "Best 5 ATS..."
    r'^top\s+\d+',                                           # "Top 10 HR..."
    r'\btrends?\s+(for|in|of|to\s+watch)\b',                # "...trends in 2026"
    r'\b(how\s+to|guide\s+(to|for)|tips\s+for|what\s+is)\b',
    r'\b(explained|roundup|overview|introduction\s+to)\b',
    r'\bfuture\s+of\b',
    r'\boutlook\s+(for|in)\b',
    r'\bstate\s+of\b.*\b(report|survey)\b',
    r'\bstatistics\b',
    r'\blist\s+of\b',
    r'\bcritical\s+(skills?|trends?|challenges?)\b',
    r'\bpredictions?\s+for\b',
    r'\byear\s+in\s+review\b',
    r'\blessons?\s+(learned|from)\b',
    r'\bwhat\s+(you\s+need|every|employers?|companies?|hr\s+teams?)\b',
    r'\b(key|essential|important)\s+(skills?|traits?|qualities|strategies|practices|metrics)\b',
    r'\bjob\s+(openings?|listings?|vacancies?|postings?|fair)\b',
    r'\bhiring\s+(drive|campaign|process|strategy|tips|checklist)\b',
    r'\brecruitment\s+(drive|campaign|process|tips|checklist|strategy|opens?|applications?)\b',
    r'\b(salary|wage)\s+(survey|benchmark|guide|data|report)\b',
    r'\bworkforce\s+(questions?|challenges?|concerns?|issues?)\b',  # "workforce questions" in media merger
    r'\b(magazine|award|conference|webinar|event|summit)\b',
    # Marktrapport/onderzoek taal
    r'\bprojected\s+to\s+(reach|grow|hit|expand)\b',
    r'\bmarket\s+(size|report|analysis|research|study|overview|forecast)\b',
    r'\b(cagr|compound\s+annual)\b',
    r'\bforecast\s+(period|by\s+\d{4})\b',
    r'\b(usd|eur)\s+\d+.*billion.*by\s+\d{4}\b',
    r'\bglobal\s+.*(market|industry)\s+(size|report|to\s+(reach|grow))\b',
    r'\bset\s+for\s+(robust|rapid|strong|significant)\s+(growth|expansion)\b',
]


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

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


def is_relevant(title: str, snippet: str, category: str) -> bool:
    """
    Controleer of een artikel relevant is:
    1. Titel bevat geen uitgesloten patronen
    2. Titel+snippet bevat minstens één categorie-actiewoord
    3. Titel+snippet bevat minstens één HR tech contextwoord
    """
    text = (title + ' ' + snippet).lower()
    title_lower = title.lower()

    # 1. Uitsluitpatronen in titel
    for pattern in EXCLUDE_TITLE_PATTERNS:
        if re.search(pattern, title_lower):
            return False

    # 2. Categorie-actiewoorden
    cat_kws = CATEGORY_KEYWORDS.get(category, [])
    if not any(kw in text for kw in cat_kws):
        return False

    # 3. HR Tech context
    if not any(kw in text for kw in HR_TECH_KEYWORDS):
        return False

    return True


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

    # Snippet: strip HTML tags, decode entities
    raw_summary = getattr(entry, 'summary', '') or ''
    snippet = re.sub(r'<[^>]+>', ' ', raw_summary)
    snippet = html.unescape(snippet)
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    if snippet.startswith('http') or len(snippet) < 20:
        snippet = ''
    if len(snippet) > 300:
        snippet = snippet[:297] + '...'

    # Relevantiefilter
    if not is_relevant(title, snippet, category):
        return None

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
            added = 0
            for entry in entries:
                article = entry_to_article(entry, category, lang)
                if article and article['id'] not in seen_ids:
                    seen_ids.add(article['id'])
                    articles.append(article)
                    added += 1
            print(f'       → {added} relevant van {len(entries)} opgehaald')

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
        print(f'  → {len(articles)} unieke artikelen in deze categorie')

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
