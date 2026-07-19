# Enterprise Setup

The default MVP runs locally with stubs. Real enterprise integrations are
optional and should be enabled only after the local API and console work.

## Local Setup

```bash
cp .env.example .env
make install
make data
make train
make api
```

In a second terminal:

```bash
make console
```

Open the API docs at `http://localhost:8000/docs` and the console at
`http://localhost:3000`.

## Dataverse

Set these values when `MODE` is not `local`:

- `DATAVERSE_ORG_URL`
- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`

The app registration must also be created as an Application User inside the
Dynamics environment and assigned a role that can upsert the surveillance case
table. The client uses an alternate key, `sd_idempotencykey`, for idempotent
case writes.

## Bedrock

The current MVP uses `LocalLLMClient`. A Bedrock client can be added behind the
same `LLMClient.complete()` contract:

- input: system prompt, user prompt, max tokens, temperature
- output: JSON text plus token counts

Keep local fixtures as the default path so evals and demos do not require cloud
credentials.
