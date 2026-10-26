"""Conservative bibliography proposals from literal source blocks.

No expected counts, paper identifiers, gold partitions or external lookups.
Failed checks select the model fallback, never an empty 'success'.
"""
import re
import unicodedata
from collections import Counter
from statistics import median

from .schema import validate_partition

VERSION = 'rules-4'
HEADING = re.compile(r'^\s*(?:(?:\d+|[IVX]+)[.)]?\s+)?(?:references?|bibliography|works\s+cited|参考文献)\s*[:：]?\s*$', re.I)
END = re.compile(r'^\s*(?:(?:[A-Z]|\d+)[.)]?\s+)?(?:appendix|appendices|supplementary(?:\s+materials?)?|acknowledg(?:e)?ments?|conclusions?|discussion|concluding\s+remarks|author\s+contributions|结论|附录)(?:\s+[A-Z0-9])?\s*[:：]?\s*$', re.I)
PROSE = re.compile(r'^(?:We\s+(?:found|evaluated|performed|propose|present|show|report)|Our\s+(?:results|method|experiments)|This\s+(?:paper|study|section)|These\s+results|In\s+this\s+(?:paper|section))\b')
TITLED_END = re.compile(r'^(?:appendix|appendices|supplementary\s+materials?|附录)(?:\s+[A-Z0-9]+)?\s*[:：]\s*[^\n]{1,100}$', re.I)
APPENDIX_END = re.compile(r'^[A-Z](?:\.\d+)*[.)]?\s+(?:Additional|Experimental|Implementation|Hyperparameters?|Details|Limitations?|Applications?|Case\s+Study|Proofs?|Supplementary|Results|Analysis|Datasets?|Training|Evaluation|Examples?)\b[^\n]{0,100}$')
NUMBER = re.compile(r'^\s*(?:\[(\d{1,4})\]|\((\d{1,4})\)|(\d{1,4})[.)])\s+')
ALPHA_LABEL = re.compile(r'^\s*\[([A-Za-z][A-Za-z0-9+.-]{1,24})\]\s+')
YEAR = re.compile(r'\b(?:1[5-9]|20)\d{2}[a-z]?\b')
IDENTIFIER = re.compile(r'10\.\d{4,9}/\S+|arxiv\s*:?\s*\d{4}\.\d{4,5}|https?://', re.I)
VENUE = re.compile(r'\b(?:journal|proceedings|conference|transactions|press|preprint|pages?|vol\.?|doi|arxiv|datasets?|repository|documentation)\b|\d+\s*\(\d+\)\s*:|\d+[–-]\d+', re.I)
AUTHOR = re.compile(r'^(?:[A-ZÀ-Ž][\wÀ-ž’\'-]+,\s*(?:[A-Z]\.?|[A-Z][a-z]+)|(?:[A-Z]\.?\s+){1,3}[A-Z][\wÀ-ž’\'-]+|[A-ZÀ-Ž][\wÀ-ž’\'-]+\s+(?:[A-Z]\.?\s+|(?:van|von|de|der|da)\s+)*[A-ZÀ-Ž][\wÀ-ž’\'-]+)')


def number(text):
    m = NUMBER.match(text)
    return int(next(x for x in m.groups() if x)) if m else None


def marker_style(text):
    m=NUMBER.match(text)
    if not m:return 'alphanumeric' if ALPHA_LABEL.match(text) else None
    return 'bracket' if m.group(1) else 'parenthesis' if m.group(2) else 'plain'


def features(text):
    text = ALPHA_LABEL.sub('', NUMBER.sub('', text)).strip()
    name_text=''.join(c for c in unicodedata.normalize('NFKD',text.replace('¨','')) if not unicodedata.combining(c))
    found = {'year': bool(YEAR.search(text)), 'identifier': bool(IDENTIFIER.search(text)),
             'venue': bool(VENUE.search(text)), 'author_start': bool(AUTHOR.match(name_text) or re.match(r'^[A-Z][\w’\'-]+\s+[A-Z]{1,3}[.,]*(?:\s|$)',name_text) or re.match(r'^[A-Z][\w-]{1,40}\.\s+(?:1[5-9]|20)\d{2}[a-z]?\b',name_text) or re.match(r'^[A-Z]{2,12}\.\s+',name_text) or re.match(r'^[A-Z][\w’\'-]+\s+&\s+[A-Z][\w’\'-]+',name_text)),
             'length': len(text)}
    if re.match(r'^(?:In\s|Proceedings\b|Journal\b|Transactions\b|Workshop\b|Volume\b|Pages\b)',text):found['author_start']=False
    # A reference needs multiple semantic signals, not just a year or a number.
    found['bibliographic'] = len(text) >= 35 and (
        sum(found[k] for k in ('year', 'identifier', 'venue')) >= 2
        or found['author_start'] and found['year'] and len(text) >= 45)
    return found


