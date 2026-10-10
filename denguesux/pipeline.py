"""Small PySpark/Delta medallion stages shared by local runner and notebooks."""
import datetime as dt
import gzip
import json
from pathlib import Path
from epiweeks import Week
from pyspark.sql import functions as F, Window
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType, BooleanType, DateType
from shapely.geometry import Point, shape
from .runtime import ROOT, read_table, write_table
from .spatial import read_geo

METRICS=['rainfall','temperature','humidity']

def epi_calendar(start=2012,end=None):
    end=end or dt.date.today().year
    result=[]
    for year in range(start,end+1):
        for week in range(1,54):
            try: ew=Week(year,week,system='cdc')
            except ValueError: continue
            result.append((f'{year}-W{week:02}',ew.startdate(),ew.enddate(),year,week))
    return result

def bronze(spark):
    source=ROOT/'data/raw/dengue/national_bulletin.csv.gz'
    raw=spark.read.option('header',True).schema('epi_week string, disease string, cases string').csv(str(source))
    write_table(raw.withColumn('source_dataset_id',F.lit('d_ca168b2cb763640d72c4600a68f9909e')),'bronze_bulletin')
    # data.gov.sg stops at 2022-W52; MOH/CDA yearly workbooks continue the same national series.
    workbook=ROOT/'data/raw/dengue/moh_weekly_dengue.csv.gz'
    if workbook.exists():
        moh=spark.read.option('header',True).schema('epi_week string, disease string, cases int, printed_week_range string, source_url string, source_sha256 string, retrieved_at_utc string').csv(str(workbook))
        write_table(moh,'bronze_moh_weekly')
    daily=ROOT/'data/phase2_inputs/weather_station_days.csv.gz'
    if not daily.exists(): raise FileNotFoundError('Run scripts/prepare_weather.py first: '+str(daily))
    weather=spark.read.option('header',True).option('inferSchema',True).csv(str(daily))
    write_table(weather,'bronze_weather_station_days')
    geo=[]
    for kind,path in [('boundaries',ROOT/'data/raw/boundaries/planning_areas_2025.geojson.gz'),('clusters',ROOT/'data/raw/dengue/active_clusters.geojson.gz')]:
        with gzip.open(path,'rt') as f: geo.append((kind,str(path.relative_to(ROOT)),f.read()))
    write_table(spark.createDataFrame(geo,'kind string, source_path string, payload string'),'bronze_geojson')
    receipts=[]
    for p in (ROOT/'data/raw').rglob('*.receipt.json'):
        r=json.loads(p.read_text())
        receipts.append((str(p.relative_to(ROOT)),json.dumps(r)))
    write_table(spark.createDataFrame(receipts,'receipt_path string, payload string'),'bronze_source_receipts')
    print('BRONZE: original archives retained; bulletin, source envelopes and complete station-day extracts in Delta.')

def sunday(column):
    return F.date_sub(F.to_date(column),F.dayofweek(F.to_date(column))-1)

