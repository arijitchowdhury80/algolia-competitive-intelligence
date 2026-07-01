# CI-OS Environment And Secrets Spec

Date: 2026-07-01
Status: Planning baseline

## Security Position

This file is the single source of truth for credential names, purposes, storage locations, and rotation rules. It must not contain real secret values.

Real secrets belong in local `.env` files, VPS secret stores, or platform-managed environment variables. Do not put live API keys, tokens, passwords, SSH keys, or Telegram credentials into Markdown.

## Local Files

Recommended local files:

- `.env.example`: committed template with variable names and comments.
- `.env.local`: local developer values, never committed.
- `.env.vps.example`: template for Chowmes/Argus deployment.
- `.env.vps.local`: deployment values, never committed.

## Required Secret Groups

### Hermes Runtime

| Variable | Purpose | Storage | Required for |
|----------|---------|---------|--------------|
| `HERMES_HOME` | Hermes data home | config, not secret | runtime |
| `ARGUS_PROFILE_HOME` | Argus profile path | config, not secret | runtime |
| `HERMES_ADMIN_TOKEN` | Admin access if enabled | VPS env | admin |

### Telegram

| Variable | Purpose | Storage | Required for |
|----------|---------|---------|--------------|
| `ARGUS_TELEGRAM_BOT_TOKEN` | Argus bot token | VPS env | Telegram delivery |
| `ARGUS_TELEGRAM_CHAT_ID` | delivery target | VPS env | Telegram delivery |
| `TELEGRAM_ALLOWED_USER_IDS` | allowlist | VPS env | Telegram gateway |

### WhatsApp

| Variable | Purpose | Storage | Required for |
|----------|---------|---------|--------------|
| `WHATSAPP_ACCESS_TOKEN` | WhatsApp Business Platform API token | VPS env or secret store | WhatsApp channel |
| `WHATSAPP_PHONE_NUMBER_ID` | sending phone number id | config/secret store | WhatsApp channel |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | WhatsApp business account id | config/secret store | WhatsApp channel |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | webhook verification | VPS env or secret store | WhatsApp webhook |
| `WHATSAPP_APP_SECRET` | webhook signature verification | VPS env or secret store | WhatsApp webhook |

### Apple Messages For Business

| Variable | Purpose | Storage | Required for |
|----------|---------|---------|--------------|
| `APPLE_MESSAGES_BUSINESS_ID` | Apple Messages for Business account id | secret store | Apple channel |
| `APPLE_MESSAGES_MSP_ID` | Messaging Service Provider id if used | secret store | Apple channel |
| `APPLE_MESSAGES_API_SECRET` | API signing or provider secret | secret store | Apple channel |
| `APPLE_MESSAGES_WEBHOOK_SECRET` | webhook verification | secret store | Apple channel |

### Model Providers

| Variable | Purpose | Storage | Required for |
|----------|---------|---------|--------------|
| `GEMINI_API_KEY` | Gemini low, standard, high tier models | local and VPS env | synthesis |
| `GOOGLE_IMAGE_API_KEY` | image generation if separate from Gemini | local and VPS env | visual storytelling |
| `OPENAI_API_KEY` | OpenAI provider if selected | local and VPS env | model provider switching |
| `ANTHROPIC_API_KEY` | Anthropic provider if selected | local and VPS env | model provider switching |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI provider if selected | local and VPS env | enterprise deployment |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint | config/secret store | enterprise deployment |
| `XAI_API_KEY` | Grok and X search if enabled | local and VPS env | X/Twitter monitoring |

### Identity And SSO

| Variable | Purpose | Storage | Required for |
|----------|---------|---------|--------------|
| `OIDC_ISSUER_URL` | OIDC identity provider issuer | config/secret store | enterprise SSO |
| `OIDC_CLIENT_ID` | OIDC app client id | config/secret store | enterprise SSO |
| `OIDC_CLIENT_SECRET` | OIDC app secret | secret store | enterprise SSO |
| `SAML_ENTITY_ID` | SAML service provider entity id | config | SAML SSO |
| `SAML_CERT` | SAML signing/encryption certificate | secret store | SAML SSO |
| `SCIM_BEARER_TOKEN` | SCIM provisioning token | secret store | SCIM provisioning |

### Web And Search

| Variable | Purpose | Storage | Required for |
|----------|---------|---------|--------------|
| `PARALLEL_API_KEY` | web search/fetch backend | local and VPS env | source discovery |
| `YOUTUBE_API_KEY` | YouTube public channel metadata | local and VPS env | video monitoring |

### Storage And Dashboard

| Variable | Purpose | Storage | Required for |
|----------|---------|---------|--------------|
| `CIOS_DATABASE_URL` | primary database path or URL | local and VPS env | ledger |
| `CIOS_DASHBOARD_PUBLIC_URL` | public dashboard URL | config | dashboard |
| `CIOS_DASHBOARD_EXPORT_PATH` | semantic JSON export path | config | dashboard |
| `DASHBOARD_GIT_PUBLISH` | optional publish toggle | config | dashboard publish |

### Compliance-Gated Social Sources

| Variable | Purpose | Storage | Required for |
|----------|---------|---------|--------------|
| `LINKEDIN_ACCESS_TOKEN` | LinkedIn API if approved | secret store | LinkedIn monitoring |
| `X_BEARER_TOKEN` | X API if approved | secret store | X monitoring |

If API access is not approved, the system must mark the source family as public/manual/limited rather than failing the whole pipeline.

## Model Routing Configuration

Recommended non-secret config:

```env
CIOS_MODEL_DEFAULT=gemini-flash-lite
CIOS_MODEL_STANDARD=gemini-flash
CIOS_MODEL_HIGH=gemini-pro-high
CIOS_MODEL_IMAGE=nanobanana
CIOS_MODEL_ESCALATION_LOG=1
CIOS_MODEL_PROVIDER_DEFAULT=google
CIOS_MODEL_PROVIDER_ALLOWED=google,openai,anthropic,azure-openai
```

These are stable internal aliases. Actual provider model ids must be verified against current provider docs during implementation and stored in one model-routing config file, not scattered across skills.

Example mapping candidates at planning time:

```env
CIOS_PROVIDER_MODEL_DEFAULT=gemini-3.1-flash-lite
CIOS_PROVIDER_MODEL_STANDARD=gemini-3-flash
CIOS_PROVIDER_MODEL_HIGH=gemini-3.1-pro
CIOS_PROVIDER_MODEL_IMAGE_FAST=gemini-3.1-flash-image
CIOS_PROVIDER_MODEL_IMAGE_PREMIUM=gemini-3-pro-image
```

## Secret Handling Rules

- Never commit `.env.local`.
- Never mirror live secrets into Obsidian.
- Never print secret values in logs.
- Redact recipient ids in user-facing output.
- Rotate compromised credentials immediately.
- Store only key presence, not key value, in health checks.

## Health Check Expectations

The health check should report:

- required variable present or missing
- optional variable present or not configured
- source family affected by missing variable
- degraded capability if missing
- no raw value

Example:

```text
GEMINI_API_KEY: present
XAI_API_KEY: missing, X/Twitter monitoring disabled
YOUTUBE_API_KEY: missing, YouTube monitoring degraded
ARGUS_TELEGRAM_BOT_TOKEN: present
```
