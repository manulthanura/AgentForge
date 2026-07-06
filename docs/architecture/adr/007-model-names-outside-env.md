# ADR-007: Model Names in `model_config.json`, Never in `.env`

**Status**: accepted

## Context

Env files carry credentials and deployment switches; model choices are
operational tuning that changes more often and shouldn't require touching
secrets or redeploying.

## Decision

Per-provider default models live in
`src/shared_kernel/config/model_config.json`, loaded through
`ModelConfigStore`. The admin API (`PATCH /admin/model-config`, guarded by
`SECRET_KEY`) updates the file at runtime. `LLM_MODEL` remains available as
an explicit env override for experiments, but `.env.example` documents the
rule: **credentials only, no model names**.

## Trade-offs

One more config surface. In exchange, retuning a model is an authorized API
call instead of a deploy, and secrets management stays strictly about
secrets.
