"""Source-grounded bibliographic formatting, never inferred author identity.

Ideas: GB type boundaries (CheckIfExist), structured name variants and complete
coverage (RefChecker/Hallucinator). Independently implemented; see fix notes.
"""
import copy
import re
from collections import Counter
from functools import lru_cache
from reference_identity.assessment import name_matches, name_forms
from reference_identity.evidence import norm

TYPE_CODE=r'(?:EB/OL|DB/OL|J/OL|M/OL|C/OL|CP/OL|DS/OL|J|M|D|C|R|S|P|N|Z|EB|DB|CP|DS)'


def clean_title(raw, title, locate):
    """Separate a terminal type tag only when a full tag exists in the source.

    The original title, tag and offsets are retained. Interior brackets, real
    subtitles and parenthesized acronyms are not modified.
    """
    if not title:return title,[]
    terminal=re.search(r'\s*\[\s*'+TYPE_CODE+r'\s*\]?\s*[.,]?$',title,re.I)
    if not terminal:return title,[]
    core=title[:terminal.start()].rstrip()
    ev=locate(raw,core)
    if not core or not ev:return title,[]
    end=ev['end']
    trailing=re.search(r'[^\w]*$',core).group()
    if trailing and raw[end:].startswith(trailing):end+=len(trailing)
    tag=re.match(r'\s*(\[\s*'+TYPE_CODE+r'\s*\])(?=\s*[.,，。])',raw[end:],re.I)
    if not tag:return title,[]
    expected=re.sub(r'[^a-z/]', '',terminal.group().casefold())
    actual=re.sub(r'[^a-z/]', '',tag[1].casefold())
    if expected!=actual:return title,[]
    start=end+tag.start(1);end=end+tag.end(1)
    return core,[{'operation':'separate_document_type','original_title':title,
                  'document_type':actual.upper(),'source':{'start':start,'end':end,'quote':raw[start:end]}}]


def ground_authors(raw, title, candidates, locate):
    """Match each parser's entire author list to the entire pre-title prefix.

    Reordering within a name requires compatible surname/initial structure and
    exactly the same source tokens. No expansion of initials, author skipping,
    cross-comma stitching, or use of names from a candidate registry is allowed.
    """
    title_span=locate(raw,title)
    if not title_span:return [],{'method':'abstain','reason':'title_not_grounded'}
    start=0;end=title_span['start'];prefix=raw[:end]
    label=re.match(r'^\s*(?:\[[^\]\n]{1,40}\]|\d+[.)])\s*',prefix)
    if label:start=label.end()
    prefix=raw[start:end]
    truncated=bool(re.search(r'\bet\s+al\.?|等',prefix,re.I))
    ignored=list(re.finditer(r'\bet\s+al\.?|\b(?:18|19|20)\d{2}[a-z]?\b|等',prefix,re.I))
    masked=list(prefix)
    for hit in ignored:masked[hit.start():hit.end()]=' '*len(hit.group())
    tokens=list(re.finditer(r'[^\W_]+',''.join(masked),re.UNICODE))
    if not tokens:return [],{'method':'abstain','reason':'no_explicit_author_prefix'}
    def atoms(value):return Counter(norm(m) for m in re.findall(r'[^\W_]+',value,re.UNICODE))
    accepted=[]
    for parser,names in candidates.items():
        names=[a for a in names if norm(a.get('literal')) not in ('etal','others')]
        if not names:continue
        @lru_cache(None)
        def solve(i,j):
            while j<len(tokens) and tokens[j].group().casefold()=='and':j+=1
            if i==len(names):return () if j==len(tokens) else None
            name=names[i];literal=name.get('literal','');want=atoms(literal)
            if re.fullmatch(r'[A-Za-z][.]?',literal.strip()):return None
            # One source token per native token prevents full-name fabrication.
            size=sum(want.values());tail=j+size
            if not size or tail>len(tokens):return None
            left=start+tokens[j].start();right=start+tokens[tail-1].end()
            quote=raw[left:right]
            if atoms(quote)!=want or not name_matches(quote,literal):return None
            if re.search(r'[;；，]|\bet\s+al\b',quote,re.I):return None
            organization=name.get('kind')=='organization'
            if not organization and re.search(r'[&/|+、]|\band\b',quote,re.I):return None
            if ',' in quote:
                # Commas inside a name must genuinely delimit family, given.
                if re.search(r'[\u3400-\u9fff]',quote):return None
                if not organization:
                    if quote.count(',')!=1 or not name.get('family') or not name.get('given'):return None
                    family,given=quote.split(',',1)
                    if norm(family)!=norm(name['family']) or norm(given)!=norm(name['given']):return None
            rest=solve(i+1,tail)
            if rest is None:return None
            return ((left,right),)+rest
        bounds=solve(0,0)
        if bounds is None:continue
        grounded=[]
        for name,(left,right) in zip(names,bounds):
            item=copy.deepcopy(name);item.update(literal=raw[left:right],parser_literal=name['literal'],
                source={'start':left,'end':right,'quote':raw[left:right]},normalization='source_name_order')
            grounded.append(item)
        accepted.append((parser,grounded))
    if not accepted:return [],{'method':'abstain','reason':'author_prefix_not_completely_grounded','source_prefix':raw[start:end]}
    # Different supported segmentations remain ambiguous, even with the same tokens.
    shapes={tuple((a['source']['start'],a['source']['end']) for a in names) for _,names in accepted}
    if len(shapes)!=1:return [],{'method':'abstain','reason':'author_boundaries_disagree','source_prefix':raw[start:end]}
    return accepted[0][1],{'method':'complete_source_author_prefix','parsers':[p for p,_ in accepted],
                          'source':{'start':start,'end':end,'quote':raw[start:end]},'truncated':truncated}
