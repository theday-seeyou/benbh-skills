# BBH Image OpenAPI Reference

## Transport

- Default base URL: `https://bbh-ai-server.benbh.cn`
- Authentication header: `X-API-Key: <key>`
- JSON responses normally use `{ "code": 200, "data": ..., "message": ... }`.
- Treat non-2xx HTTP responses and JSON responses whose `code` is present but not `200` as errors.

## Endpoints

### List models

`GET /api/v5/models`

Optional query parameter: `task_type`.

The response describes model IDs, supported task types, tiers, point costs, parameter schemas, and reference-image limits. Always prefer this live response over hard-coded assumptions.

### Get account points

`GET /api/v5/user/points`

Useful response fields under `data`:

- `total_points`: current total usable points
- `points`: remaining purchased points
- `gift_points`: remaining daily gift points

### Upload a temporary file

`POST /api/v3/temp/file/upload`

Send `multipart/form-data` with a single `file` part. The returned `data.url` can be passed as a URL reference image.

### Submit an image task

`POST /api/v5/image/submit`

JSON body:

```json
{
  "model_id": "101",
  "prompt": "a cute cat",
  "tier_id": "optional-tier",
  "aspect_ratio": "1:1",
  "image_size": "1K",
  "quality": "optional-quality",
  "images": [
    { "type": "url", "data": "https://example.com/reference.png" },
    { "type": "base64", "data": "data:image/png;base64,..." }
  ],
  "user_params": {}
}
```

Only `model_id` and `prompt` are universally required. Validate other fields against the selected model. A successful response returns `data.task_id`.

### Get task status

`GET /api/v5/task/status/{task_id}`

Successful terminal statuses: `completed`, `succeeded`, `success`.

Failed terminal statuses: `failed`, `error`, `cancelled`, `canceled`, `timeout`.

Common result shapes under `data`:

```json
{
  "status": "completed",
  "progress": 100,
  "results": [
    { "output_type": "image", "url": "https://..." }
  ]
}
```

Some responses use `data.result_url` instead of `data.results`.

## CLI output and exit codes

The CLI writes machine-readable JSON to stdout and progress messages to stderr.

- `0`: success
- `2`: invalid local input or missing configuration
- `3`: network, HTTP, or API response error
- `4`: task failed or polling timed out

Use `--compact` for one-line JSON. Do not parse stderr as structured output.
