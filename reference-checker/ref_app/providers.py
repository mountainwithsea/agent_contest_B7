"""Provider adapters promoted from the recorded retrieval pilot; no fixed inputs."""
import json, re, html, urllib.parse, unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from difflib import SequenceMatcher
from reference_identity.evidence import norm
HERE=Path('.')
ENV={}
def candidate(source,title,authors=None,year=None,url=None,ids=None,venue=None,record_url=None,**extra):
    return {'source':source,'title':title or '', 'authors':authors or [],'year':str(year) if year else None,'url':url,
            'identifiers':ids or {},'venue':venue,'record_url':record_url or url,'evidence_kind':'metadata',**extra}


def score(inp,row):
    target,found=norm(inp['qwen'].get('title')),norm(row.get('title'))
    exact=bool(target and target==found)
    contains=bool(target and found and len(target)>15 and target in found)
    sim=SequenceMatcher(None,target,found).ratio() if target and found else 0
    if contains:sim=max(sim,.97)
    row['title_exact']=exact;row['title_contains']=contains;row['title_similarity']=round(sim,4)
    qauthors=inp['qwen'].get('authors',[]);first=qauthors[0]['literal'] if qauthors else ''
    fn=norm(first);allauthors=[norm(a) for a in row.get('authors',[])]
    row['first_author_literal_found']=bool(fn and any(fn==a or fn in a or a in fn for a in allauthors if a))
    row['year_agreement']='unknown' if not row.get('year') or not inp['qwen'].get('year') else 'same' if row['year']==inp['qwen']['year'] else 'different'
    return row


