"""Derived visual views of saved artifacts; never change reference decisions."""
import json
import threading
from pathlib import Path
from .jobs import atomic
from .qualification import span, folded
from reference_identity.evidence import sha

LOCK=threading.RLock()
FIELDS=('title','authors','year','container_title','doi','arxiv','pages','volume','issue')


def file_summary(references, job, extraction):
    """Existence categories are exclusive; diagnostic counts may overlap."""
    summary = dict(total=len(references), non_hallucinated=0, hallucinated=0,
                   undetermined=0, unverified=0, field_differences=0,
                   field_unverified=0, execution_issues=0,
                   uncertain_groups=extraction.get('uncertain_groups', 0),
                   state=job.get('state'), hallucination_policy='positive_existence_only')
    for ref in references:
        dimensions = (ref.get('result') or {}).get('dimensions', {})
        status = dimensions.get('existence', {}).get('status')
        category = 'non_hallucinated' if status == 'confirmed' else 'undetermined' if status else 'unverified'
        summary[category] += 1
        claims = dimensions.get('fields', {}).get('claims', [])
        summary['field_differences'] += any(c.get('status') == 'conflict' for c in claims)
        summary['field_unverified'] += any(c.get('status') == 'unknown' for c in claims)
        execution = dimensions.get('execution', {})
        summary['execution_issues'] += bool(execution.get('errors') or
            execution.get('status') not in (None, 'completed') or
            (ref.get('parsing') or {}).get('status') == 'tool_failure')
    return summary

def read(path,default=None):
    try:return json.loads(path.read_text('utf-8'))
    except (OSError,ValueError):return default

def geometry(result,document):
    refs=[];ownership={};warnings=[];available=set()
    for i,r in enumerate(result.get('references',[]),1):
        cid=f'R{i:03}'
        refs.append({'id':cid,'raw_text':r['raw_text'],'pages':r.get('pages',[]),'source_ids':r.get('source_ids',[]),'color':f'hsl({round((i-1)*137.508%360,2)} 65% 37%)'})
        for sid in r.get('source_ids',[]):
            if sid in ownership:warnings.append('文字块重复归属：'+sid)
            ownership.setdefault(sid,[]).append(cid)
    pages=[]
    for page in document.get('pages',[]):
        boxes=[];texts=[]
        for b in page.get('blocks',[]):
            available.add(b['id'])
            for cid in ownership.get(b['id'],[]):
                texts.append({'id':b['id'],'text':b.get('text',''),'ref_id':cid})
                box=b.get('bbox')
                if box and len(box)==4 and all(isinstance(x,(int,float)) for x in box):
                    boxes.append({'ref_id':cid,'source_id':b['id'],'bbox':box,'text':b.get('text','')})
        if texts:
            pages.append({'page':page['page'],'boxes':boxes,'text_blocks':texts,'width':page.get('width'),'height':page.get('height')})
            if len(boxes)<len(texts) and document.get('input_type') not in ('docx','txt'):
                warnings.append(f'第 {page["page"]} 页部分文字没有可靠坐标；不在原图伪造标注，另列彩色文本。')
    warnings.extend('缺少原文坐标块：'+sid for sid in ownership if sid not in available)
    return {'references':refs,'pages':pages,'warnings':warnings,'input_type':document.get('input_type'),'total_pages':len(document.get('pages',[])),
            'extraction_method':result.get('extraction_method'),'extraction_status':result.get('status'),'extraction_model_attempts':result.get('api_attempts',0),
            'uncertain_groups':len(result.get('uncertain',[]))}

def project_fields(ref,pages):
    """Project unique literal field matches onto actual PDF glyph bounds."""
    blocks={b['source_id']:(p['page'],b) for p in pages for b in p['boxes'] if b['ref_id']==ref['id']}
    text='';positions=[]
    for sid in ref['source_ids']:
        if sid not in blocks:continue
        page,b=blocks[sid]
        for c in b.get('chars',[]):
            text+=c['text'];positions.extend([(page,sid,c['bbox'])]*len(c['text']))
        text+=' ';positions.append(None)
    normalized,_=folded(text);out=[];unmapped=[]
    for field,value in ref['chosen'].items():
        for v in value if isinstance(value,list) else [value]:
            v=v.get('literal') if isinstance(v,dict) else v
            if v is None or v=='':continue
            v=str(v);needle,_=folded(v)
            hit=span(text,v) if needle and normalized.count(needle)==1 else None
            if not hit:
                unmapped.append({'field':field,'value':v});continue
            groups=[]
            for item in positions[hit['start']:hit['end']]:
                if item is None:continue
                page,sid,box=item
                if groups and groups[-1]['page']==page and groups[-1]['source_id']==sid and abs(groups[-1]['bbox'][1]-box[1])<5 and box[0]>=groups[-1]['bbox'][0]:
                    prev=groups[-1]['bbox'];groups[-1]['bbox']=[min(prev[0],box[0]),min(prev[1],box[1]),max(prev[2],box[2]),max(prev[3],box[3])]
                else:groups.append({'page':page,'source_id':sid,'bbox':list(box)})
            out.extend(dict(g,field=field,quote=hit['quote']) for g in groups)
    ref['field_boxes']=out;ref['unmapped_fields']=unmapped

