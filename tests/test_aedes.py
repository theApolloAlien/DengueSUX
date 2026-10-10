import pytest
from denguesux.aedes import normalize

def feature(stamp):
    return {'type':'Feature','properties':{'Description':f'<table><tr><th>FMEL_UPD_D</th><td>{stamp}</td></tr><tr><th>OBJECTID</th><td>10</td></tr></table>','description':'April to June 2019'},'geometry':{'type':'Polygon','coordinates':[[[103.8,1.3],[103.81,1.3],[103.81,1.31],[103.8,1.31],[103.8,1.3]]]}}

def test_source_date_is_feature_stamp_not_dataset_description():
    r=normalize({'type':'FeatureCollection','features':[feature('20260929120000')]})
    assert r['source_date']=='2026-09-29'
    assert r['features'][0]['properties']['source_date']=='2026-09-29'
    assert r['skipped_invalid']==[]

def test_missing_feature_date_fails_closed():
    with pytest.raises(ValueError,match='stamp'):
        normalize({'type':'FeatureCollection','features':[feature('')]})

def test_invalid_polygon_is_disclosed_not_silently_repaired():
    invalid=feature('20260929120000');invalid['geometry']['coordinates']=[[[0,0],[1,1],[0,1],[1,0],[0,0]]]
    r=normalize({'type':'FeatureCollection','features':[feature('20260929120000'),invalid]})
    assert len(r['features'])==1 and r['skipped_invalid']==['10']