def extract(provider,record):
    if record['state']!='ok' or not record.get('raw_response'):return []
    raw=(HERE/record['raw_response']).read_text(encoding='utf-8')
    out=[]
    if provider=='arxiv':
        root=ET.fromstring(raw);ns={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom'}
        for r in root.findall('a:entry',ns):
            url=r.findtext('a:id',default='',namespaces=ns)
            if '/api/errors' in url:continue
            arxiv=url.split('/abs/')[-1] if '/abs/' in url else None
            doi=r.findtext('x:doi',default='',namespaces=ns)
            out.append(candidate(provider,re.sub(r'\s+',' ',r.findtext('a:title',default='',namespaces=ns)),
                [a.findtext('a:name',default='',namespaces=ns) for a in r.findall('a:author',ns)],
                r.findtext('a:published',default='',namespaces=ns)[:4],url,{'arxiv':arxiv,'doi':doi or None},
                published=r.findtext('a:published',default='',namespaces=ns),updated=r.findtext('a:updated',default='',namespaces=ns)))
    else:
        data=json.loads(raw)
        if provider=='crossref':
            message=data['message'];items=message.get('items',[message])
            for r in items:
                dates=r.get('published',r.get('issued',{})).get('date-parts',[[]]);year=dates[0][0] if dates and dates[0] else None
                doi=r.get('DOI');authors=[' '.join(filter(None,[a.get('given'),a.get('family')])) or a.get('name','') for a in r.get('author',[])]
                out.append(candidate(provider,'; '.join(r.get('title',[])),authors,year,r.get('URL'),{'doi':doi},'; '.join(r.get('container-title',[])),
                    'https://api.crossref.org/works/'+urllib.parse.quote(doi,safe='') if doi else None,type=r.get('type'),provider_score=r.get('score')))
        elif provider=='openalex':
            for r in data.get('results',[]):
                ids=r.get('ids',{});doi=(r.get('doi') or '').removeprefix('https://doi.org/') or None
                location=r.get('primary_location') or {};src=location.get('source') or {}
                out.append(candidate(provider,r.get('title'),[a.get('author',{}).get('display_name','') for a in r.get('authorships',[])],r.get('publication_year'),
                    location.get('landing_page_url') or r.get('id'),{'doi':doi,'openalex':r.get('id'),'pmid':ids.get('pmid')},src.get('display_name'),r.get('id'),type=r.get('type')))
        elif provider=='datacite':
            rows=data.get('data',[]);rows=rows if isinstance(rows,list) else [rows]
            for item in rows:
                r=item.get('attributes',{});doi=r.get('doi')
                related=r.get('relatedIdentifiers',[])
                out.append(candidate(provider,'; '.join(t.get('title','') for t in r.get('titles',[])),[a.get('name','') for a in r.get('creators',[])],r.get('publicationYear'),
                    r.get('url') or 'https://doi.org/'+str(doi),{'doi':doi},r.get('publisher'),'https://api.datacite.org/dois/'+str(doi),type=r.get('types',{}).get('resourceTypeGeneral'),related_identifiers=related))
        elif provider=='europepmc':
            for r in data.get('resultList',{}).get('result',[]):
                authors=[a.get('fullName') or a.get('collectiveName','') for a in r.get('authorList',{}).get('author',[])]
                out.append(candidate(provider,html.unescape(r.get('title','')),authors,r.get('pubYear'),'https://europepmc.org/article/'+r.get('source','MED')+'/'+r['id'],
                    {'doi':r.get('doi'),'pmid':r.get('pmid'),'pmcid':r.get('pmcid')},r.get('journalInfo',{}).get('journal',{}).get('title')))
        elif provider=='semantic_scholar':
            rows=data.get('data',[])
            for r in rows:
                ids=r.get('externalIds',{})
                out.append(candidate(provider,r.get('title'),[a.get('name','') for a in r.get('authors',[])],r.get('year'),r.get('url'),
                    {'doi':ids.get('DOI'),'arxiv':ids.get('ArXiv'),'pmid':ids.get('PubMed'),'s2':r.get('paperId')},r.get('venue')))
        elif provider=='dblp':
            hits=data.get('result',{}).get('hits',{}).get('hit',[])
            for hit in hits:
                r=hit.get('info',{});authors=r.get('authors',{}).get('author',[]);authors=authors if isinstance(authors,list) else [authors]
                out.append(candidate(provider,r.get('title'),[a.get('text','') if isinstance(a,dict) else a for a in authors],r.get('year'),r.get('ee') or r.get('url'),
                    {'doi':r.get('doi'),'dblp':r.get('key')},r.get('venue'),r.get('url'),type=r.get('type')))
        elif provider=='openlibrary':
            for r in data.get('docs',[]):
                out.append(candidate(provider,r.get('title'),r.get('author_name',[]),r.get('first_publish_year'),'https://openlibrary.org'+r['key'],
                    {'openlibrary':r['key'],'isbn':r.get('isbn',[])[:5]},type='book',edition_count=r.get('edition_count')))
        elif provider=='googlebooks':
            for item in data.get('items',[]):
                r=item.get('volumeInfo',{});isbn=[i['identifier'] for i in r.get('industryIdentifiers',[]) if i['type'].startswith('ISBN')]
                out.append(candidate(provider,r.get('title'),r.get('authors',[]),r.get('publishedDate','')[:4],r.get('infoLink'),{'isbn':isbn,'googlebooks':item['id']},r.get('publisher'),type='book'))
        elif provider=='deepseek':
            for r in data.get('results',[]):
                out.append(candidate(provider,r.get('title'),url=r.get('url'),record_url=r.get('url'),evidence_kind='search_result',
                    snippet=r.get('snippet'),summary=r.get('summary'),provider_score=r.get('rerank_score'),authority=r.get('authority'),
                    search_page_date=r.get('date'),site_name=r.get('site_name')))
    for r in out:r['request_id']=record['request_id']
    return out


def endpoint(provider,inp,variant=0):
    title=inp['title_variants'][min(variant,len(inp['title_variants'])-1)];q=inp['qwen'];body=None;headers={}
    if provider=='crossref':
        if q.get('doi') and variant==0:return 'https://api.crossref.org/works/'+urllib.parse.quote(q['doi'][0],safe=''),None,{}
        first=(q.get('authors') or [{}])[0].get('literal','')
        params={'query.bibliographic':title+' '+first,'rows':5}
        url='https://api.crossref.org/works?'+urllib.parse.urlencode(params)
    elif provider=='openalex':
        params={'search':title,'per-page':5}
        url='https://api.openalex.org/works?'+urllib.parse.urlencode(params)
    elif provider=='datacite':url='https://api.datacite.org/dois?'+urllib.parse.urlencode({'query':'titles.title:"'+title.replace('"','')+'"','page[size]':5})
    elif provider=='europepmc':url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':'TITLE:"'+title.replace('"','')+'"','format':'json','pageSize':5,'resultType':'core'})
    elif provider=='arxiv':
        params={'id_list':','.join(q['arxiv'])} if q.get('arxiv') and variant==0 else {'search_query':'ti:"'+title.replace('"','')+'"','start':0,'max_results':5}
        url='https://export.arxiv.org/api/query?'+urllib.parse.urlencode(params)
    elif provider=='semantic_scholar':
        params={'query':title,'limit':5,'fields':'title,authors,year,externalIds,url,venue,publicationDate'}
        url='https://api.semanticscholar.org/graph/v1/paper/search?'+urllib.parse.urlencode(params)
        if ENV.get('SEMANTIC_SCHOLAR_API_KEY'):headers['x-api-key']=ENV['SEMANTIC_SCHOLAR_API_KEY']
    elif provider=='dblp':url='https://dblp.org/search/publ/api?'+urllib.parse.urlencode({'q':title,'format':'json','h':5})
    elif provider=='openlibrary':url='https://openlibrary.org/search.json?'+urllib.parse.urlencode({'title':title,'limit':5,'fields':'key,title,author_name,first_publish_year,edition_count,isbn'})
    elif provider=='googlebooks':url='https://www.googleapis.com/books/v1/volumes?'+urllib.parse.urlencode({'q':'intitle:'+title,'maxResults':5})
    elif provider=='deepseek':
        # Search-only variants are bounded to the official 128-character limit.
        if variant==0:
            first=(q.get('authors') or [{}])[0].get('literal','').split()
            tail=(' '+first[-1]) if first and len(title)<100 else ''
            query=title+tail
        else:
            query=inp['title_variants'][-1]
            query=re.sub(r'[-–—]',' ',query)
        if len(query)>128:query=query[:128].rsplit(' ',1)[0]
        body={'query':query,'count':5,'need_content':False}
        url=ENV.get('DEEPSEEK_BASE_URL','https://api.deepseek.com').rstrip('/')+'/v1/tools/search'
        headers={'Authorization':'Bearer '+ENV.get('DEEPSEEK_API_KEY','')}
    else:raise ValueError(provider)
    return url,body,headers
