"""Fixed safety copy. Symptom requests never reach a generative model."""
import json
import re
from pathlib import Path
SYMPTOMS=re.compile(r'\b(fever|vomit(?:ing)?|bleed(?:ing)?|unwell|symptoms?|diagnos(?:e|is)|headache|abdominal|rash|sick|ill|pain|nausea|aching|dizzy|fatigue|gejala|do i have dengue|could i have dengue|drowsy|clammy|breath(?:ing)?|demam|muntah|pendarahan|sakit)\b|发烧|發燒|呕吐|嘔吐|腹痛|出血|症状|症狀|காய்ச்சல்|வாந்தி|வலி|இரத்த',re.I)

def symptom_question(text):
    return bool(SYMPTOMS.search(str(text)))

def language_for(text,default='en'):
    if re.search('[\u0b80-\u0bff]',text):return 'ta'
    if re.search('[\u4e00-\u9fff]',text):return 'zh'
    if re.search(r'\b(demam|muntah|sakit|denggi)\b',text,re.I):return 'ms'
    return default if default in ('en','zh','ms','ta') else 'en'

def fixed_response(root,text,language='en'):
    copy=json.loads((Path(root)/'app/web/care-copy.json').read_text())
    lang=language_for(text,language);content=copy[lang]
    return {'answer':content['otherwise'],'cards':[{'type':'unwell','language':lang,'copy':content,'reviewed_at':copy['reviewed_at']}], 'sources':copy['sources'],'steps':[],'trace':[],'actions':[],'mode':'Fixed health guidance · not AI generated'}
