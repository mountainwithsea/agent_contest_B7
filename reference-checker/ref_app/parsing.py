"""Conservative, source-grounded citation parsing. No network in the rule path."""
import hashlib
import re

VERSION = 'rules-links-v1'
ROLES = {'primary_work', 'related_data', 'related_code', 'alternate_version', 'unknown'}


def evidence(raw, value, method):
    if not value:
        return None
    # Allow whitespace folding only; never silently repair wording or names.
    pattern = r'\s+'.join(re.escape(x) for x in value.split())
    match = re.search(pattern, raw, re.I)
    if not match:
        raise ValueError('Field is not grounded in citation: ' + value[:100])
    return {'start': match.start(), 'end': match.end(), 'quote': match.group(), 'method': method}


def extract_links(raw):
    links = []
    previous_end = 0
    for match in re.finditer(r'https?://[^\s<>"]+', raw, re.I):
        url = match.group().rstrip('.,;')
        while url.endswith(')') and url.count(')') > url.count('('):
            url = url[:-1]
        context = raw[previous_end:match.start()]
        # Only explicit local introduction is enough to assign a resource role.
        role = 'unknown'
        cues = list(re.finditer(r'\b(data|dataset|code|source code|full version|extended version)\s+(?:(?:can\s+be\s+found|is\s+available|are\s+available|available|at)\s*)?(?:at\s*)?[:：]?\s*$', context, re.I))
        if cues:
            word = cues[-1].group(1).lower()
            role = 'related_data' if word in ('data', 'dataset') else 'related_code' if 'code' in word else 'alternate_version'
        links.append({'url': url, 'role': role, 'certainty': 'explicit' if role != 'unknown' else 'unknown',
                      'source': {'start': match.start(), 'end': match.start()+len(url), 'quote': url},
                      'context': context[-180:], 'method': 'rule'})
        previous_end = match.end()
    return links


