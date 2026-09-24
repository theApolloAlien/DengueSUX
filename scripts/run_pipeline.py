"""Run the actual local Spark + Delta medallion pipeline."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from denguesux.runtime import get_spark
from denguesux import pipeline

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['all','bronze','silver','gold'],default='all');a=p.parse_args()
    spark=get_spark()
    try:
        for name in (['bronze','silver','gold'] if a.stage=='all' else [a.stage]): getattr(pipeline,name)(spark)
    finally: spark.stop()
