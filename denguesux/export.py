"""Produce one real-data application payload; static bundle is portable to displayHTML."""
import datetime as dt
import json
from .runtime import ROOT
from .labels import combined_contract, contract_for_file, freshness


def _label_status(root=ROOT):
    path = root / 'data/raw/dengue/national_bulletin.csv.gz'
    receipt_path = path.with_suffix(path.suffix + '.receipt.json')
    if not path.exists():
        return {'available': False, 'reason': 'No verified weekly label file is present', 'source_kind': 'unavailable'}
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    retrieved = receipt.get('retrieved_at_utc', dt.datetime.now(dt.timezone.utc).isoformat())
    if (root / 'data/raw/dengue/moh_weekly_dengue.csv.gz').exists():
        contract = combined_contract(root, retrieved_at=retrieved)
    else:
        contract = contract_for_file(path, source_url=receipt.get('source_url', 'https://data.gov.sg/datasets/d_ca168b2cb763640d72c4600a68f9909e/view'),
                                     retrieved_at=retrieved)
    gate = freshness(contract, as_of=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date())
    return {'contract': {k: v for k, v in contract.items() if k != 'frame_rows'}, 'gate': gate, 'source_kind': contract['source_kind']}

def export_dashboard(current=None,model=None):
    out=ROOT/'output/web';out.mkdir(parents=True,exist_ok=True)
    current=current or json.loads((out/'current.json').read_text())
    model=model or json.loads((out/'model.json').read_text())
    labels = _label_status()
    result={'meta':{'name':'DengueSUX','generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'mode':'Live forecast when labels pass freshness gate; otherwise historical backtest + current leading-signal priorities','synthetic_data':False,
        'forecast_state': 'live_available' if labels.get('gate',{}).get('available') else 'historical_backtest_only',
        'forecast_state_reason': labels.get('gate',{}).get('reasons', ['No recent official weekly labels']),
        'labels': labels,
        'sources':[{'name':'NEA active clusters','url':'https://data.gov.sg/datasets/d_dbfabf16158d1b0e1c420627c0819168/view'},
                   {'name':'URA Master Plan 2025 boundaries','url':'https://data.gov.sg/datasets/d_2cc750190544007400b2cfd5d7f53209/view'},
                   {'name':'Weekly national infectious disease bulletin','url':'https://data.gov.sg/datasets/d_ca168b2cb763640d72c4600a68f9909e/view'},
                   {'name':'NEA weather collections','url':'https://data.gov.sg/collections'}]},'current':current,'model':model}
    for name in ('inspection', 'growth', 'notices', 'alerts', 'footprints', 'population', 'aedes', 'feed'):
        path=out/f'{name}.json'
        if path.exists(): result[name]=json.loads(path.read_text())
    (out/'dashboard.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False))
    return result
