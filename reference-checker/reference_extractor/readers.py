from pathlib import Path
from statistics import median
from .heading_layout import split_styled_headings


def word_blocks(words, page_number, width, height):
    """Split visual rows at wide gaps; model determines reading order, not this function."""
    rows = []
    for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
        same_row=False
        if rows:
            anchor=max(rows[-1],key=lambda w:w['bottom']-w['top'])
            ah=anchor['bottom']-anchor['top'];wh=word['bottom']-word['top']
            overlap=min(anchor['bottom'],word['bottom'])-max(anchor['top'],word['top'])
            horizontal_free=all(min(w['x1'],word['x1'])-max(w['x0'],word['x0'])<=max(.5,min(w['x1']-w['x0'],word['x1']-word['x0'])*.15) for w in rows[-1])
            same_row=abs(word['top']-anchor['top'])<=3 or (horizontal_free and min(ah,wh)<max(ah,wh)*.9 and overlap>=min(ah,wh)*.45)
        if not same_row:
            rows.append([word])
        else:
            rows[-1].append(word)
    pieces = []
    for row in rows:
        row.sort(key=lambda w: w['x0'])
        current = []
        for word in row:
            if current and word['x0'] - current[-1]['x1'] > max(12, width * .025):
                pieces.append(current)
                current = []
            current.append(word)
        if current:
            pieces.append(current)
    pieces,heading_splits=split_styled_headings(pieces,rows)
    blocks = []
    for words in pieces:
        text = ' '.join(w['text'] for w in words).strip()
        if text:
            blocks.append({'id': f'p{page_number}-b{len(blocks)+1}', 'page': page_number,
                           'text': text, 'bbox': [
                               round(min(w['x0'] for w in words) / width * 1000, 2),
                               round(min(w['top'] for w in words) / height * 1000, 2),
                               round(max(w['x1'] for w in words) / width * 1000, 2),
                               round(max(w['bottom'] for w in words) / height * 1000, 2)]})
            chars=[c for w in words for c in w.get('chars',[])]
            if chars:
                blocks[-1]['font_size']=round(median(c['size'] for c in chars),2)
                blocks[-1]['font_names']=sorted({c['fontname'] for c in chars})
            if id(words) in heading_splits:
                blocks[-1]['heading_layout_evidence']=heading_splits[id(words)]
    return blocks


def render_pdf_page(path, page_number, output):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        pdf.pages[page_number - 1].to_image(resolution=180).save(output)


def read_document(path, workdir):
    path, workdir = Path(path), Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    pages = []
    if suffix == '.pdf':
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                raise ValueError('PDF contains no pages')
            for i, page in enumerate(pdf.pages, 1):
                blocks = word_blocks(page.extract_words(x_tolerance=1, y_tolerance=3, return_chars=True), i, page.width, page.height)
                pages.append({'page': i, 'blocks': blocks, 'reader': 'pdfplumber',
                              'width': page.width, 'height': page.height})
                # Keep the extracted source blocks, release pdfplumber's bulky
                # character/layout caches before reading the next physical page.
                page.close()
    elif suffix in ('.png', '.jpg', '.jpeg'):
        from PIL import Image, ImageOps
        target = workdir / 'page-1.png'
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.save(target)
        pages = [{'page': 1, 'blocks': [], 'image': str(target), 'reader': 'vision_transcription'}]
    elif suffix in ('.txt', '.docx'):
        if suffix == '.txt':
            lines = path.read_text(encoding='utf-8-sig').splitlines()
        else:
            from docx import Document
            from docx.text.paragraph import Paragraph
            document = Document(path)
            if document.element.xpath('.//w:txbxContent | .//w:ins | .//w:del | .//w:drawing'):
                raise ValueError('Word contains images/textboxes/revisions; export it to PDF or images for this version')
            lines = []
            for item in document.iter_inner_content():
                if isinstance(item, Paragraph):
                    lines.extend(item.text.splitlines())
                else:
                    for row in item.rows:
                        for cell in row.cells:
                            lines.extend(cell.text.splitlines())
        blocks = [{'id': f'p1-b{i+1}', 'page': 1, 'text': line.strip(), 'bbox': None}
                  for i, line in enumerate(line for line in lines if line.strip())]
        if not blocks:
            raise ValueError('No readable text found')
        pages = [{'page': 1, 'blocks': blocks, 'reader': suffix[1:]}]
    else:
        raise ValueError('Unsupported input; use PDF, DOCX, TXT, PNG or JPEG')
    return {'input_type': suffix[1:], 'pages': pages}