def base(raw):
    return {'title': None, 'authors': [], 'year': None, 'container_title': None,
            'volume': None, 'issue': None, 'pages': None, 'doi': [], 'arxiv': [],
            'urls': [], 'authors_truncated': False, 'notes': [], 'work_type': 'other',
            'raw_text': raw, 'raw_sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'parser_version': VERSION, 'field_evidence': {}, 'links': extract_links(raw)}


def parse_rules(raw):
    q = base(raw)
    reasons = []
    for key, pattern in [('doi', r'\b10\.\d{4,9}/[^\s<>"]+'),
                         ('arxiv', r'(?:arxiv\s*:\s*|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}(?:v\d+)?)')]:
        for m in re.finditer(pattern, raw, re.I):
            value = (m.group(1) if key == 'arxiv' else m.group()).rstrip('.,;')
            if value not in q[key]:
                q[key].append(value)
    # A deliberately narrow grammar: full names, year, title, explicit venue.
    text = re.sub(r'^\s*(?:\[[^\]]+\]|\d+[.)])\s*', '', raw)
    m = re.match(r'(?P<authors>.+?)\.\s+(?P<year>(?:19|20)\d{2})[a-z]?\.\s+(?P<title>[^.?!]+[?!]?)\.\s*(?P<tail>.*)$', text, re.S)
    if m:
        names = re.split(r',\s*(?:and\s+)?|\s+and\s+', m['authors'])
        names = [n.strip() for n in names if n.strip()]
        truncated = bool(names and names[-1].lower() == 'et al')
        if truncated:names = names[:-1]
        valid_names = bool(names) and all(re.fullmatch(r"[^\W\d_][\w'’\-]+(?:\s+[^\W\d_][\w'’\-]+){1,5}", n, re.UNICODE) for n in names)
        tail = m['tail'].strip()
        venue = re.match(r'(?:In\s+)?((?:Proceedings\b|Advances in\b|Transactions\b|Journal\b|International Conference\b)[^.]+)\.', tail, re.I)
        if valid_names and len(m['title'].split()) >= 3 and venue:
            q.update(title=m['title'].strip(), authors=[{'literal':n, 'kind':'person'} for n in names], year=m['year'], work_type='article')
            q['authors_truncated'] = truncated
            venue_text = venue.group(1)
            page = re.search(r',\s*pages?\s+(\d+(?:\s*[–—-]\s*\d+)?)', venue_text, re.I)
            q['container_title'] = venue_text[:page.start()].strip() if page else venue_text.strip()
            if page:q['pages'] = page.group(1)
            volume = re.search(r',\s*(\d+)(?:\((\d+)\))?\s*:\s*(\d+(?:\s*[–—-]\s*\d+)?)$', venue_text)
            if volume:
                q.update(container_title=venue_text[:volume.start()].strip(), volume=volume.group(1), issue=volume.group(2), pages=volume.group(3))
            remainder = tail[venue.end():].strip()
            if remainder:q['notes'] = [remainder]
        else:
            reasons.append('作者或题名、出处边界不能由严格格式确定')
    else:
        reasons.append('不符合已支持的严格作者—年份—题名—出处格式')
    if any(x['role'] == 'unknown' for x in q['links']):
        reasons.append('链接与被引用作品的关系需要判断')
    if re.search(r'https?://\S+\s*\n\s*\S+', raw):
        reasons.append('网址可能跨行，保留原文交给模型复核')
    if q['title'] and re.search(r'\w-\s+\w', ' '.join([q['title']]+[a['literal'] for a in q['authors']])):
        reasons.append('题名或作者有跨行断词，需要复核')
    q['fallback_reasons'] = reasons
    q['parse_status'] = 'needs_llm' if reasons else 'rules_complete'
    q['parser_method'] = 'rules'
    attach_evidence(q, 'rule')
    finalize_urls(q)
    return q


def attach_evidence(q, method):
    for key in ('title', 'year', 'container_title', 'volume', 'issue', 'pages'):
        if q.get(key):q['field_evidence'][key] = evidence(q['raw_text'], q[key], method)
    q['field_evidence']['authors'] = [evidence(q['raw_text'], a['literal'], method) for a in q['authors']]
    for key in ('doi', 'arxiv', 'notes'):
        q['field_evidence'][key] = [evidence(q['raw_text'], value, method) for value in q[key]]


def finalize_urls(q):
    # Existing downstream URL input receives work links and unresolved links,
    # never links explicitly described as associated data/code/other versions.
    q['urls'] = list(dict.fromkeys(x['url'] for x in q['links'] if x['role'] in ('primary_work', 'unknown')))
    q['all_urls'] = list(dict.fromkeys(x['url'] for x in q['links']))
    if 'all_identifiers' not in q:
        q['all_identifiers'] = {key:list(q[key]) for key in ('doi','arxiv')}
    for key in ('doi','arxiv'):
        q[key] = [value for value in q['all_identifiers'][key]
                  if not any(value in x['url'] and x['role'] in ('related_data','related_code','alternate_version') for x in q['links'])]


def parse_reference(raw, fallback=None):
    q = parse_rules(raw)
    if q['parse_status'] == 'rules_complete' or fallback is None:
        return q
    model = fallback(raw, q)
    q['rule_draft'] = {k:q[k] for k in ('title', 'authors', 'year', 'container_title', 'notes')}
    for key in ('title', 'authors', 'year', 'container_title', 'volume', 'issue', 'pages', 'authors_truncated', 'notes', 'work_type'):
        if key in model:q[key] = model[key]
    if not q.get('title'):raise ValueError('Model must supply a grounded title')
    attach_evidence(q, 'llm')
    # Model roles must point to a literal URL and a verbatim context quote.
    for item in model.get('links', []):
        if item.get('role') not in ROLES:raise ValueError('Unknown link role')
        source = evidence(raw, item.get('evidence', ''), 'llm')
        if not source or item.get('url', '') not in source['quote']:
            raise ValueError('Link classification needs a source quote containing URL')
        for link in q['links']:
            if link['url'] == item['url'] and link['role'] == 'unknown':
                link.update(role=item['role'], certainty='unknown' if item['role']=='unknown' else 'model_inferred', method='llm', role_evidence=source)
    q['parse_status'] = 'llm_parsed'
    q['parser_method'] = 'rules+llm'
    q['review_reasons'] = ['仍有用途不明确的链接'] if any(x['role']=='unknown' for x in q['links']) else []
    finalize_urls(q)
    return q
