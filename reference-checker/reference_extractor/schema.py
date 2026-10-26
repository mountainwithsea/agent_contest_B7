from collections import Counter
import math


def validate_pages(value, available, allow_empty=False):
    if not isinstance(value, dict) or not isinstance(value.get('reference_pages'), list):
        raise ValueError('reference_pages must be a list of page numbers')
    pages = value['reference_pages']
    if ((not pages and not allow_empty) or any(type(n) is not int or n not in available for n in pages)
            or len(pages) != len(set(pages))):
        raise ValueError('reference_pages must be nonempty, unique, valid integer page numbers')
    if not isinstance(value.get('reason'), str):
        raise ValueError('Page selection needs a reason')


def validate_partition(value, blocks, allow_empty=False):
    if not isinstance(value, dict):
        raise ValueError('Response must be a JSON object')
    ids = [b['id'] for b in blocks]
    if len(set(ids)) != len(ids):
        raise ValueError('Input source IDs are not unique')
    used = []
    for category in ['references', 'excluded', 'uncertain']:
        entries = value.get(category)
        if not isinstance(entries, list):
            raise ValueError(category + ' must be a list')
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(category + ' entries must be objects, not strings')
            source_ids = entry.get('source_ids')
            if (not isinstance(source_ids, list) or not source_ids
                    or any(not isinstance(i, str) for i in source_ids)):
                raise ValueError('Every entry needs a nonempty list of source_ids strings')
            if category != 'references' and not isinstance(entry.get('reason'), str):
                raise ValueError(category + ' entries need a reason')
            used.extend(source_ids)
    extra = set(used) - set(ids)
    missing = set(ids) - set(used)
    duplicates = [i for i, n in Counter(used).items() if n > 1]
    if extra or missing or duplicates:
        raise ValueError(f'Coverage error: unknown={sorted(extra)}, missing={sorted(missing)}, duplicate={duplicates}')
    if not value['references'] and not allow_empty:
        raise ValueError('No references extracted; review the input instead of reporting empty success')


def normalize_ocr(value):
    """Adapt native grounding boxes; no text edits and no guessed confidence."""
    if isinstance(value, list):
        blocks = value
    elif isinstance(value, dict) and isinstance(value.get('blocks'), list):
        blocks = value['blocks']
    else:
        raise ValueError('OCR must return blocks or native text/bbox_2d objects')
    normalized = [];discarded_blank_blocks=0
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError('OCR block must be an object')
        if isinstance(block.get('text'),str) and not block['text'].strip() and block.get('uncertain') is False:
            discarded_blank_blocks+=1
            continue
        normalized.append({'text': block.get('text'),
                           'bbox': block.get('bbox', block.get('bbox_2d')),
                           'uncertain': block.get('uncertain', True)})
    return {'blocks': normalized,'discarded_blank_blocks':discarded_blank_blocks}


def validate_ocr(value):
    value = normalize_ocr(value)
    if not isinstance(value, dict) or not isinstance(value.get('blocks'), list) or not value['blocks']:
        raise ValueError('OCR must return a nonempty blocks list')
    for block in value['blocks']:
        if not isinstance(block, dict) or not isinstance(block.get('text'), str) or not block['text'].strip():
            raise ValueError('Each OCR block needs nonempty text')
        if type(block.get('uncertain')) is not bool:
            raise ValueError('OCR uncertain must be a boolean')
        box = block.get('bbox')
        if box is None:
            continue
        if (not isinstance(box, list) or len(box) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1000 for v in box)
                or box[0] >= box[2] or box[1] >= box[3]):
            raise ValueError('OCR bbox must be [x0,y0,x1,y1], 0..1000 with positive dimensions')
