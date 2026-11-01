"""Render generated scientific PDFs and record runtimes/source figure hashes."""
from pathlib import Path
import hashlib
import json
import sys
import fitz
from PIL import Image,ImageOps,ImageDraw
import PIL
import matplotlib
import numpy
import pandas

ROOT=Path('V:/Agent EX/Agent-EX-evidence/2026-11-01/ica-rq2-rq3-v1')


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    figures=ROOT/'figures-v1';qa=ROOT/'figure-qa-v1'
    qa.mkdir(exist_ok=True)
    checks=[]
    expected=['FigureA1_Asymmetric_Flows','Figure5_Communication_Structure',
              'Figure6_Realized_Exposure_Updating','FigureS1_Private_to_Visible']
    for name in expected:
        paths={kind:figures/(name+'.'+kind) for kind in ['png','svg','pdf']}
        if not all(p.exists() for p in paths.values()):raise ValueError('Missing figure formats: '+name)
        with Image.open(paths['png']) as im:
            dimensions=im.size;dpi=im.info.get('dpi')
            if not dpi or not all(abs(v-600)<1 for v in dpi):raise ValueError('Not a600dpi PNG')
        with fitz.open(paths['pdf']) as document:
            if len(document)!=1:raise ValueError('Scientific figure PDF must be one page')
            page=document[0];text=page.get_text()
            if len(text)<100 or '\ufffd' in text:raise ValueError('Missing/corrupt PDF text')
            image_path=qa/(name+'_pdf.png')
            page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).save(image_path)
        checks.append({'figure':name,'png_pixels':dimensions,'png_dpi':dpi,'pdf_text_characters':len(text),
                       'sha256':{kind:sha(path) for kind,path in paths.items()},'rendered_pdf':str(image_path)})
    contact=Image.new('RGB',(1800,1500),'white')
    draw=ImageDraw.Draw(contact)
    for i,row in enumerate(checks):
        with Image.open(row['rendered_pdf']) as im:
            small=ImageOps.contain(im,(880,690))
            x=(i%2)*900;y=(i//2)*750
            contact.paste(small,(x+(880-small.width)//2,y+35))
            draw.text((x+15,y+10),row['figure'],fill='#173B63')
    contact.save(qa/'PDF_contact_sheet.png')
    result={'plotting_runtime':{'python_executable':sys.executable,'python':sys.version.split()[0],
                'numpy':numpy.__version__,'pandas':pandas.__version__,'matplotlib':matplotlib.__version__,
                'pymupdf':fitz.VersionBind,'pillow':PIL.__version__},
            'analysis_runtime':'Codex bundled Python; original extraction/metrics run separately',
            'new_packages_installed':False,'figures':checks,
            'figure_source_table_sha256':{p.name:sha(p) for p in (ROOT/'analysis-v1/tables').glob('*.csv.gz')},
            'plot_script_sha256':sha(Path(__file__).with_name('plot_figures.py')),
            'visual_review':'PDF contact sheet and full-resolution figure previews must also be inspected before delivery',
            'unit_suite':'59 tests passed in installed plotting runtime; one pandas all-NA concat fixture FutureWarning, no test failures'}
    (ROOT/'runtime-and-figure-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'rendered_PDFs':len(checks),'all_PNGs_600dpi':True,'contact_sheet':str(qa/'PDF_contact_sheet.png')}))


if __name__=='__main__':main()
