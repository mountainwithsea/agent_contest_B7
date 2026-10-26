"""Recover style-isolated bibliography headings embedded in another column.

Only split existing word objects. No title rewriting, source removal, model,
document names, page constants or expected reference counts are involved.
"""
from statistics import median
from .rules import HEADING


def _style(word):
    chars=word.get('chars',[])
    if not chars:return None
    return (round(median(c['size'] for c in chars),2),tuple(sorted({c['fontname'] for c in chars})))


def split_styled_headings(pieces,rows):
    refined=[];evidence={}
    for piece in pieces:
        if HEADING.fullmatch(' '.join(w['text'] for w in piece)):
            refined.append(piece);continue
        runs=[]
        for w in piece:
            if not runs or _style(w)!=_style(runs[-1][-1]):runs.append([w])
            else:runs[-1].append(w)
        cuts=set();proof={}
        offset=0
        for run in runs:
            start,end=offset,offset+len(run);offset=end
            style=_style(run[0])
            if not style or not HEADING.fullmatch(' '.join(w['text'] for w in run)):continue
            neighbors=[piece[i] for i in (start-1,end) if 0<=i<len(piece)]
            sizes=[s[0] for w in neighbors if (s:=_style(w))]
            if not sizes or style[0]<median(sizes)*1.2:continue
            gaps=[]
            if start:gaps.append(run[0]['x0']-piece[start-1]['x1'])
            if end<len(piece):gaps.append(piece[end]['x0']-run[-1]['x1'])
            # Ordinary inline word spacing is insufficient evidence of a column.
            if not gaps or min(gaps)<max(4,style[0]*.75):continue
            x=run[0]['x0'];support=0
            for row in rows:
                if any(w is run[0] for w in row):continue
                aligned=any(abs(w['x0']-x)<=max(2,style[0]*.2) for w in row)
                crossing=any(w['x0']<x-2 and w['x1']>x+2 for w in row)
                if aligned and not crossing:support+=1
            if support<3:continue
            cuts.update((start,end));proof[(start,end)]={
                'method':'larger_font_run_with_column_alignment','font_size':style[0],
                'adjacent_font_size':median(sizes),'minimum_gap_points':round(min(gaps),3),
                'aligned_other_rows':support}
        bounds=sorted({0,len(piece),*cuts})
        for a,b in zip(bounds,bounds[1:]):
            segment=piece[a:b]
            refined.append(segment)
            if (a,b) in proof:evidence[id(segment)]=proof[(a,b)]
    return refined,evidence