def _rows(blocks):
    """Tiny font-metric shifts must not move a right-hand fragment before its line."""
    rows=[]
    for b in sorted(blocks,key=lambda b:(b['bbox'][1],b['bbox'][0])):
        box=b['bbox']
        if not rows or box[1]-rows[-1][0]['bbox'][1]>min(2,(box[3]-box[1])*.2):
            rows.append([b])
        else:rows[-1].append(b)
    return [b for row in rows for b in sorted(row,key=lambda b:b['bbox'][0])]


def reading_order(document):
    """Read narrow columns separately; full-width lines separate column bands."""
    result = []; layouts = []
    for page in document['pages']:
        blocks = page['blocks']
        if not blocks or not all(b.get('bbox') for b in blocks):
            result.extend(blocks);layouts.append({'page':page['page'],'columns':None});continue
        narrow = [b for b in blocks if b['bbox'][2]-b['bbox'][0] < 470]
        long_lines=[b for b in narrow if b['bbox'][2]-b['bbox'][0]>=150]
        pairs=[]
        for left in long_lines:
            lb=left['bbox']
            if lb[0]>=450:continue
            for right in long_lines:
                rb=right['bbox']
                if rb[0]>450 and rb[0]-lb[2]>=10 and abs(rb[1]-lb[1])<=max(lb[3]-lb[1],rb[3]-rb[1])*1.5:
                    pairs.append((lb[2]+rb[0])/2)
        starts = sorted(b['bbox'][0] for b in long_lines)
        gaps = [(b-a,(a+b)/2) for a,b in zip(starts,starts[1:]) if b-a>180]
        boundary = median(pairs) if len(pairs)>=2 else max(gaps)[1] if gaps else None
        if boundary and (sum(x<boundary for x in starts)<2 or sum(x>=boundary for x in starts)<2):boundary=None
        if boundary is None:
            result.extend(_rows(blocks))
            layouts.append({'page':page['page'],'columns':1});continue
        wide = sorted([b for b in blocks if b['bbox'][0]<boundary<b['bbox'][2] and b['bbox'][2]-b['bbox'][0]>=470],key=lambda b:b['bbox'][1])
        pending = [b for b in blocks if b not in wide]
        def emit_band(band):
            result.extend(_rows([b for b in band if b['bbox'][0]<boundary]))
            result.extend(_rows([b for b in band if b['bbox'][0]>=boundary]))
        for separator in wide:
            before=[b for b in pending if b['bbox'][1]<separator['bbox'][1]]
            emit_band(before);pending=[b for b in pending if b not in before];result.append(separator)
        emit_band(pending);layouts.append({'page':page['page'],'columns':2,'boundary':boundary})
    return result,layouts


def _noise(blocks):
    marginal=Counter(b['text'].strip() for b in blocks if b.get('bbox') and (b['bbox'][3]<80 or b['bbox'][1]>925))
    result={}
    for b in blocks:
        box=b.get('bbox');text=b['text'].strip()
        if not box:continue
        if (box[1]>925 or box[3]<65) and re.fullmatch(r'\d{1,4}(?:\s*/\s*\d{1,4})?',text):result[b['id']]='isolated_marginal_page_number'
        elif (box[3]<80 or box[1]>925) and marginal[text]>=2 and not HEADING.fullmatch(text) and number(text) is None and (not features(text)['bibliographic'] or ('|' in text and re.search(r'https?://',text) and YEAR.search(text))):
            result[b['id']]='repeated_marginal_header_footer'
    return result