def silver(spark):
    calendar=spark.createDataFrame(epi_calendar(),'epi_week string, week_start date, week_end date, epi_year int, epi_number int')
    raw=read_table(spark,'bronze_bulletin').select('epi_week','disease','cases').filter(F.col('epi_week')<'2023-W01')
    if (ROOT/'data/raw/dengue/moh_weekly_dengue.csv.gz').exists():
        moh=read_table(spark,'bronze_moh_weekly').filter(F.col('epi_week')>='2023-W01').select('epi_week','disease',F.col('cases').cast('string').alias('cases'))
        raw=raw.unionByName(moh)
    cases=(raw.filter(F.col('disease').isin('Dengue Fever','Dengue Haemorrhagic Fever'))
           .groupBy('epi_week').agg(F.sum(F.col('cases').cast('int')).alias('cases'),F.count('*').alias('disease_rows')))
    if cases.filter((F.col('disease_rows')!=2)|F.col('cases').isNull()).count(): raise ValueError('Missing/duplicate dengue rows')
    latest=cases.agg(F.max('epi_week')).first()[0]
    national=calendar.filter(F.col('epi_week')<=latest).join(cases,'epi_week','left')
    if national.filter(F.col('cases').isNull()).count(): raise ValueError('Bulletin calendar not complete')
    days=read_table(spark,'bronze_weather_station_days').withColumn('date',F.to_date('date')).withColumn('usable',F.col('usable').cast('boolean'))
    clean=days.withColumn('clean_value',F.when(F.col('usable') & F.col('value').isNotNull(),F.col('value').cast('double')))
    national_days=(clean.groupBy('metric','date').agg(F.avg('clean_value').alias('value'),F.count('clean_value').alias('usable_stations'))
                   .withColumn('week_start',sunday('date')))
    weekly=national_days.groupBy('metric','week_start').agg(F.count('value').alias('observed_days'),F.avg('value').alias('daily_mean'),F.min('usable_stations').alias('minimum_stations'))
    # Keep a weekly weather value only when all 7 days have at least one usable station.
    weekly=weekly.withColumn('value',F.when(F.col('observed_days')==7,F.col('daily_mean')*F.when(F.col('metric')=='rainfall',F.lit(7.0)).otherwise(F.lit(1.0))))
    for metric in METRICS:
        part=weekly.filter(F.col('metric')==metric).select('week_start',F.col('value').alias(metric),F.col('observed_days').alias(metric+'_days'),F.col('minimum_stations').alias(metric+'_stations'))
        national=national.join(part,'week_start','left')
    write_table(national.orderBy('week_start'),'silver_national_weekly')
    write_table(clean,'silver_weather_station_days')
    # Historical area weather uses stations physically inside fixed 2025 polygons. No invented case labels.
    features=read_geo(ROOT/'data/raw/boundaries/planning_areas_2025.geojson.gz')['features']
    area_geoms=[(f['properties']['PLN_AREA_C'],shape(f['geometry'])) for f in features]
    locations=clean.select('station_id','latitude','longitude').dropDuplicates().collect()
    rows=[]
    for r in locations:
        if r.latitude is None or r.longitude is None: continue
        found=sorted(code for code,g in area_geoms if g.covers(Point(float(r.longitude),float(r.latitude))))
        if found: rows.append((r.station_id,float(r.latitude),float(r.longitude),found[0]))
    mapping=spark.createDataFrame(rows,'station_id string, latitude double, longitude double, area_code string')
    area_days=(clean.join(mapping,['station_id','latitude','longitude'],'inner')
               .groupBy('area_code','metric','date').agg(F.avg('clean_value').alias('value')).withColumn('week_start',sunday('date')))
    area_weekly=area_days.groupBy('area_code','metric','week_start').agg(F.count('value').alias('observed_days'),F.avg('value').alias('daily_mean'))
    area_weekly=area_weekly.withColumn('value',F.when(F.col('observed_days')==7,F.col('daily_mean')*F.when(F.col('metric')=='rainfall',7.0).otherwise(1.0)))
    area_meta=spark.createDataFrame([(f['properties']['PLN_AREA_C'],f['properties']['PLN_AREA_N']) for f in features],'area_code string, area_name string')
    grid=area_meta.crossJoin(calendar.filter(F.col('epi_year')>=2017).select('week_start','week_end','epi_week'))
    for metric in METRICS:
        part=area_weekly.filter(F.col('metric')==metric).select('area_code','week_start',F.col('value').alias(metric),F.col('observed_days').alias(metric+'_days'))
        grid=grid.join(part,['area_code','week_start'],'left')
    grid=grid.withColumn('local_cases',F.lit(None).cast('int')).withColumn('cluster_count',F.lit(None).cast('int')).withColumn('boundary_edition',F.lit('URA 2025'))
    write_table(grid,'silver_area_weekly')
    print('SILVER: Sunday–Saturday national and planning-area weekly tables; unavailable area outcomes remain null.')

