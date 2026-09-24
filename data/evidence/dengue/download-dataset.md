> For the complete documentation index, see [llms.txt](https://guide.data.gov.sg/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://guide.data.gov.sg/developer-guide/dataset-apis/download-dataset.md).

# Download dataset

## Guide to downloading datasets

To download an entire dataset via API, you will need to first call the `initiate download` API, followed by the `poll download` API.

You may add column and rows filters to get a subset of the dataset, although this is optional.

For datasets that do not have the CSV extension (ie GeoJSON, KML, PDF etc.), you may skip this endpoint and proceed to the Poll Download API below.

{% hint style="info" %}
To find the dataset\_id, refer to the URL of dataset.\
\
For this dataset:\
<https://data.gov.sg/collections/522/datasets/d_11e68bba3b3c76733475a72d09759eeb/view> \
or \
<https://data.gov.sg/datasets/d_11e68bba3b3c76733475a72d09759eeb/view>\ <br>

The datasetId is:\
`d_11e68bba3b3c76733475a72d09759eeb`

For staging, note that the dataset\_id might differ between staging and production:

* Domain: <https://api-open-staging.data.gov.sg/>
* Example: <https://api-open-staging.data.gov.sg/v1/public/api/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/initiate-download>
  {% endhint %}

## GET /v1/public/api/datasets/{datasetId}/initiate-download

> Initiate download for a dataset

```json
{"openapi":"3.0.0","info":{"title":"DGS Public Download API","version":"1.0.0"},"servers":[{"url":"https://api-open.data.gov.sg"}],"paths":{"/v1/public/api/datasets/{datasetId}/initiate-download":{"get":{"summary":"Initiate download for a dataset","parameters":[{"name":"datasetId","in":"path","required":true,"schema":{"type":"string"},"description":"ID of the dataset"}],"requestBody":{"description":"Optional request body for filtering dataset","content":{"application/json":{"schema":{"type":"object","properties":{"columnNames":{"type":"array","items":{"type":"string"},"description":"List of selected columns in filtered dataset."},"filters":{"type":"array","description":"Filters defines how users want to filter their dataset.\n\nFilters is an array of objects which have `columnName`, `type` and `value` attributes.\n- `columnName` refers to the column where the filter is to be applied.\n- `type` can be `EQ`, `LIKE`, or `ILIKE`:\n  - **EQ**: Direct comparison for filter and is case sensitive.\n  - **LIKE**: Similar to EQ but includes partial matching. Any words containing the string in the `value` attribute will be matched.\n  - **ILIKE**: Case-insensitive version of LIKE.\n"}}}}}},"responses":{"201":{"description":"Successful response","content":{"application/json":{"schema":{"type":"object","properties":{"code":{"type":"integer","description":"Response code"},"data":{"type":"object","properties":{"message":{"type":"string","description":"Success message"}}},"errorMsg":{"type":"string","description":"Error message (if any)"}}}}}},"400":{"description":"Request Failure <br/>\n<li>Contains invalid column name.</li> <li>Invalid filters.</li> <li>Event object validation failed.</li>","content":{"application/json":{"schema":{"type":"object","properties":{"code":{"type":"integer","description":"Response code"},"name":{"type":"string","description":"Error type"},"errorMsg":{"type":"string","description":"Error Message"}}}}}},"429":{"description":"Rate limit exceeded","content":{"application/json":{"schema":{"type":"object","properties":{"code":{"type":"number"},"name":{"type":"string"},"data":{"type":"object"},"errorMsg":{"type":"string"}}}}}}}}}}}
```

After initiating the download of a dataset, this endpoint below returns a link to access the dataset

## GET /v1/public/api/datasets/{datasetId}/poll-download

> Poll download for a dataset after download has been initiated

```json
{"openapi":"3.0.0","info":{"title":"DGS Public Download API","version":"1.0.0"},"servers":[{"url":"https://api-open.data.gov.sg"}],"paths":{"/v1/public/api/datasets/{datasetId}/poll-download":{"get":{"summary":"Poll download for a dataset after download has been initiated","parameters":[{"name":"datasetId","in":"path","required":true,"schema":{"type":"string"},"description":"ID of the dataset"}],"requestBody":{"description":"Optional request body for filtering dataset","content":{"application/json":{"schema":{"type":"object","properties":{"columnNames":{"type":"array","items":{"type":"string"},"description":"List of selected columns in filtered dataset."},"filters":{"type":"array","description":"Filters defines how users want to filter their dataset.\n\nFilters is an array of objects which have `columnName`, `type` and `value` attributes.\n- `columnName` refers to the column where the filter is to be applied.\n- `type` can be `EQ`, `LIKE`, or `ILIKE`:\n  - **EQ**: Direct comparison for filter and is case sensitive.\n  - **LIKE**: Similar to EQ but includes partial matching. Any words containing the string in the `value` attribute will be matched.\n  - **ILIKE**: Case-insensitive version of LIKE.\n"}}}}}},"responses":{"201":{"description":"Successful response","content":{"application/json":{"schema":{"type":"object","properties":{"code":{"type":"integer","description":"Response code"},"data":{"type":"object","properties":{"status":{"type":"string","description":"Status of download"},"url":{"type":"string","description":"Link to access downloaded dataset"}}},"errorMsg":{"type":"string","description":"Error message (if any)"}}}}}},"400":{"description":"Request Failure <br/>\n<li>Contains invalid column name.</li> <li>Invalid filters.</li> <li>Event object validation failed.</li>","content":{"application/json":{"schema":{"type":"object","properties":{"code":{"type":"integer","description":"Response code"},"name":{"type":"string","description":"Error type"},"errorMsg":{"type":"string","description":"Error Message"}}}}}},"429":{"description":"Rate limit exceeded","content":{"application/json":{"schema":{"type":"object","properties":{"code":{"type":"number"},"name":{"type":"string"},"data":{"type":"object"},"errorMsg":{"type":"string"}}}}}}}}}}}
```

{% hint style="info" %}
As data.gov.sg is a public shared service, we will apply quotas to ensure that they are fairly used by all users. If you exceed the quota of 5 requests per minute, you’ll likely receive a 429 Error.\
\
For higher rate limits - [create an API key](/developer-guide/api-overview/how-to-request-an-api-key.md)
{% endhint %}
