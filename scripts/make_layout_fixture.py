#!/usr/bin/env python3
"""Generate a synthetic Persian advertisement for layout/spacing regression tests.
This is NOT the user's original advertisement and does not establish accuracy on it.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]
FONT=ROOT/'tx/assets/fonts/Vazirmatn[wght].ttf'
OUT=ROOT/'tests/fixtures/persian-poster.png'
W,H=1400,1900
im=Image.new('RGB',(W,H),'#F6F1E9');d=ImageDraw.Draw(im)
def fa(text,xy,size=36,fill='#253D35',anchor='ra'):
 d.text(xy,text,font=ImageFont.truetype(str(FONT),size),fill=fill,direction='rtl',language='fa',anchor=anchor)
def en(text,xy,size=36,fill='#253D35',anchor='la'):
 d.text(xy,text,font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',size),fill=fill,anchor=anchor)
d.rounded_rectangle((45,40,1355,1855),radius=38,fill='white',outline='#D9E2DB',width=2)
en('COMFORT YOU FEEL, STYLE YOU LOVE',(90,85),35)
fa('۱۸۱,۲۷۷',(1290,160),48)
fa('شلوار زنانه لاکچری',(1290,250),64)
fa('شلواری که برای بانوان خوش سلیقه طراحی شده',(1290,355),37)
fa('تا در تمام لحظات روز همراهی مطمئن و شایسته باشد.',(1290,415),35)
d.rounded_rectangle((85,510,1315,650),radius=20,fill='#E5EFE8')
fa('بهترین جنس، نرم، لطیف و ضدحساسیت',(1260,548),43)
features=[
 ('کمر کشی با دوخت دوبخیه','راحتی بی‌نظیر بدون فشار و جمع شدن'),
 ('دوخت عالی و تمیز','با دستان ماهرترین خیاط‌ها'),
 ('مناسب دخترا و خانم‌ها','استایل شیک، رسمی و روزمره'),
 ('دوام و ماندگاری بالا','کیفیت تضمین شده در هر بار شستشو'),
 ('مناسب برای هر موقعیت','سایزبندی کامل، ۳۸ تا ۵۴'),
 ('آزادی حرکت','محیط کار، دانشگاه، مهمانی'),
 ('بدون محدودیت','و استفاده روزمره'),
 ('فروش تکی و عمده','قیمت همکاری فوق‌العاده برای فروشنده‌ها'),
]
y=710
for i,(a,b) in enumerate(features):
 d.ellipse((1270,y+9,1288,y+27),fill='#37745C')
 fa(a,(1245,y),38)
 fa(b,(1245,y+58),30,fill='#65776D')
 y+=122
d.rounded_rectangle((90,1710,1310,1815),radius=22,fill='#285843')
fa('همین حالا سفارش دهید!',(1245,1728),43,fill='white')
fa('ارسال سریع به سراسر کشور',(590,1740),31,fill='white')
OUT.parent.mkdir(parents=True,exist_ok=True);im.save(OUT)
print(OUT)
