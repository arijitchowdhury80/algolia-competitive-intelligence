# CI-OS Channels, Identity, ACL, And Model Provider Architecture

Date: 2026-07-01
Status: Planning baseline

## Purpose

CI-OS must be designed from the beginning as a multi-user, multi-channel, enterprise-adoptable product.

Users should be able to interact with Argus through:

- Web app
- Telegram
- WhatsApp
- Apple Messages for Business, commonly described by users as iMessage access

The same user, permission model, audit trail, and Argus intelligence state must apply across all channels.

## Core Principle

Channels are interfaces, not identities.

A user may have:

- one Google or enterprise SSO identity
- one Telegram identity
- one WhatsApp identity
- one Apple Messages for Business identity
- one or more role assignments

Argus must resolve channel identities back to a canonical user before giving access to reports, evidence, actions, or admin functions.

## Channel Reality Check

### Telegram

Telegram is the fastest first production channel because it already exists in the Chowmes/Argus loop and supports bot-style interaction.

V1 use:

- approved user allowlist
- daily and weekly delivery
- interactive Q&A with Argus
- admin-gated commands

### WhatsApp

WhatsApp should be planned through the official WhatsApp Business Platform / Cloud API path.

Architecture implications:

- webhook receiver
- message status webhooks
- WhatsApp business account and phone number id
- template rules for outbound initiated messages
- opt-in and compliance handling
- channel-specific delivery state

### Apple Messages / iMessage

Plan this as Apple Messages for Business, not an unofficial consumer iMessage bot.

Architecture implications:

- Apple Business Register / Messages for Business setup
- possible Messaging Service Provider relationship
- webhook-style integration
- approval and brand identity steps
- channel capability limits

Do not build an unofficial Mac relay or private iMessage automation as the enterprise architecture. That would be brittle and unacceptable for Algolia IT.

## Channel Adapter Pattern

Each channel implements the same interface:

```text
ChannelAdapter
  receive(raw_event) -> NormalizedInboundMessage
  send(response_envelope) -> DeliveryResult
  verify_signature(raw_event) -> VerificationResult
  map_identity(raw_event) -> ChannelIdentity
  supports(capability) -> boolean
```

Initial adapters:

- `telegram_adapter`
- `whatsapp_adapter`
- `apple_messages_business_adapter`
- `web_app_adapter`

Normalized inbound message:

- `channel`
- `channel_user_id`
- `channel_thread_id`
- `message_id`
- `text`
- `attachments`
- `received_at`
- `signature_verified`
- `metadata`

Response envelope:

- `recipient_user_id`
- `channel`
- `thread_id`
- `text`
- `cards`
- `attachments`
- `evidence_links`
- `classification`
- `delivery_policy`

## Identity Resolution

Flow:

1. Receive channel event.
2. Verify webhook signature or channel authenticity.
3. Resolve `channel_identity` to canonical `user`.
4. If unlinked, create access request or account-linking challenge.
5. Load role and permissions.
6. Apply ACL before any data access or tool execution.
7. Route allowed request to Argus.
8. Record audit log.
9. Deliver response through originating or configured channel.

## Access Control Model

Use role-based access control first, with attribute-based checks where needed.

Roles:

- `owner`
- `operator_admin`
- `ci_operator`
- `executive_viewer`
- `gtm_viewer`
- `pmm_user`
- `marketer`
- `product_user`
- `sales_enablement_user`
- `guest_viewer`

Permission families:

- view daily reports
- view weekly reports
- view evidence
- view source health
- view content recommendations
- create or edit action items
- manage competitors
- manage sources
- manage users
- manage integrations
- manage model routing
- trigger runs
- approve skill changes
- view operational logs

Rules:

- Default deny.
- No channel command bypasses ACL.
- Admin commands require elevated role and audit record.
- Evidence visibility can be stricter than report visibility.
- Operational logs and secrets status are operator-only.
- Every Argus response should be scoped to the user's permissions.

## Multi-Tenant Readiness

Even if v1 has one tenant, design the schema with `tenant_id`.

This enables:

- Algolia internal deployment
- future customer deployments
- separate source ledgers
- separate model provider configs
- separate user directories
- clean data isolation

Minimum tenant concepts:

- tenant
- organization
- identity provider config
- enabled channels
- allowed domains
- model provider policy
- data retention policy

## SSO And Enterprise IT Readiness

V1:

- Google OAuth / OIDC for fast internal login.
- Allowlist by account and domain.

Enterprise-ready path:

