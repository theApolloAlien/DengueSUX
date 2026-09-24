"""Independent checks against persisted Delta outputs and exported evaluation."""
import json
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from pyspark.sql import functions as F
from shapely.geometry import shape
from denguesux.runtime import ROOT,get_spark,read_table
from denguesux.model import chronological_split


def verify_model(model):
    """Recompute exported metrics and check that selection and explanations agree."""
    pred=model['predictions']
    assert len(pred)==52
    assert len({p['target_date'] for p in pred})==len(pred)
    assert all('2022-01-02'<=p['target_date']<'2023-01-01' for p in pred)
    low,high=model['thresholds']['low'],model['thresholds']['high']
    def risk(value):
        return 'Low' if value<low else 'Medium' if value<high else 'High'
    for field,metrics_key in [('prediction','selected_metrics'),('baseline','baseline_metrics')]:
        measured=model[metrics_key]
        assert measured['n']==len(pred)
        assert abs(float(np.mean([abs(p['actual']-p[field]) for p in pred]))-measured['mae'])<1e-8
        assert abs(float(np.mean([risk(p['actual'])==risk(p[field]) for p in pred]))-measured['accuracy'])<1e-8
    assert model['metrics']==model['selected_metrics']
    candidates=model['validation_candidates']
    order=['baseline','ridge','gradient_boosting']
    expected=min(order,key=lambda key:(candidates[key]['selection_mae'],order.index(key)))
    assert model['selected_model']==expected
    assert model['selected_baseline']==(expected=='baseline')
    names={'baseline':'Four-week average','ridge':'Weather + trend ridge',
           'gradient_boosting':'Weather + trend gradient boosting'}
    assert model['name']==model['recommended_model']==names[expected]
    assert model['selection_details']['evaluation_used_for_selection'] is False
    first_issue=min(p['issue_date'] for p in pred)
    for fold in model['validation_folds']:
        assert fold['train_labels_through']<fold['first_issue_date']
        assert '2019-01-06'<=fold['validation_start']<=fold['validation_end']<first_issue
    for values in candidates.values():
        assert abs(values['selection_mae']-np.mean([values['by_year'][str(y)]['mae'] for y in (2019,2020,2021)]))<1e-8
    from datetime import date
    peak=max(pred,key=lambda row:row['actual'])
    assert model['peak_lead_time']['peak_week']==peak['target_date']
    for key,field in [('selected','prediction'),('baseline','baseline')]:
        first=next(row for row in pred if row[field]>=high and row['issue_date']<=peak['target_date'])
        lead=model['peak_lead_time'][key]
        assert first['issue_date']==lead['first_high_issue_date']
        weeks=(date.fromisoformat(peak['target_date'])-date.fromisoformat(first['issue_date'])).days/7
        assert weeks==(lead['weeks_before_peak'] if lead['weeks_before_peak'] is not None else lead['at_least_weeks_before_peak'])
    groups={'Recent cases','Time of year','Rain','Heat'}
    assert {f['feature'] for f in model['feature_importance']}==groups
    for p in pred:
        assert np.isfinite([p['actual'],p['prediction'],p['baseline']]).all()
        assert p['prediction']>=0 and p['baseline']>=0
        assert p['prediction']==p['selected_prediction']
        assert p['risk']==risk(p['prediction'])
        assert p['baseline_risk']==risk(p['baseline'])
        assert p['actual_risk']==risk(p['actual'])
        assert {f['feature'] for f in p['top_features']}==groups
        explained=max(0,p['explanation_base']+sum(f['value'] for f in p['top_features'])+p['explanation_remainder'])
        assert abs(explained-p['prediction'])<1e-7
        if expected=='baseline':
            assert p['prediction']==p['baseline']
            assert all(f['value']==0 for f in p['top_features'] if f['feature']!='Recent cases')
    return {'test_predictions':len(pred),'selected_model':expected}


