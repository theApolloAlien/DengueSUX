import datetime as dt
import numpy as np
import pandas as pd
from denguesux.pipeline import epi_calendar
from denguesux.model import chronological_split, make_model

def test_epi_calendar_preserves_sunday_saturday_and_53():
    rows=epi_calendar(); lookup={r[0]:r for r in rows}
    assert len(rows)==574
    assert lookup['2014-W53'][1]==dt.date(2014,12,28)
    assert lookup['2020-W53'][1]==dt.date(2020,12,27)
    assert all(r[1].weekday()==6 and r[2].weekday()==5 for r in rows)
    assert all((b[1]-a[1]).days==7 for a,b in zip(rows,rows[1:]))

def test_split_purges_targets_not_observable_at_next_origin():
    origins=pd.date_range('2017-01-01','2022-12-31',freq='W-SUN')
    frame=pd.DataFrame({'week_start':origins,'target_week_start':origins+pd.Timedelta(days=14),'issue_date':origins+pd.Timedelta(days=7),'target_week_end':origins+pd.Timedelta(days=20),'target_cases':10.})
    train,val,test=chronological_split(frame)
    assert train.target_week_end.max()<val.issue_date.min()
    assert val.target_week_end.max()<test.issue_date.min()
    assert set(train.index).isdisjoint(test.index)

def test_imputer_learns_training_median_and_keeps_missing_indicator():
    model=make_model(10)
    model.fit(pd.DataFrame({'rainfall':[0.,10.,np.nan,20.]}),[1,2,3,4])
    assert model.named_steps['impute'].statistics_[0]==10
    transformed=model.named_steps['impute'].transform(pd.DataFrame({'rainfall':[np.nan,1000.]}))
    assert transformed[0,0]==10 and transformed[0,1]==1
    assert transformed[1,0]==1000 and transformed[1,1]==0