def numbered_context_support(evidence, numbers, heading=False):
    """Incomplete metadata must not invalidate an otherwise supported list.

    This only relaxes entry semantics, never geometry, coverage or end checks.
    A numeral alone cannot establish bibliographic identity.
    """
    if len(numbers) < (2 if heading else 3) or any(n is None for n in numbers):
        return set()
    if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        return set()
    strong = sum(f['bibliographic'] for f in evidence)
    author_venue = lambda f: f['author_start'] and f['venue']
    supported = (strong >= 2 and strong * 2 >= len(evidence)) or (
        heading and len(evidence) >= 3 and all(author_venue(f) for f in evidence))
    return {i for i, f in enumerate(evidence) if author_venue(f)} if supported else set()


def _partition_candidate(content, start, stop, mode, heading, column_map):
    segment=content[start:stop];refs=[];excluded=[];issues=[]
    if mode in ('numbered','labelled'):
        style=marker_style(segment[0]['text'])
        anchors={}
        for b in segment:
            if marker_style(b['text'])==style and b.get('bbox'):
                key=column_map[b['id']];anchors[key]=min(anchors.get(key,1000),b['bbox'][0])
        previous_number=None
        for b in segment:
            if HEADING.fullmatch(b['text']):excluded.append({'source_ids':[b['id']],'reason':'reference_heading'});continue
            is_marker=marker_style(b['text'])==style
            if is_marker and b.get('bbox') and abs(b['bbox'][0]-anchors[column_map[b['id']]])>12:
                f=features(b['text'])
                if style!='plain' or number(b['text'])==(previous_number or 0)+1 or f['author_start'] and f['year'] and not 1500<=number(b['text'])<=2099:
                    issues.append('misaligned_reference_marker')
                is_marker=False
            if is_marker:
                refs.append({'source_ids':[]});previous_number=number(b['text'])
            if not refs:
                issues.append('unassigned_prefix');continue
            refs[-1]['source_ids'].append(b['id'])
    else:
        # Only geometric evidence permits unnumbered automatic grouping.
        usable=[b for b in segment if not HEADING.fullmatch(b['text'])]
        boxes=[b['bbox'] for b in usable if b.get('bbox')]
        if len(boxes)!=len(usable) or not boxes:return None
        heights=[box[3]-box[1] for box in boxes];h=median(heights)
        anchors={}
        for b in usable:
            key=column_map[b['id']]
            anchors[key]=min(anchors.get(key,1000),b['bbox'][0])
        previous=None
        for b in segment:
            if HEADING.fullmatch(b['text']):excluded.append({'source_ids':[b['id']],'reason':'reference_heading'});continue
            box=b['bbox'];is_anchor=abs(box[0]-anchors[column_map[b['id']]])<=7
            gap=box[1]-previous['bbox'][3] if previous and column_map[previous['id']]==column_map[b['id']] else h
            author=features(b['text'])['author_start']
            new=is_anchor and author and (not refs or gap>h*.4)
            if new:refs.append({'source_ids':[]})
            if not refs:return None
            if previous and is_anchor and not new and gap>h*.5:issues.append('ambiguous_paragraph_boundary')
            refs[-1]['source_ids'].append(b['id']);previous=b
        # Hanging indents must repeat, rather than merely paragraphs with names.
        lookup={b['id']:b for b in segment}
        hanging=sum(len(r['source_ids'])>=2 and lookup[r['source_ids'][1]]['bbox'][0]-lookup[r['source_ids'][0]]['bbox'][0]>12 for r in refs)
        if hanging<3:issues.append('insufficient_repeated_layout')
    lookup={b['id']:b for b in segment}
    evidence=[]
    for ref in refs:
        text=' '.join(lookup[i]['text'] for i in ref['source_ids'])
        f=features(text);evidence.append({'source_ids':ref['source_ids'],**f})
        if len(text)>3500:issues.append('oversized_entry')
        # A new prose paragraph cannot be silently swallowed by the last marker.
        for a,z in zip(ref['source_ids'],ref['source_ids'][1:]):
            a,z=lookup[a],lookup[z];ab,zb=a.get('bbox'),z.get('bbox')
            if PROSE.match(z['text']):issues.append('prose_inside_entry')
            if ab and zb and column_map[a['id']]==column_map[z['id']] and zb[1]>ab[3] and zb[1]-ab[3]>(ab[3]-ab[1])*.55:
                issues.append('ambiguous_paragraph_boundary')
    numbers=[number(lookup[r['source_ids'][0]]['text']) for r in refs]
    context = numbered_context_support(evidence, numbers, heading) if mode == 'numbered' else set()
    notes = []
    for i, f in enumerate(evidence):
        if not f['bibliographic']:
            if i in context:
                notes.append({'source_ids': refs[i]['source_ids'], 'reason': 'metadata_incomplete_numbered_entry',
                              'evidence': 'Consecutive markers, author and venue; grouping retained independently of missing year or identifier'})
            else:
                issues.append('weak_bibliographic_entry')
    if mode=='numbered' and numbers and numbers!=list(range(numbers[0],numbers[0]+len(numbers))):issues.append('number_sequence')
    if mode=='labelled':
        labels=[ALPHA_LABEL.match(lookup[r['source_ids'][0]]['text']).group(1) for r in refs]
        if len(labels)!=len(set(labels)):issues.append('duplicate_reference_label')
    if len(refs)<(2 if heading else 3):issues.append('insufficient_repetition')
    return {'references':refs,'excluded':excluded,'uncertain':[],'issues':sorted(set(issues)),
            'entry_features':evidence,'entry_notes':notes,'original_numbers':numbers,'mode':mode,'start':start,'stop':stop,'heading':heading}