- OIDC for modern SSO.
- SAML 2.0 for enterprise customers that require it.
- SCIM for user and group provisioning.
- Just-in-time provisioning from trusted identity provider claims.
- Group-to-role mapping.
- Domain verification.
- Session management and logout.

Algolia IT should be able to host CI-OS and connect it to their identity provider without changing core business logic.

## Data Model Additions

Add or plan for:

- `tenants`
- `users`
- `user_identities`
- `roles`
- `permissions`
- `user_role_assignments`
- `groups`
- `group_role_mappings`
- `identity_provider_configs`
- `channel_accounts`
- `channel_identities`
- `channel_threads`
- `channel_messages`
- `delivery_attempts`
- `access_requests`
- `audit_events`
- `tenant_model_provider_configs`
- `model_provider_runs`

## Modular Architecture

CI-OS should be modular in five places:

1. Channel adapters: Telegram, WhatsApp, Apple Messages for Business, web app.
2. Source connectors: websites, RSS, LinkedIn, YouTube, X, news, docs, changelogs.
3. Skill modules: source hunting, collection, synthesis, content, quality, delivery.
4. Model providers: Gemini, OpenAI, Anthropic, Azure OpenAI, local or hosted models.
5. Dashboard modules: command center, sources, content, actions, reports, settings.

Module contracts should be explicit and tested. New modules should plug in through interfaces, not copy-pasted special cases.

## Model-Agnostic Design

Argus must not be hardwired to Gemini.

Use:

- stable internal model aliases
- provider adapters
- capability registry
- model router
- eval suite per provider
- tenant-level model policy

Core interfaces:

```text
ModelProvider
  generate(request) -> ModelResponse
  stream(request) -> ModelStream
  supports(capability) -> boolean
  estimate_cost(request) -> CostEstimate
  health_check() -> ProviderHealth

ModelRouter
  select_model(task_profile, tenant_policy, budget, latency_target) -> ModelSelection
  record_run(selection, result, cost, quality) -> ModelRunRecord
```

Capabilities:

- text generation
- structured JSON
- long context
- tool calling
- web/search grounding
- vision input
- image generation
- low-latency chat
- high-reasoning synthesis

Provider switching rule:

- Switching from Gemini to OpenAI should require config and credentials, not application rewrites.
- Prompts and skills should declare task capability needs, not provider-specific model names.
- Provider-specific quirks live inside adapters.
- Evals must run before a provider becomes production default.

## Conversation And Agent Context

Every Argus interaction must carry:

- tenant id
- canonical user id
- channel
- role claims
- permission set
- conversation id
- requested task
- allowed data scopes
- model policy

Agent and skill execution must never infer permissions from a friendly Telegram or WhatsApp sender name. Identity and ACL must be resolved by the platform first.

## Audit And Compliance

Record:

- login events
- channel identity link/unlink
- report access
- evidence access
- admin changes
- model provider changes
- delivery attempts
- failed ACL checks
- source connector changes
- skill updates

User-facing logs should be polished. Operator audit events should be structured.

## Additional Things Not To Miss

These should be planned before implementation, even if some are deferred:

- User onboarding: invite flow, account linking, role assignment, and first-channel verification.
- User offboarding: SSO deprovisioning, channel unlinking, session revocation, and delivery suppression.
- Group sync: map IdP groups to CI-OS roles.
- Opt-in and consent: especially for WhatsApp outbound messages and any executive-facing alerts.
- Channel rate limits: each adapter should expose rate-limit and retry behavior.
- Data retention: report history, raw evidence, conversation transcripts, audit logs, and deleted users.
- Legal hold: preserve audit and report records when required.
- Customer deployment mode: single-tenant Algolia internal deployment should not require code forks.
- Cost governance: provider budgets, model tier budgets, and per-tenant usage reporting.
- Prompt and response audit: retain enough metadata to debug quality without leaking secrets.
- Break-glass admin: emergency operator access with strict audit trail.
- Regional hosting: leave room for EU or customer-specific hosting requirements.
- Connector marketplace: future modules should register capabilities, required secrets, scopes, and evals.

## Source Notes

- WhatsApp planning should follow the official Meta WhatsApp Business Platform / Cloud API webhook and messaging model.
- Apple messaging planning should follow Apple Messages for Business, not unofficial consumer iMessage automation.
- Enterprise SSO should support OIDC first, with SAML and SCIM for IT-managed deployments.

## Build Implication

This architecture must be included before implementation starts. Retrofitting identity, channels, ACL, and provider abstraction later will create exactly the kind of debt CI-OS is being designed to avoid.
