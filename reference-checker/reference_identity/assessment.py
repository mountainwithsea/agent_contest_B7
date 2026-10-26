"""Independent identity, bibliographic-field and execution outcomes.

Rules are shared by every input; no reference IDs or expected answers belong here.
"""
import re
from .evidence import norm, title_score


def name_forms(value):
    value=re.sub(r'(?<=\w)-\s+(?=\w)','',value)
    # Keep lexical surname compounds intact. Formatting changes do not permit
    # arbitrary token permutations or dropping surname particles.
    words=re.findall(r"[^\W_]+(?:[-’'][^\W_]+)*",value,flags=re.UNICODE)
    if len(words)<2:return []
    # Upper-case compact initials are common in biomedical bibliographies.
    def given(parts,compact=False):
        out=[]
        for part in parts:
            for token in re.findall(r'[^\W_]+',part):
                out.extend(list(token.lower()) if compact and token.isupper() and len(token)<=3 else [norm(token)])
        return out
    if ',' in value:
        family,first=value.split(',',1)
        return [(norm(family),given(re.findall(r'[^\W_]+',first),compact=True))]
    particles={'al','bin','da','de','del','della','der','di','dos','du','la','le','van','von','den','ten','ter'}
    boundary=len(words)-1
    while boundary>0 and words[boundary-1].casefold() in particles:boundary-=1
    forms=[(norm(' '.join(words[boundary:])),given(words[:boundary],compact=True))]
    # Reversal is allowed only when the remaining token(s) are initials.
    for boundary in range(1,len(words)):
        if all(len(w)==1 or (w.isupper() and len(w)<=3) for w in words[boundary:]):
            family=words[:boundary]
            if len(family)==1 or all(w.casefold() in particles for w in family[:-1]):
                forms.append((norm(' '.join(family)),given(words[boundary:],compact=True)))
    return forms


def name_matches(a,b):
    if norm(a)==norm(b):return True
    for family,first in name_forms(a):
        for other,last in name_forms(b):
            if family!=other or not first or not last:continue
            if len(first)!=len(last):continue
            if all(x==y or (min(len(x),len(y))==1 and x[0]==y[0]) for x,y in zip(first,last)):
                return True
    return False


def match_authors(cited,found):
    # Bipartite matching prevents one returned author satisfying two inputs.
    owner={}
    def assign(i,seen):
        for j,b in enumerate(found):
            if j in seen or not name_matches(cited[i],b):continue
            seen.add(j)
            if j not in owner or assign(owner[j],seen):owner[j]=i;return True
        return False
    for i in range(len(cited)):assign(i,set())
    reverse={i:j for j,i in owner.items()}
    return [{'input':a,'matched':found[reverse[i]] if i in reverse else None} for i,a in enumerate(cited)]


def assess(q,evidence,identifiers,verdict,errors,reviewed=True):
    cited=[a['literal'] for a in q.get('authors',[])]
    excluded={eid for item in identifiers if item['state']=='mismatch' for eid in item.get('evidence_ids',[])}
    anchors=[];candidates=[]
    identity_conflict=bool(reviewed and verdict and any(c['field'] in ('title','authors') and c['status']=='conflict' for c in verdict.get('claims',[])))
    def compatible_title(e):
        original=re.sub(r'(?<=\w)-\s+(?=\w)','',q.get('title',''))
        returned=e['data']['title']
        if norm(original)==norm(returned):return True
        # Similarity alone cannot distinguish parts, numbered follow-ups or
        # opposite claims in nearly identical titles.
        def markers(t):return re.findall(r'\b(?:\d+|[ivx]+|not|no|without)\b',t.casefold())
        if markers(original)!=markers(returned):return False
        return bool(reviewed and verdict and any(c['field']=='title' and c['status'] in ('match','explained') and any(x['evidence_id']==e['id'] for x in c['quotes']) for c in verdict['claims']))
    for e in evidence:
        if not e['usable'] or e['id'] in excluded:continue
        d=e.get('data',{})
        if not d.get('title') or title_score(q.get('title'),d['title'])<.94:continue
        candidates.append(e['id'])
        if e['kind']!='metadata':continue
        if identity_conflict or not compatible_title(e):continue
        if any(t in str(d.get('type','')).lower() for t in ('audiovisual','conference talk','dataset')):continue
        matches=match_authors(cited,d.get('authors',[]))
        # Full coverage replaces the old 80% shortcut. Name normalization is
        # evidence of bibliographic compatibility, not proof of personal identity.
        if cited and all(m['matched'] for m in matches):
            anchors.append({'evidence_id':e['id'],'title':d['title'],'matches':matches,'basis':'same_record_title_and_all_explicit_authors'})
    # For news/pages, require a reviewed title+byline on the same document,
    # with quoted names matching the input; search snippets never suffice.
    if verdict and reviewed and not identity_conflict and verdict.get('status')=='confirmed':
        for e in evidence:
            if not e['usable'] or e['kind']!='document' or e['id'] in excluded:continue
            title_quotes=[x['quote'] for c in verdict['claims'] if c['field']=='title' and c['status'] in ('match','explained') for x in c['quotes'] if x['evidence_id']==e['id']]
            author_quotes=[x['quote'] for c in verdict['claims'] if c['field']=='authors' and c['status'] in ('match','explained') for x in c['quotes'] if x['evidence_id']==e['id']]
            if not any(norm(q.get('title')) in norm(t) for t in title_quotes):continue
            # Whole normalized name is required for free-text bylines. Ambiguous
            # abbreviations can instead be resolved through structured records.
            text=' '+ ' '.join(re.findall(r'\w+',' '.join(author_quotes).casefold()))+' '
            if cited and all(' '+' '.join(re.findall(r'\w+',a.casefold()))+' ' in text for a in cited):
                anchors.append({'evidence_id':e['id'],'title':q['title'],'basis':'reviewed_document_title_and_byline','matches':[{'input':a,'matched':a} for a in cited]})
    status='confirmed' if anchors else 'candidate' if candidates or any(e['usable'] and e['kind']=='search' for e in evidence) else 'unknown'
    gaps=[] if anchors else ['缺少同一条书目记录或作品页面中的题名与全部明确作者对应证据；请针对作者／署名补查。']
    if identity_conflict:gaps.append('已复核的题名或作者存在身份冲突；需要进一步来源证据解决，不能用相似度覆盖。')
    claims=(verdict or {}).get('claims',[])
    field_issues=[c for c in claims if c['status'] in ('conflict','unknown','explained')]
    identifier_issues=[i for i in identifiers if i['origin']=='input' and i['state'] in ('mismatch','uncertain','unresolved')]
    field_status='issues' if field_issues or identifier_issues else 'assessed' if verdict else 'unavailable'
    return {'existence':{'status':status,'reason':'同一来源的题名及全部明确作者对应；字段和版本问题另列。' if anchors else '已找到线索但身份条件尚未满足。' if status=='candidate' else '当前证据不足；不能据此断言作品不存在。','matched_title':anchors[0]['title'] if anchors else (verdict or {}).get('matched_title',''),'evidence_ids':[a['evidence_id'] for a in anchors],'anchors':anchors,'gaps':gaps},
            'fields':{'status':field_status,'reviewed':reviewed and bool(verdict),'claims':claims,'identifier_issues':identifier_issues,'unresolved':(verdict or {}).get('unresolved',[])},
            'execution':{'status':'partial' if errors and (evidence or verdict) else 'failed' if errors else 'completed','errors':errors}}


def recovery_needed(result):
    return result['existence']['status']!='confirmed'