def analyze(document):
    ordered,layouts=reading_order(document);noise=_noise(ordered)
    content=[b for b in ordered if b['id'] not in noise]
    layout_by_page={x['page']:x for x in layouts}
    column_map={b['id']:(b['page'],bool(b.get('bbox') and b['bbox'][0]>=layout_by_page[b['page']].get('boundary',1001))) for b in ordered}
    def section_end(b, previous):
        text=b['text'].strip()
        if END.fullmatch(text) or TITLED_END.fullmatch(text):return 'explicit_heading'
        if APPENDIX_END.fullmatch(text):return 'topic_heading_hint'
        sizes=[x['font_size'] for x in previous[-24:] if x.get('font_size') and len(x['text'])>20 and not HEADING.fullmatch(x['text'])]
        normal_font=median(sizes) if len(sizes)>=2 else None
        # Small-cap section heads may have a deceptively small reported font.
        # Require section notation, uppercase words, and a clear vertical break.
        if previous and re.fullmatch(r'[A-Z](?:\.\d+)*[.)]?\s+[A-Z][A-Z -]{8,}',text):
            before=previous[-1];ab,bb=before.get('bbox'),b.get('bbox')
            if ab and bb and before['page']==b['page'] and bb[1]-ab[3]>(ab[3]-ab[1]) and len(sizes)>=2:
                return 'small_caps_hint'
        # Relative typography generalizes beyond a list of appendix topic words.
        if normal_font and b.get('font_size',0)>normal_font*1.12 and len(text)<100 and not features(text)['bibliographic'] and not HEADING.fullmatch(text) and number(text) is None:
            if re.match(r'^(?:[A-Z](?:\.\d+)*[.)]?\s+)?[A-Z][A-Za-z ’“”"/:;-]{3,}$',text):return 'typographic_hint'
        return False
    candidates=[]
    headings=[i for i,b in enumerate(content) if HEADING.fullmatch(b['text'])]
    starts=headings[:]
    # Also permit cropped numbered materials; each restart proposes a region.
    markers=[i for i,b in enumerate(content) if number(b['text']) is not None]
    for j,i in enumerate(markers):
        if j==0 or number(content[i]['text'])!=number(content[markers[j-1]]['text'])+1:starts.append(i)
    if not headings and not markers:
        starts.extend(i for i,b in enumerate(content) if features(b['text'])['author_start'])
    for start in sorted(set(starts)):
        heading=bool(HEADING.fullmatch(content[start]['text']))
        stop=next((j for j in range(start+1,len(content)) if section_end(content[j],content[max(start+1,j-24):j])),len(content))
        first=start+1 if heading else start
        if first>=stop:continue
        style=marker_style(content[first]['text'])
        mode='labelled' if style=='alphanumeric' else 'numbered' if style else 'layout'
        candidate=_partition_candidate(content,first,stop,mode,heading,column_map)
        if candidate:
            candidate['end_kind']=section_end(content[stop],content[max(start+1,stop-24):stop]) if stop<len(content) else 'end_of_received_material'
            if candidate['end_kind'] not in ('explicit_heading','end_of_received_material'):
                candidate['issues'].append('ambiguous_typographic_boundary')
            candidate['region_start']=start;candidates.append(candidate)
    # Prefer complete coverage and earlier repeated headings. Never prefer a
    # clean tail over an earlier rejected candidate within the same bibliography.
    supported=[c for c in candidates if len(c['references'])>=2]
    chosen=max(supported,key=lambda c:(c['heading'],len(c['references']),-c['region_start'])) if supported else None
    result={'version':VERSION,'accepted':False,'issues':['no_supported_region'],'layouts':layouts,
            'candidates':[{'start':c['start'],'stop':c['stop'],'mode':c['mode'],'entries':len(c['references']),'issues':c['issues']} for c in candidates],
            'block_features':[{'source_id':b['id'],**features(b['text'])} for b in ordered]}
    if not chosen:return result
    issues=chosen['issues'][:]
    # Do not omit a separate list or restart elsewhere in the document.
    inside={b['id'] for b in content[chosen['region_start']:chosen['stop']]}
    outside_markers=[b['id'] for b in content if b['id'] not in inside and marker_style(b['text']) is not None and features(b['text'])['bibliographic']]
    if outside_markers:issues.append('other_bibliographic_markers_outside_region')
    if any(HEADING.fullmatch(b['text']) and b['id'] not in inside for b in content):issues.append('other_reference_heading_outside_region')
    # A preceding numbered marker or author-like indented line may be a cropped
    # first entry; decline automatic acceptance rather than drop it.
    if not chosen['heading'] and chosen['region_start']:
        previous=content[chosen['region_start']-1]
        if chosen['mode']=='layout' or features(previous['text'])['bibliographic'] or number(previous['text']) is not None:issues.append('ambiguous_start')
    refs=chosen['references'];used={i for r in refs for i in r['source_ids']}
    if refs and chosen['stop']<len(content):
        lookup={b['id']:b for b in content}
        last_features=features(' '.join(lookup[i]['text'] for i in refs[-1]['source_ids']))
        if not (last_features['venue'] or last_features['identifier']):issues.append('ambiguous_end')
    exclusions=[]
    for b in ordered:
        if b['id'] not in used:
            reason=noise.get(b['id']) or ('reference_heading' if HEADING.fullmatch(b['text']) else 'outside_reference_region')
            exclusions.append({'source_ids':[b['id']],'reason':reason})
    partition={'references':refs,'excluded':exclusions,'uncertain':[]}
    if refs:validate_partition(partition,ordered)
    selected=sorted({b['page'] for b in ordered if b['id'] in used})
    result.update(accepted=bool(refs) and not issues,issues=sorted(set(issues)),partition=partition,
                  original_numbers=chosen['original_numbers'],mode=chosen['mode'],entry_features=chosen['entry_features'],entry_notes=chosen['entry_notes'],
                  selection={'reference_pages':selected,'reason':'Repeated bibliographic entries with region, numbering and source-coverage checks','uncertain':bool(issues)},
                  boundaries={'first_source_id':refs[0]['source_ids'][0] if refs else None,'last_source_id':refs[-1]['source_ids'][-1] if refs else None,
                              'end_reason':'next_section_heading' if chosen['stop']<len(content) else 'end_of_received_material','end_evidence':chosen['end_kind'],
                              'end_source_id':content[chosen['stop']]['id'] if chosen['stop']<len(content) else None},
                  checks={'all_input_blocks_assigned_once':bool(refs),'number_sequence': 'passed' if chosen['mode']=='numbered' and 'number_sequence' not in issues else 'failed' if chosen['mode']=='numbered' else 'not_applicable',
                          'outside_bibliographic_markers':outside_markers,'entry_semantics':'passed' if 'weak_bibliographic_entry' not in issues else 'failed'})
    return result
