"""Native parser adapters, promoted from the frozen comparison experiment."""
import hashlib
import json
import re
import statistics
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADAPTER_VERSION = 'native-structured-names-v2'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',str(value or '')).casefold() if c.isalnum())


def author_norm(value):
    # Ignore given/family serialization order for this one author, not author-list order.
    tokens = re.findall(r'[^\W_]+', unicodedata.normalize('NFKC',value or '').casefold())
    return sorted(tokens)


def text(node):
    return ''.join(node.itertext()).strip() if node is not None else None


def normalized_ids(values, kind):
    out=[]
    for val in values:
        if kind=='arxiv':
            match = re.search(r'(\d{4}\.\d{4,5}(?:v\d+)?)',val,re.I)
            if match:out.append(match[1].lower())
        elif kind=='doi':
            match = re.search(r'10\.\d{4,9}/\S+',val,re.I)
            if match:out.append(match[0].rstrip('.,;').lower())
    return sorted(set(out))


def grobid_rows(record):
    root=ET.fromstring(record['raw_response'])
    nodes=root.findall('.//{*}biblStruct')
    assert len(nodes)==len(record['ids']), ('GROBID row alignment',len(nodes),len(record['ids']))
    out=[]
    for cid,node,inp in zip(record['ids'],nodes,record['input']):
        returned = text(node.find('./{*}note[@type="raw_reference"]'))
        original = inp['raw_text']
        if returned != original and not (re.match(r'^\[[^\]\n]+\]', original) and returned == original[1:]):
            raise ValueError('GROBID source alignment')
        analytic=node.find('./{*}analytic')
        monogr=node.find('./{*}monogr')
        title_node=analytic.find('./{*}title') if analytic is not None else None
        if title_node is None and monogr is not None:
            title_node=next((t for t in monogr.findall('./{*}title') if t.get('level')=='m'),None)
        author_parent=analytic if analytic is not None and analytic.findall('./{*}author') else monogr
        authors=[]
        if author_parent is not None:
            for a in author_parent.findall('./{*}author'):
                p=a.find('./{*}persName')
                org=a.find('./{*}orgName')
                author={'literal':' '.join(filter(None,[text(x) for x in list(p)])) if p is not None else text(org) or text(a),
                        'kind':'person' if p is not None else 'organization' if org is not None else 'unknown'}
                if p is not None:
                    author.update(given=' '.join(filter(None,[text(x) for x in p.findall('./{*}forename')])),
                                  family=' '.join(filter(None,[text(x) for x in p.findall('./{*}surname')])))
                authors.append(author)
        date=node.find('.//{*}date')
        year_match=re.search(r'\d{4}',(date.get('when','')+' '+(text(date) or '')) if date is not None else '')
        ids=[{'type':i.get('type'), 'value':text(i)} for i in node.findall('.//{*}idno')]
        arxiv=[i['value'] for i in ids if (i['type'] or '').lower()=='arxiv' or re.search('arxiv|abs/',i['value'] or '',re.I)]
        doi=[i['value'] for i in ids if (i['type'] or '').lower()=='doi' or re.search(r'10\.\d{4,9}/',i['value'] or '')]
        journal=node.find('.//{*}title[@level="j"]')
        container_node=journal
        if container_node is None and analytic is not None and monogr is not None:container_node=monogr.find('./{*}title')
        scopes={s.get('unit'):text(s) or '-'.join(filter(None,[s.get('from'),s.get('to')])) for s in node.findall('.//{*}biblScope')}
        out.append({'id':cid,'title':text(title_node),'authors':authors,'year':year_match[0] if year_match else None,
                    'container_title':text(container_node),'arxiv':normalized_ids(arxiv,'arxiv'),'doi':normalized_ids(doi,'doi'),
                    'volume':scopes.get('volume'),'issue':scopes.get('issue'),'pages':scopes.get('page'),
                    'notes':[{'type':n.get('type'),'text':text(n)} for n in node.findall('./{*}note') if n.get('type')!='raw_reference'],
                    'native_identifiers':ids,'raw_reference_returned':text(node.find('./{*}note[@type="raw_reference"]')),
                    'native_xml':ET.tostring(node,encoding='unicode')})
    return out


def any_rows(record):
    data=json.loads(record['raw_export'])
    assert isinstance(data,list) and len(data)==len(record['ids']), 'AnyStyle row alignment'
    assert len(record['parsed_segments'])==len(record['input']), 'AnyStyle token rows'
    for tokens,inp in zip(record['parsed_segments'],record['input']):
        assert norm(' '.join(value for tag,value in tokens))==norm(inp['raw_text']), 'AnyStyle source alignment'
    out=[]
    for cid,row in zip(record['ids'],data):
        authors=[]
        for a in row.get('author',[]):
            literal=a.get('literal') or ' '.join(filter(None,[a.get('given'),a.get('dropping-particle'),a.get('non-dropping-particle'),a.get('particle'),a.get('family'),a.get('suffix')]))
            authors.append({'literal':literal,'kind':'literal' if a.get('literal') else 'structured_name',
                            **{k:a[k] for k in ('given','family','dropping-particle','non-dropping-particle','particle','suffix') if k in a}})
        dates=row.get('issued',{}).get('date-parts',[])
        year=str(dates[0][0]) if dates and dates[0] else None
        def values(key):
            val=row.get(key,[])
            return val if isinstance(val,list) else [val]
        out.append({'id':cid,'title':row.get('title'),'authors':authors,'year':year,
            'container_title':row.get('container-title'),'arxiv':normalized_ids(values('arxiv'),'arxiv'),
            'doi':normalized_ids(values('DOI'),'doi'),'pages':row.get('page'),'volume':row.get('volume'),'issue':row.get('issue'),
            'notes':row.get('note'), 'native_csl':row})
    return out
