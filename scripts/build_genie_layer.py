"""Create or refresh the Genie-facing objects (planning-area lookup, inspection_places view, table and column comments).

Usage: python scripts/build_genie_layer.py --profile denguesux [--prefix workspace.denguesux] [--warehouse ID] [--dry-run]
Runs through a SQL warehouse, so it needs no cluster and costs no job quota. Safe to re-run; the same statements run at the
end of the pipeline's gold stage. Region comes from the dated planning-area boundaries in output/web/current.json.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from denguesux.genie_layer import apply_governance, statements, tag_statements, TABLE_SOURCES  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', default='denguesux')
    ap.add_argument('--prefix', default='workspace.denguesux')
    ap.add_argument('--warehouse')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    current = json.loads((ROOT / 'output/web/current.json').read_text())
    stmts = statements(args.prefix, [(a['code'], a['name'], a['region']) for a in current['areas']])
    if args.dry_run:
        tags = [sql for table in TABLE_SOURCES for sql in tag_statements(args.prefix, table)]
        print('\n;\n'.join(stmts + tags))
        return
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient(profile=args.profile)
    warehouse = args.warehouse or next(x.id for x in w.warehouses.list())
    for i, sql in enumerate(stmts, 1):
        res = w.statement_execution.execute_statement(statement=sql, warehouse_id=warehouse, wait_timeout='50s')
        state = res.status.state.value
        if state != 'SUCCEEDED':
            sys.exit(f'Statement {i}/{len(stmts)} {state}: {res.status.error.message if res.status.error else ""}\n{sql[:200]}')
    print(f'{len(stmts)} statements applied to {args.prefix} via warehouse {warehouse}.')
    def execute(sql):
        response = w.statement_execution.execute_statement(statement=sql, warehouse_id=warehouse, wait_timeout='50s')
        if response.status.state.value != 'SUCCEEDED':
            raise RuntimeError('Optional catalog metadata statement did not succeed')
    print(apply_governance(execute, args.prefix))


if __name__ == '__main__':
    main()
