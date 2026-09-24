import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get('DENGUE_ROOT', Path(__file__).resolve().parents[1]))
TABLE_PREFIX = os.environ.get('DENGUE_TABLE_PREFIX', '')

def get_spark(existing=None):
    if existing is not None:
        return existing
    from pyspark.sql import SparkSession
    if os.environ.get('DATABRICKS_RUNTIME_VERSION'):
        return SparkSession.builder.getOrCreate()
    from delta import configure_spark_with_delta_pip
    os.environ.setdefault('SPARK_LOCAL_IP', '127.0.0.1')
    os.environ['PYSPARK_PYTHON'] = sys.executable
    os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable
    builder = (SparkSession.builder.master('local[2]').appName('DengueSUX')
        .config('spark.sql.extensions', 'io.delta.sql.DeltaSparkSessionExtension')
        .config('spark.sql.catalog.spark_catalog', 'org.apache.spark.sql.delta.catalog.DeltaCatalog')
        .config('spark.sql.shuffle.partitions', '4')
        .config('spark.driver.memory', '2g')
        .config('spark.sql.session.timeZone', 'Asia/Singapore'))
    spark = configure_spark_with_delta_pip(builder).getOrCreate()
    spark.sparkContext.setLogLevel('ERROR')  # Local classic Spark only.
    return spark

def write_table(df, name):
    if os.environ.get('DATABRICKS_RUNTIME_VERSION') and not TABLE_PREFIX:
        raise ValueError('Set DENGUE_TABLE_PREFIX to a writable catalog.schema on Databricks.')
    writer = df.write.format('delta').mode('overwrite').option('overwriteSchema', 'true')
    if TABLE_PREFIX:
        writer.saveAsTable(f'{TABLE_PREFIX}.{name}')
    else:
        writer.save(str(ROOT / 'data/delta' / name))

def read_table(spark, name):
    return spark.table(f'{TABLE_PREFIX}.{name}') if TABLE_PREFIX else spark.read.format('delta').load(str(ROOT / 'data/delta' / name))
