"""Render only a temporary label using Hancom's installed HFT font; never attach to an open document."""
import json
import os
from pathlib import Path
import site
import sys
ROOT=Path(__file__).resolve().parents[1]
site.addsitedir(str(ROOT/'.runtime/packages'))
sys.path.insert(0,str(ROOT/'.runtime/packages'))
if (ROOT/'.runtime/packages/pywin32_system32').exists():
    dll=os.add_dll_directory(str(ROOT/'.runtime/packages/pywin32_system32'))
from pyhwpx import Hwp
import pymupdf
from PIL import Image,ImageOps

def main():
    request=Path(sys.argv[1]);out=Path(sys.argv[2]);data=json.loads(request.read_text(encoding='utf-8'))
    hwp=Hwp(new=True,visible=False)
    try:
        page=hwp.get_pagedef()
        page.PageDef.PaperWidth=round(1100*100)
        page.PageDef.PaperHeight=round(800*100)
        for margin in ('LeftMargin','RightMargin','TopMargin','BottomMargin'):setattr(page.PageDef,margin,1000)
        page.PageDef.HeaderLen=0;page.PageDef.FooterLen=0
        hwp.set_pagedef(page)
        hwp.insert_text(data['text'])
        hwp.HAction.Run('SelectAll')
        shape=hwp.CharShape
        for lang in ('Hangul','Latin','Hanja','Japanese','Other','Symbol','User'):
            shape.SetItem('FaceName'+lang,'신명 중명조')
            shape.SetItem('FontType'+lang,2)
        shape.SetItem('Height',round(data['size']*100))
        hwp.CharShape=shape
        applied=hwp.CharShape
        if applied.Item('FaceNameHangul')!='신명 중명조' or applied.Item('FontTypeHangul')!=2: raise ValueError('신명 중명조 HFT 글꼴 적용 실패')
        pdf=out.with_suffix('.pdf')
        if not hwp.save_as(str(pdf),'PDF'): raise ValueError('한글 PDF 출력 실패')
        doc=pymupdf.open(pdf)
        if len(doc)!=1: raise ValueError('글씨가 너무 큽니다. 객체를 나누거나 크기를 줄이세요.')
        spans=[s for b in doc[0].get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']]
        fonts=[s['font'] for s in spans]
        # Keep proof of the font the PDF actually used, not only a requested face name.
        out.with_suffix('.font.json').write_text(json.dumps({'face':applied.Item('FaceNameHangul'),'type':applied.Item('FontTypeHangul'),'pdf_fonts':doc[0].get_fonts(full=True)},ensure_ascii=False),encoding='utf-8')
        # Hancom emits its HFT outlines as anonymous Type3 fonts (T1, T2...).
        if not fonts or not all(f[2]=='Type3' for f in doc[0].get_fonts(full=True)): raise ValueError('신명 중명조 HFT 윤곽선 출력 확인 실패')
        pix=doc[0].get_pixmap(matrix=pymupdf.Matrix(3,3),alpha=False)
        image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        mask=ImageOps.invert(image.convert('L'));box=mask.getbbox()
        if not box: raise ValueError('빈 글씨 출력')
        glyph=Image.new('RGBA',(box[2]-box[0]+6,box[3]-box[1]+6),(0,0,0,0))
        ink=Image.new('RGBA',(box[2]-box[0],box[3]-box[1]),(0,0,0,255));ink.putalpha(mask.crop(box));glyph.paste(ink,(3,3))
        glyph.save(out)
        doc.close()
    finally:
        hwp.quit(save=False)

if __name__=='__main__':main()
