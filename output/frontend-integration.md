Current real payload is output/web/dashboard.json. Server running http://127.0.0.1:8787, mounts app/web.
Please adapt app.js to actual model fields (now finalized):
model.metrics={mae,accuracy} CANDIDATE ridge metrics; model.baseline_metrics={mae,accuracy}; model.selected_metrics; model.recommended_model='Four-week average', model.selected_baseline=true.
model.predictions[].prediction is candidate ridge, .baseline baseline; .selected_prediction validation-recommended. .risk for predicted national band, .origin_week is origin date. top_features=[{feature,value}] true linear SHAP contributions.
model.thresholds={low,high} training derived. model.training_window string, model.evaluation_window string, model.splits={train,validation,test,refit} counts. model.validation_baseline.mae and model.validation[] candidate tuning metrics.
Explain candidate beats baseline on held-out 2022, but baseline wins 2021 validation and is retained as recommendation; do NOT switch using test set. Model name Weather + trend ridge. Selected conservative baseline must be clear.
No feature_importance yet; please derive average absolute top_features across predictions for chart but label as 'Largest displayed attributions' (top6 truncated), or I can export full mean SHAP in next run. Prefer final full feature_importance I will add via model code.
Global bundled HTML is window.__DENGUE_DATA__; currently app looks for window.DENGUESUX_DATA. Accept both or I can change exporter.
Please ensure source snapshot retrieval date visible, weather date visible, feature update range visible via methodology. Beautiful original design; no need imagegen.

Mean absolute SHAP export added in model.py now; next gold execution will populate feature_importance correctly. Exporter now uses window.DENGUESUX_DATA to match app.
