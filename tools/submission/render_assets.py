"""Render original code-native submission artwork. Requires Pillow, no AI image generation."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/submission'
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD='/System/Library/Fonts/Supplemental/Arial Bold.ttf'


def font(size,bold=False):return ImageFont.truetype(BOLD if bold else FONT,size)


def render():
    OUT.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGB',(1920,1080),'#f4f8f7');d=ImageDraw.Draw(image)
    d.rounded_rectangle((100,80,180,160),radius=25,fill='#087f75');d.text((121,87),'R',font=font(60,True),fill='white')
    d.text((215,104),'RYDE / DIGITAL NATIVE TRACK',font=font(26,True),fill='#54736e')
    d.text((100,244),'Fair ride disputes.',font=font(100,True),fill='#173d37')
    d.text((100,358),'Evidence-led decisions.',font=font(100,True),fill='#087f75')
    d.text((105,517),'Ryde Tribunal',font=font(46,True),fill='#173d37')
    d.text((105,588),'Two advocates. One impartial judge. A clear path to review.',font=font(28),fill='#54736e')
    for x,title,subtitle in [(105,'Rider Advocate','Builds the rider’s case'),(670,'Driver Advocate','Builds the driver’s case'),(1235,'Judge','Applies evidence and policy')]:
        d.rounded_rectangle((x,740,x+520,948),radius=22,fill='white',outline='#d7e7e2',width=3)
        d.rounded_rectangle((x+28,768,x+36,896),radius=4,fill='#087f75')
        d.text((x+60,785),title,font=font(32,True),fill='#173d37');d.text((x+60,852),subtitle,font=font(25),fill='#54736e')
    d.text((105,1008),'GPS + communications + fares  /  Published policy  /  Human review',font=font(23),fill='#54736e')
    image.save(OUT/'cover-1920x1080.png');image.resize((380,216),Image.Resampling.LANCZOS).save(OUT/'cover-380x216.png')
    svg='''<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900" viewBox="0 0 1440 900"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0 0 L9 3 L0 6" fill="#087f75"/></marker></defs><rect width="1440" height="900" fill="#f4f8f7"/><style>text{font-family:Arial,sans-serif;fill:#173d37}.title{font-size:34px;font-weight:bold}.head{font-size:22px;font-weight:bold}.sub{font-size:17px;fill:#54736e}.box{fill:white;stroke:#cee2dc;stroke-width:2;rx:16}.line{fill:none;stroke:#087f75;stroke-width:3;marker-end:url(#arrow)}</style><text x="70" y="70" class="title">Ryde Tribunal — evidence, policy and human oversight</text>'''
    boxes=[(70,125,570,110,'Reviewer workspace','File • inspect evidence • approve or override'),(70,320,250,130,'Rider Advocate','Read-only retrieval'),(390,320,250,130,'Driver Advocate','Read-only retrieval'),(760,320,300,130,'Impartial Judge','Claims + policy + facts'),(70,560,570,125,'Source records / PostgreSQL','GPS • fares • chat • events • profiles'),(760,125,570,110,'Current published policy','Official sources + distinct operating rules'),(760,560,570,125,'Validation and escalation','Citations • remedies • gaps • confidence'),(760,750,570,100,'Human review / recorded decision','Model proposal retained separately')]
    for x,y,w,h,title,sub in boxes:svg+=f'<rect class="box" x="{x}" y="{y}" width="{w}" height="{h}"/><text class="head" x="{x+24}" y="{y+44}">{title}</text><text class="sub" x="{x+24}" y="{y+82}">{sub.replace("&","&amp;")}</text>'
    for path in ['M180 235 V320','M500 235 V320','M195 560 V450','M515 560 V450','M320 385 H390','M640 385 H760','M1045 235 V320','M910 450 V560','M1045 685 V750']:
        svg+=f'<path class="line" d="{path}"/>'
    svg+='<text class="sub" x="70" y="790">Persisted agent actions and source provenance</text><text class="sub" x="70" y="825">No live outcome labels • No automated financial execution</text></svg>'
    (OUT/'architecture.svg').write_text(svg)


if __name__=='__main__':render()
