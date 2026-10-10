import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from denguesux import assistant as A
from denguesux.chat_cards import CARD_SCHEMA, build_cards

DATA=json.loads((Path(__file__).resolve().parents[1]/'output/web/dashboard.json').read_text())

def test_cards_are_typed_and_use_tool_values():
    rows=[]
    for name, args in [('get_area',{'area':'Bishan'}),('top_areas',{}),('inspection_plan',{'area':'Bishan'}),('forecast_week',{})]:
        result,_=A.TOOLS[name]['fn'](DATA,**args)
        rows.append({'tool':name,'result':result})
    cards=build_cards(rows,DATA)
    assert len(CARD_SCHEMA.validate_python(cards))==4
    assert cards[0]['people']==rows[0]['result']['people_in_clusters']
    assert cards[2]['stops']==len(rows[2]['result']['stops'])
    assert cards[3]['prediction']==rows[3]['result']['forecast_people']
    assert cards[0]['trend']=='14-day trend unavailable'

def test_error_results_cannot_be_rendered_as_facts():
    assert build_cards([{'tool':'get_area','result':{'error':'unknown_area'}}],DATA)==[]
    with pytest.raises(ValidationError):
        CARD_SCHEMA.validate_python([{'type':'area','people':'model invented number'}])