def base_view(folder,job):
    attempts=sorted(folder.glob('extraction*/result.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    result_file=next((p for p in attempts if (read(p,{}) or {}).get('references')),None)
    if result_file is None:return {'references':[],'pages':[],'warnings':[],'pending':True}
    blocks_file=result_file.parent/'source-blocks.json'
    doc=read(blocks_file,{})
    if not doc:return {'references':[],'pages':[],'warnings':['原文坐标尚未保存。'],'pending':True}
    fingerprint='visual-v5-extraction-accounting:'+sha(result_file)+sha(blocks_file)+job['input_sha256']
    dest=folder/'visual';saved=read(dest/'geometry.json')
    if saved and saved.get('fingerprint')==fingerprint and all(not p.get('image') or (folder/p['image']).is_file() for p in saved['pages']):return saved
    data=geometry(read(result_file),doc);dest.mkdir(exist_ok=True)
    source=folder/job['input']
    if source.suffix.lower()=='.pdf':
        import pdfplumber
        with pdfplumber.open(source) as pdf:
            for page in data['pages']:
                pdfpage=pdf.pages[page['page']-1]
                for box in page['boxes']:
                    x0,y0,x1,y1=box['bbox'];chars=[]
                    for c in pdfpage.chars:
                        cx=(c['x0']+c['x1'])/2/pdfpage.width*1000;cy=(c['top']+c['bottom'])/2/pdfpage.height*1000
                        if x0-1<=cx<=x1+1 and y0-1<=cy<=y1+1:
                            chars.append({'text':c['text'],'bbox':[c['x0']/pdfpage.width*1000,c['top']/pdfpage.height*1000,c['x1']/pdfpage.width*1000,c['bottom']/pdfpage.height*1000]})
                    # Source blocks are normally lines; bucket baselines to tolerate superscripts.
                    chars.sort(key=lambda c:(round(c['bbox'][1]/5),c['bbox'][0]))
                    box['chars']=chars
                target=dest/f'page-{page["page"]}-300dpi.png'
                if not target.exists():pdf.pages[page['page']-1].to_image(resolution=300,antialias=True).save(target,quantize=False)
                page['image']=str(target.relative_to(folder)).replace('\\','/')
    elif source.suffix.lower() in ('.png','.jpg','.jpeg'):
        from PIL import Image,ImageOps
        target=dest/'page-1.png'
        with Image.open(source) as image:
            image=ImageOps.exif_transpose(image).convert('RGB');width,height=image.size;image.save(target)
        for page in data['pages']:page.update(image='visual/page-1.png',width=width,height=height)
    data.update(fingerprint=fingerprint,source_artifacts={str(p.relative_to(folder)).replace('\\','/'):sha(p) for p in (source,result_file,blocks_file)},
        image_hashes={p['image']:sha(folder/p['image']) for p in data['pages'] if p.get('image')})
    atomic(dest/'geometry.json',data)
    return data

def snapshot(folder,job):
    with LOCK:data=base_view(folder,job)
    # Work on a new read each time; extraction geometry cache is immutable here.
    qualified=read(folder/'public-parsing/result.json') or read(folder/'local-parsing/result.json') or []
    if not qualified:qualified=read(folder/'public-parsing/offline.json') or []
    byid={q['id']:q for q in qualified};results={r['id']:r for r in job.get('results',[])}
    for ref in data['references']:
        cid=ref['id'];q=byid.get(cid);r=results.get(cid);ref['result']=r
        chosen=(r or {}).get('input',{}).get('qwen')
        if not chosen and q and q.get('status') in ('ready_offline','ready_llm'):
            from .efficient import prepare
            chosen=prepare(q)
        ref['chosen']={k:(chosen or {}).get(k) for k in FIELDS}
        ref['parsing']=None
        if q:
            ref['parsing']={'status':q['status'],'reasons':q.get('reasons',[]),'pending_fields':q.get('pending_fields',[]),
                'source_evidence':q.get('source_evidence',{}),'title_evidence':q.get('title_evidence',[]),
                'tools':{name:{k:(record or {}).get('fields',{}).get(k) for k in FIELDS} for name,record in q.get('native_parsers',{}).items()},'soft_fields':q.get('soft_fields',{})}
        ref['spans']=[]
        for field,value in ref['chosen'].items():
            values=value if isinstance(value,list) else [value]
            for v in values:
                v=v.get('literal') if isinstance(v,dict) else v
                if isinstance(v,str) and (hit:=span(ref['raw_text'],v)):
                    ref['spans'].append({'field':field,**hit})
        project_fields(ref,data['pages'])
        ref['schedule']=read(folder/'retrieval/schedules'/f'{cid}.json',{}).get('providers',[])
    # Glyphs are only needed on the server; the browser receives merged field rectangles.
    for page in data['pages']:
        for box in page['boxes']:box.pop('chars',None)
    data['job_id']=job['id'];data['state']=job['state'];data['current']=job.get('current');data['summary']=job.get('summary')
    data['file_summary']=file_summary(data['references'],job,data)
    return data