def gold(spark):
    weekly=read_table(spark,'silver_national_weekly')
    w=Window.orderBy('week_start')
    df=weekly
    for metric in METRICS:
        for lag in range(1,9):
            df=df.withColumn(f'{metric}_lag_{lag}',F.lag(metric,lag).over(w))
    for lag in range(1,9): df=df.withColumn(f'cases_lag_{lag}',F.lag('cases',lag).over(w))
    df=(df.withColumn('cases_current',F.col('cases').cast('double'))
        .withColumn('cases_mean_4',F.avg('cases').over(w.rowsBetween(-3,0)))
        .withColumn('cases_trend',F.col('cases')-F.col('cases_lag_2'))
        .withColumn('target_cases',F.lead('cases',2).over(w).cast('double'))
        .withColumn('target_week_start',F.date_add('week_start',14))
        .withColumn('target_week_end',F.date_add('week_end',14))
        .withColumn('issue_date',F.date_add('week_end',1))
        .withColumn('season_sin',F.sin(F.col('epi_number')*2*3.141592653589793/52.1775))
        .withColumn('season_cos',F.cos(F.col('epi_number')*2*3.141592653589793/52.1775))
        .filter(F.col('week_start')>=F.lit('2017-03-05').cast('date')))
    write_table(df,'gold_national_features')
    # Small supervised matrix only is collected; all weekly transforms above use PySpark.
    from .model import train_and_evaluate
    from .export import _label_status
    label_status = _label_status()
    result,predictions=train_and_evaluate(df.toPandas(), label_metadata={
        'available': bool(label_status.get('gate', {}).get('available')),
        'reason': '; '.join(label_status.get('gate', {}).get('reasons', [])) or 'Recent official weekly labels passed the freshness gate.',
        'mode': 'live_forecast' if label_status.get('gate', {}).get('available') else 'historical_backtest',
        'latest_label_week_end': label_status.get('gate', {}).get('latest_week_end'),
        'max_age_days': label_status.get('gate', {}).get('max_age_days'),
        'source': label_status.get('source_kind'),
    })
    write_table(spark.createDataFrame(predictions),'gold_national_predictions')
    from .spatial import build_current
    current=build_current()
    area_rows=[(a['code'],a['name'],a['risk'],a['score'],a['cluster_count'],a['cluster_cases'],current['weather_date']) for a in current['areas']]
    write_table(spark.createDataFrame(area_rows,'area_code string, area_name string, priority string, heuristic_score double, cluster_count int, cluster_cases int, weather_date string'),'gold_area_priorities')
    from .growth import write_growth
    from .inspection import build_inspection
    from .notices import write_notices
    write_growth(spark=spark)
    build_inspection(spark=spark)
    write_notices(spark=spark)
    from .alerts import write_alerts
    write_alerts(spark=spark)
    from .map_context import build_map_context
    build_map_context()
    from .export import export_dashboard
    export_dashboard(current,result)
    genie_layer(spark,current)
    print('GOLD: national predictions, MLflow evaluation, dated priorities, inspection plans, cluster comparisons and resident drafts exported.')

def genie_layer(spark,current=None):
    """Planning-area lookup (with region), readable places view and Unity Catalog comments for the Genie space."""
    from .genie_layer import apply_governance, statements
    from .runtime import TABLE_PREFIX
    if not TABLE_PREFIX: return print('GENIE: skipped, no Unity Catalog table prefix configured.')
    if current is None:
        from .spatial import build_current
        current=build_current()
    for statement in statements(TABLE_PREFIX,[(a['code'],a['name'],a['region']) for a in current['areas']]): spark.sql(statement)
    apply_governance(spark.sql, TABLE_PREFIX)
    print('GENIE: dim_planning_area, inspection_places view, comments and best-effort tags refreshed.')
