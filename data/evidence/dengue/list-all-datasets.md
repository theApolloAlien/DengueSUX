> For the complete documentation index, see [llms.txt](https://guide.data.gov.sg/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://guide.data.gov.sg/developer-guide/dataset-apis/list-all-datasets.md).

# List all datasets

### Datasets Listing

This API returns a list of all the datasets available on data.gov.sg

## GET /v2/public/api/datasets

> Get datasets

```json
{"openapi":"3.0.3","info":{"title":"beta.data.gov.sg Public API","version":"1.0.11"},"tags":[{"name":"datasets"}],"servers":[{"url":"https://api-production.data.gov.sg"}],"paths":{"/v2/public/api/datasets":{"get":{"summary":"Get datasets","tags":["datasets"],"parameters":[{"in":"query","name":"page","schema":{"type":"integer","minimum":1},"description":"Page number (optional, must be 1 or more)"}],"responses":{"200":{"description":"Successful response","content":{"application/json":{"schema":{"type":"object","properties":{"code":{"type":"integer"},"data":{"type":"object","properties":{"datasets":{"type":"array","items":{"type":"object","properties":{"datasetId":{"type":"string"},"createdAt":{"type":"string"},"name":{"type":"string"},"status":{"type":"string"},"format":{"type":"string"},"lastUpdatedAt":{"type":"string"},"managedByAgencyName":{"type":"string"},"coverageStart":{"type":"string"},"coverageEnd":{"type":"string"}}}},"pages":{"type":"integer"}}},"errorMsg":{"type":"string"}}}}}}}}}}}
```
