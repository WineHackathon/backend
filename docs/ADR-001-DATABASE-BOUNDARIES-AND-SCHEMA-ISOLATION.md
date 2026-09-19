# ADR-001: Database Architecture, Schema Partitioning and Domain Isolation

## Status
**ACCEPTED** (Production Architecture Standard)

## Date
2026-09-19

## Context & Problem Statement
The «Своё Вино» platform is composed of 6 independent backend services:
1. `auth-service` (Identity Provider, JWT, OAuth 2.0)
2. `catalog-service` (Wine Catalog & Food Pairings Master)
3. `user-service` (Personal Wine Cellar, Wishlist, Scans)
4. `recognition-service` (Wine Label Image Scanner)
5. `sommelier-service` (AI Sommelier with RAG Pipeline)
6. `ml-service` (Vision Embeddings & Vector Search Worker)

Currently, the persistence layer utilizes a shared PostgreSQL 16 database (`wine_db`). While convenient for local development and rapid prototyping, sharing the default `public` schema across multiple microservices poses architectural risks:
- **Coupling & Leaky Boundaries**: Direct cross-domain queries or accidental foreign keys bypass service APIs.
- **Blast Radius**: Migration errors or table locking in one domain (e.g. `scans`) could impact unrelated domains (e.g. `auth`).
- **Security & Multi-Tenancy**: A compromised service credential could theoretically read or mutate tables belonging to another domain.

## Decision
We adopt a phased **Schema-per-Service Isolation Model** transitioning to **Database-per-Service** in production:

### 1. Logical Isolation via PostgreSQL Schemas
The database cluster is partitioned into isolated schemas corresponding to bounded contexts:
- **`catalog` schema**:
  - `catalog.wines`
  - `catalog.wine_food_pairings`
  - Owned strictly by `catalog-service` (read-only views exposed to `sommelier-service`).
- **`auth` schema**:
  - `auth.users`
  - Owned strictly by `auth-service`.
- **`user_cellar` schema**:
  - `user_cellar.cellar_items`
  - `user_cellar.scan_history`
  - Owned strictly by `user-service`.

### 2. Domain Ownership Rules
- **No Cross-Schema Foreign Keys**: Relationships across service boundaries are modeled as soft references (UUIDs or business slugs), never database-level foreign key constraints.
- **No Direct Cross-Service SQL Queries**: Microservices communicate exclusively via DTO contracts (REST APIs or Redis RPC), never by issuing SQL queries against tables outside their domain.
- **Dedicated Least-Privilege DB Roles**:
  - `catalog_service_role`: Access restricted exclusively to `SCHEMA catalog`.
  - `auth_service_role`: Access restricted exclusively to `SCHEMA auth`.
  - `user_service_role`: Access restricted exclusively to `SCHEMA user_cellar`.

### 3. Production Roadmap: Database-per-Service
For multi-region / high-scale production:
1. **Phase 1 (Current)**: Schema-per-service on managed PostgreSQL (Aurora/RDS) with role-based access control (RBAC).
2. **Phase 2 (Scale)**: Physical separation into independent database clusters (`catalog-db`, `auth-db`, `user-db`) using the existing schema boundaries without application code refactoring.

## Consequences

### Positive
- **Clear Domain Boundaries**: Prevents monolithic database anti-patterns and circular dependencies.
- **Independent Migrations**: Alembic migrations can run per-schema without table lock contention.
- **Strict Security**: Compromise of `user-service` credentials does not grant access to password hashes in `auth.users`.
- **Zero-Downtime Migration**: The provided `split_schemas.sql` creates non-blocking views over existing tables, preserving backward compatibility with zero data loss.

### Negative / Mitigations
- *Management Overhead*: Multiple schemas and database roles require slightly more configuration in infrastructure code (`docker-compose.yml`, Kubernetes Helm charts).
  *Mitigation*: Centralized via `database/scripts/split_schemas.sql` and automated Docker entrypoints.
