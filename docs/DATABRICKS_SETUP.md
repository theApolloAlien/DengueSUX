# DengueSUX on Databricks: first-time setup checklist

Plain-language steps for getting DengueSUX running in a Databricks Free Edition workspace.
Do them in order. Tick each box only when the "You should see" line is true.

**Honest caveat:** the notebooks and job have never been run on Databricks. Expect to hit
a few errors. Phases 4 and 5 are where they will most likely appear. When one does, copy
the full error text and bring it back; that is normal progress, not failure.
Button names in Databricks change slightly between releases, so match by meaning.

**The golden rule:** edit code on your laptop, push to GitHub, then press Pull in
Databricks. Do not edit code inside Databricks.

---

## Phase 0: Laptop prep (10 min)

- [ ] `git status` is clean, and your latest work is pushed to GitHub
      (`git push origin main`). Note: `deck/*.pdf` and `deck/*.pptx` currently show as modified.
      Commit or discard them first.
- [ ] Make a small upload folder on your laptop (nothing here is committed to git).
      The pipeline only needs these data files (about 60 MB), not the 890 MB `data/raw` folder:

```bash
mkdir -p ~/Desktop/denguesux_upload && cd /Users/apollo/1m/dengueRadar
rsync -a --relative \
  data/raw/boundaries data/raw/dengue data/raw/inspection data/raw/weather \
  data/phase2_inputs/weather_station_days.csv.gz data/phase2_inputs/weather_manifest.json \
  data/cache data/snapshots \
  ~/Desktop/denguesux_upload/
du -sh ~/Desktop/denguesux_upload
```

  **You should see:** a total of roughly 60 MB. If it is hundreds of MB, something extra was copied.

## Phase 1: Workspace (10 min)

- [ ] Sign in to your Databricks Free Edition workspace
      (Free Edition signup page; email one-time code or Google).
- [ ] Decide this is your **one final demo workspace**. Don't build in a second one.
- [ ] Open **Catalog** (left sidebar). Under your catalog (often `workspace`), create a
      schema called `denguesux`.
- [ ] Inside that schema, create a **Volume** called `files` (managed volume).

  **You should see:** `workspace.denguesux.files` in the Catalog tree.
  Your two key settings are now:
  - `DENGUE_TABLE_PREFIX` = `workspace.denguesux` (use your real catalog name if it is not `workspace`)
  - `DENGUE_ROOT` = `/Volumes/workspace/denguesux/files/denguesux`

## Phase 2: Put the data in the cloud (15 min)

- [ ] In the Catalog, open the `files` Volume. Create a folder `denguesux`.
- [ ] Upload the contents of `~/Desktop/denguesux_upload/` into it, keeping the folders
      (`data/raw/...`, `data/phase2_inputs/...`, `data/cache`, `data/snapshots`).
      Folder drag-and-drop works in the Volume browser. If it only takes files, upload
      folder by folder.
- [ ] Check the path of one file, for example
      `/Volumes/workspace/denguesux/files/denguesux/data/raw/dengue/national_bulletin.csv.gz`.

  **You should see:** that exact file listed. If it is one level off, the pipeline will fail
  with "file not found", which is a path problem and not a code problem.

## Phase 3: Connect the code (10 min)

- [ ] Open **Workspace**, click Create, then **Git folder**.
- [ ] Paste `https://github.com/theApolloAlien/DengueSUX.git` and create it.
      (It is a public repo, so no login is needed.)
- [ ] Open the new folder and check that you can see `notebooks/`, `denguesux/` and `app.py`.

  **You should see:** all three. **If there is no Git folder option on Free Edition:**
  use the fallback below.

  *Fallback (manual upload):* Workspace, Create, folder `DengueSUX`. Use Import to upload the
  `notebooks/`, `denguesux/` and `scripts/` folders. Each later change then means re-uploading
  by hand, so push for the Git route first.

## Phase 4: Run the pipeline (30 min)

Use the runner notebook `notebooks/run_stage.py` (in your Git folder). It installs compatible
libraries, sets the paths and MLflow, then runs one stage. Run the stages in order, with
**Serverless** compute attached. Set the `stage` widget at the top to each value in turn:

- [ ] `bronze`. You should see: 5 `bronze_*` tables in the Catalog.
- [ ] `silver`. You should see: `silver_national_weekly`, `silver_weather_station_days`,
      `silver_area_weekly` and the inspection silver tables.
- [ ] `gold`: the slow one (model training, MLflow, inspection plans, notices).
      You should see: `gold_*` tables, and an MLflow experiment named
      `DengueSUX-national-forecast` under your user.

Things learned the hard way on Free Edition (already handled in `run_stage.py`):
- Installing `shap` can break scipy against Databricks' numpy, so numpy and scipy are pinned up.
- Serverless blocks MLflow reading `spark.mlflow.modelRegistryUri`, so the registry URI is set explicitly.
- Databricks ships an older MLflow than the repo needs (`name=` in `log_model`), so 3.5.0 is installed.
- An MLflow experiment cannot share its path with a workspace folder. The Git folder is
  `DengueSUX`, so the experiment is `DengueSUX-national-forecast`.

## Phase 5: Genie, app and job

- [x] **Genie:** create a Genie space over the `gold_*` tables. The space definition (tables,
      plain-language instructions, tested example SQL) is saved in `databricks_app/genie_space.json`.
- [x] **App (Databricks Apps):** build the deploy folder, upload it, create the app with the Genie
      space (`CAN_RUN`) and the SQL warehouse (`CAN_USE`) attached, then deploy:

```bash
python scripts/build_databricks_app.py /tmp/app_build --web-from <copy of the pipeline's output/web>
databricks workspace import-dir /tmp/app_build /Workspace/Users/<you>/denguesux_app --overwrite
databricks apps create --json @app_create.json      # name, resources: genie-space + sql-warehouse
databricks apps deploy denguesux --source-code-path /Workspace/Users/<you>/denguesux_app
```

  The app's service principal also needs `USE CATALOG`, `USE SCHEMA` and `SELECT` on
  `workspace.denguesux`. The "Ask the data" tab then answers live through Genie, and falls back
  to saved-data answers if Genie is unavailable. Free Edition stops an app after 24 hours;
  restart it before a demo with `databricks apps start denguesux`.
- [x] **Jobs (serverless):** `databricks.yml` defines two jobs with no cluster, so they run on
      serverless compute: `pipeline` (bronze, silver, gold) and `daily_inspection` (live NEA
      snapshot, growth, inspection plans, resident notices; schedule is PAUSED to save quota).

```bash
databricks bundle deploy -p <profile>
databricks bundle run pipeline -p <profile>
databricks bundle run daily_inspection -p <profile>
```

  Both were run end to end on Databricks Free Edition. The daily job's live fetch from data.gov.sg
  works within Free Edition's outbound-internet allowlist.

## Day-to-day loop after setup

1. Edit on your laptop and test locally.
2. `git add -A && git commit -m "..." && git push`.
3. In Databricks, open the Git folder and click **Pull**.
4. Re-run the notebook, or redeploy the app.

## Quota rules to keep in mind

- Going over quota switches compute off for the rest of the day. Your data stays safe.
- Don't run `scripts/prepare_weather.py` (the 125M-row scan) on Databricks. The compact
  weather file is already uploaded.
- Run each notebook once, read the result, then move on. Avoid re-running everything in a loop.
- Free Edition internet is limited to trusted domains, so live calls to data.gov.sg or
  OneMap may be blocked. Test one small request early. Your saved data works without it.