def verify_current(current):
    """Reconcile shared area counts against unique source clusters and geometry."""
    clusters=current['clusters']['features']
    areas={area['code']:area for area in current['areas']}
    boundaries={f['properties']['code']:shape(f['geometry']) for f in current['boundaries']['features']}
    assert len(areas)==len(current['areas'])==55
    assert current['totals']['areas']==len(areas)
    assert set(areas)==set(boundaries)
    assert len({f['properties']['id'] for f in clusters})==len(clusters)==11
    national_cases=sum(f['properties']['cases'] for f in clusters)
    assert national_cases==101
    assert current['totals']['clusters']==len(clusters)
    assert current['totals']['cluster_cases']==national_cases
    counts,cases=defaultdict(int),defaultdict(int)
    unmatched=[]
    for feature in clusters:
        props,geometry=feature['properties'],shape(feature['geometry'])
        # Calculate overlap independently; touching a line alone has zero area.
        expected={code for code,boundary in boundaries.items() if geometry.intersection(boundary).area>0}
        assert len(props['area_codes'])==len(set(props['area_codes']))
        assert set(props['area_codes'])==expected
        assert set(props['area_names'])=={areas[code]['name'] for code in expected}
        if expected:
            assert props['area_code'] in expected
        else:
            assert props['area_code'] is None
        if not expected:
            unmatched.append(props['id'])
        for code in expected:
            counts[code]+=1
            cases[code]+=props['cases']
    assert sorted(current['methodology']['unmatched_clusters'])==sorted(unmatched)
    for code,area in areas.items():
        assert area['cluster_count']==counts[code]
        assert area['cluster_cases']==cases[code]
    # Area totals are associations, so a shared cluster is intentionally repeated.
    return {'unique_clusters':len(clusters),'unique_cluster_cases':national_cases,
            'area_cluster_associations':sum(counts.values()),'area_case_associations':sum(cases.values())}


def verify_tables(spark):
    national=read_table(spark,'silver_national_weekly')
    features=read_table(spark,'gold_national_features')
    areas=read_table(spark,'silver_area_weekly')
    assert national.count()==574
    assert national.select('week_start').distinct().count()==574
    assert national.filter(F.dayofweek('week_start')!=1).count()==0
    assert features.filter(F.datediff('target_week_start','week_start')!=14).count()==0
    observed=national.select(F.col('week_start').alias('target_week_start'),F.col('cases').alias('observed_target'))
    joined=features.join(observed,'target_week_start','inner')
    assert joined.filter(F.col('target_cases')!=F.col('observed_target')).count()==0
    assert areas.filter(F.col('local_cases').isNotNull()|F.col('cluster_count').isNotNull()).count()==0
    assert areas.select('area_code').distinct().count()==55
    assert areas.select('area_code','week_start').distinct().count()==areas.count()
    missing={}
    for metric in ['rainfall','temperature','humidity']:
        assert national.filter((F.col(metric+'_days')<7)&F.col(metric).isNotNull()).count()==0
        missing[metric]=national.filter((F.col('epi_year')>=2017)&F.col(metric).isNull()).count()
    matrix=features.toPandas();train,val,test=chronological_split(matrix)
    assert train.target_week_end.max()<val.issue_date.min()
    assert val.target_week_end.max()<test.issue_date.min()
    payload=json.loads((ROOT/'output/web/dashboard.json').read_text())
    persisted=read_table(spark,'gold_national_predictions').orderBy('target_date').toPandas()
    exported=sorted(payload['model']['predictions'],key=lambda row:row['target_date'])
    assert persisted.target_date.tolist()==[row['target_date'] for row in exported]
    assert np.allclose(persisted.prediction,[row['prediction'] for row in exported],atol=1e-10)
    persisted_areas={row.area_code:row.asDict() for row in read_table(spark,'gold_area_priorities').collect()}
    for area in payload['current']['areas']:
        assert persisted_areas[area['code']]['priority']==area['risk']
        assert persisted_areas[area['code']]['cluster_cases']==area['cluster_cases']
    model_result=verify_model(payload['model'])
    current_result=verify_current(payload['current'])
    assert payload['meta']['synthetic_data'] is False
    assert payload['model']['synthetic_data'] is False
    result={'status':'passed','national_weeks':574,'feature_origins':features.count(),**model_result,**current_result,
        'area_weeks':areas.count(),'incomplete_weather_weeks_2017_2022':missing,
        'checks':['Delta tables readable','CDC Sunday calendar','target is exact t+2 observed label','purged temporal splits',
                  'no invented historical area cases or clusters','missing weather preserved','unique area/week keys',
                  'selected and baseline metrics independently recomputed','selection excludes evaluation labels',
                  'selected predictor labels and additive explanations agree','clusters associated with every positive-area overlap',
                  'unique national cluster totals and overlapping area counts reconciled','no synthetic observations']}
    (ROOT/'output/verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':
    spark=get_spark()
    try:
        verify_tables(spark)
    finally:
        spark.stop()
