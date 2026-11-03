"""Public-domain literature from 위키문헌 (ko.wikisource.org) for passage sets.

Only works whose authors all died long enough ago are offered. Korean copyright runs for the
author's life + 70 years, but works of authors who died before 1963 had already expired under the
earlier 50-year rule when the term was extended in 2013. Anonymous works pass only when 위키문헌
itself tags them PD-old. The check runs again when the text is fetched; the client is never trusted.
"""
import datetime
import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

API = 'https://ko.wikisource.org/w/api.php'
AGENT = 'TestCraft/0.2 (school exam authoring; https://github.com/sehunYang/testcraft)'
DIED = re.compile(r'^분류:(\d{3,4})년 죽음$')
MAX_TEXT = 20000


def expired_before(today=None):
    """Last death year whose works are free in Korea today."""
    year = (today or datetime.date.today()).year
    return max(1962, year - 71)


def call(**params):
    params.update(format='json', formatversion='2')
    request = urllib.request.Request(API + '?' + urllib.parse.urlencode(params), headers={'User-Agent': AGENT})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode('utf-8'))
    except OSError as e:
        raise ValueError('위키문헌에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.') from e


def pages(titles, **params):
    """Page info for up to 50 titles, keyed by title (redirects followed)."""
    if not titles: return {}
    data = call(action='query', titles='|'.join(titles), redirects=1, **params)
    out = {p['title']: p for p in data.get('query', {}).get('pages', [])}
    for r in data.get('query', {}).get('redirects', []):
        if r['to'] in out: out[r['from']] = out[r['to']]
    return out


def categories(page):
    return [c['title'] for c in page.get('categories', [])]


def statuses(titles, today=None):
    """Copyright status of each work: author names, latest death year and whether it may be used."""
    works = pages(titles, prop='links|categories|pageprops', plnamespace=100, pllimit='max', cllimit='max', ppprop='disambiguation')
    authors = sorted({link['title'] for p in works.values() for link in p.get('links', [])})
    people = pages(authors, prop='categories', cllimit='max')
    limit = expired_before(today)
    out = {}
    for title in titles:
        page = works.get(title) or {}
        names, years, unknown = [], [], []
        for link in page.get('links', []):
            name = link['title'].split(':', 1)[-1]; names.append(name)
            died = [int(m[1]) for c in categories(people.get(link['title']) or {}) if (m := DIED.match(c))]
            (years if died else unknown).append(max(died) if died else name)
        if 'disambiguation' in page.get('pageprops', {}):
            status = dict(allowed=False, reason='같은 이름의 작품을 모은 안내 문서입니다. 아래 목록에서 판본을 골라 주세요.')
        elif unknown:
            status = dict(allowed=False, reason=f"{', '.join(unknown)}의 사망 연도를 확인할 수 없습니다.")
        elif years:
            last = max(years)
            status = dict(allowed=last <= limit, died=last,
                          reason='' if last <= limit else f'저작자가 {last}년에 사망해 아직 저작권이 남아 있습니다.')
        elif any(c.startswith('분류:PD-old') for c in categories(page)):
            status = dict(allowed=True, reason='')                     # anonymous classic tagged PD-old
        else:
            status = dict(allowed=False, reason='저작자와 저작권 상태를 확인할 수 없습니다.')
        out[title] = dict(status, author=', '.join(names))
    return out


def plain(snippet):
    return html.unescape(re.sub(r'<[^>]+>', '', snippet or '')).strip()


def search(query, today=None):
    query = str(query or '').strip()
    if not 1 <= len(query) <= 80: raise ValueError('작품 이름이나 저자를 80자 이내로 입력해 주세요.')
    found = call(action='query', list='search', srsearch=query, srnamespace=0, srlimit=15).get('query', {}).get('search', [])
    titles = [r['title'] for r in found]
    known = statuses(titles, today)
    results = [dict(title=r['title'], work=work_name(r['title']), snippet=plain(r.get('snippet'))[:160], **known[r['title']]) for r in found]
    return {'results': results, 'limit': expired_before(today)}


def work_name(title):
    """'하늘과 바람과 별과 시 (1948년)/서시' -> '서시'."""
    return re.sub(r'\s*\([^)]*\)$', '', title.split('/')[-1]).strip()


SKIP_CLASSES = {'ws-noexport', 'messagebox', 'metadata', 'ambox', 'wst-header', 'ws-header', 'licenseContainer', 'licensetpl', 'pagenum', 'mw-heading', 'reference', 'references', 'mw-references-wrap', 'noprint', 'mw-editsection'}
BLOCKS = {'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'dd', 'dt', 'table', 'blockquote', 'pre'}
VOID = {'br', 'img', 'hr', 'meta', 'link', 'input', 'wbr', 'source', 'col', 'area'}


class TextOnly(HTMLParser):
    """Body text of a rendered 위키문헌 page: line breaks kept, header/licence/page numbers/notes dropped."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.stack = [], []

    def skipping(self):
        return any(self.stack)

    def handle_starttag(self, tag, attrs):
        if tag == 'br':
            if not self.skipping(): self.parts.append('\n')
            return
        if tag in VOID: return
        a = dict(attrs)
        skip = tag in ('style', 'script', 'sup') or bool(SKIP_CLASSES & set((a.get('class') or '').split()))
        self.stack.append(skip)
        if tag in BLOCKS and not self.skipping(): self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in VOID or not self.stack: return
        skipped = self.stack.pop()
        if tag in BLOCKS and not skipped and not self.skipping(): self.parts.append('\n')

    def handle_data(self, data):
        if not self.skipping(): self.parts.append(data.replace('\n', ' '))   # source newlines are only whitespace

    def text(self):
        raw = ''.join(self.parts).replace('​', '').replace('\xa0', ' ')
        lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in raw.split('\n')]
        return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def text(title, today=None):
    title = str(title or '').strip()
    if not title or len(title) > 255: raise ValueError('작품을 다시 선택해 주세요.')
    status = statuses([title], today)[title]
    if not status['allowed']: raise ValueError(status['reason'] or '저작권이 만료된 작품만 넣을 수 있습니다.')
    data = call(action='parse', page=title, prop='text', redirects=1, disablelimitreport=1, disableeditsection=1)
    if 'error' in data: raise ValueError('작품 본문을 찾지 못했습니다.')
    parser = TextOnly(); parser.feed(data['parse']['text']); content = parser.text()
    if not content: raise ValueError('본문이 비어 있습니다. 하위 문서(각 작품)를 골라 주세요.')
    truncated = len(content) > MAX_TEXT
    source = f"{status['author']}, 「{work_name(title)}」" if status['author'] else f'「{work_name(title)}」'
    return {'content': content[:MAX_TEXT], 'source': source, 'truncated': truncated, 'title': title,
            'url': 'https://ko.wikisource.org/wiki/' + urllib.parse.quote(title.replace(' ', '_'))}
