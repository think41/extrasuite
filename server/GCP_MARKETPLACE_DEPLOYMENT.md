# ExtraSuite Server: Google Cloud Marketplace Deployment Report

## Executive Summary

This report explores deploying the ExtraSuite server to Google Cloud Marketplace to enable seamless enterprise procurement and deployment. Given ExtraSuite's architecture — a FastAPI server running on Cloud Run with Firestore, IAM, and Google Workspace APIs — the **SaaS listing** model is the strongest fit. A secondary option, **Kubernetes app listing**, is also analyzed for customers who want to run ExtraSuite in their own GKE clusters.

---

## 1. Current Architecture Assessment

### What We Have Today

| Component | Technology | Cloud Dependency |
|-----------|-----------|-----------------|
| Runtime | FastAPI + Uvicorn on Cloud Run | GCP-native |
| Database | Firestore (async) | GCP-native |
| Auth | Google OAuth2 + IAM service accounts | GCP-native |
| Container | Multi-stage Docker, pushed to Artifact Registry | GCP-native |
| CI/CD | GitHub Actions → `asia-southeast1-docker.pkg.dev` | GCP-native |
| Logging | Structured JSON for Cloud Logging | GCP-native |

### Key Observations

- **Deeply GCP-native**: Firestore, IAM service account creation, domain-wide delegation, and Cloud Logging are all hard GCP dependencies. This makes a SaaS listing natural.
- **Already containerized**: The Dockerfile is production-ready with health checks, non-root user, and multi-stage builds.
- **Environment-driven config**: All settings flow through environment variables (Pydantic Settings), making deployment parameterization straightforward.
- **Per-tenant isolation**: Each customer already gets isolated 1:1 service accounts — a strong enterprise selling point.

---

## 2. Marketplace Listing Options

### Option A: SaaS Listing (Recommended)

In this model, Think41 hosts and operates ExtraSuite. Enterprise customers subscribe through the Marketplace, and Google handles billing. Customers connect their Google Workspace domain to the hosted ExtraSuite instance.

**Why this fits:**
- ExtraSuite is already a managed service (Cloud Run + Firestore)
- Customers don't need to manage infrastructure
- Domain-wide delegation setup requires admin consent regardless of where the server runs
- Billing integration consolidates into the customer's existing GCP invoice
- Fastest time-to-market (4–8 weeks)

**Architecture for SaaS listing:**

```
┌─────────────────────────────────────────────────┐
│  Google Cloud Marketplace                       │
│  ┌───────────────┐    ┌──────────────────────┐  │
│  │ Customer signs │───▶│ Procurement API      │  │
│  │ up & subscribes│    │ (account + billing)  │  │
│  └───────────────┘    └──────────┬───────────┘  │
│                                  │ Pub/Sub       │
│                                  ▼               │
│  ┌──────────────────────────────────────────┐   │
│  │  ExtraSuite Server (Cloud Run)           │   │
│  │  ┌─────────┐  ┌──────────┐  ┌────────┐  │   │
│  │  │ FastAPI  │  │ Token Gen│  │ Skills │  │   │
│  │  │ + Auth   │  │ (IAM)   │  │ API    │  │   │
│  │  └────┬─────┘  └────┬─────┘  └────────┘  │   │
│  │       │              │                    │   │
│  │  ┌────▼──────────────▼──────────────┐     │   │
│  │  │  Firestore (users, sessions,     │     │   │
│  │  │  access logs, oauth states)      │     │   │
│  │  └──────────────────────────────────┘     │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### Option B: Kubernetes App Listing

In this model, the customer deploys ExtraSuite into their own GKE cluster. Think41 provides the container images and a Helm chart or deployer image.

**Why this could fit:**
- Some enterprises mandate self-hosted solutions for compliance
- Customer retains full control over data and network policies
- Works well for air-gapped or regulated environments

**Why this is harder:**
- Customer must configure their own GCP project (Firestore, IAM roles, OAuth consent screen, domain-wide delegation)
- Significant onboarding complexity — ExtraSuite needs `roles/iam.serviceAccountAdmin`, Firestore composite indexes, OAuth client credentials, etc.
- Requires building a Helm chart, deployer image, and `schema.yaml` for the Marketplace deployer framework
- Ongoing support burden increases significantly

### Recommendation

**Start with SaaS (Option A)**. It aligns with the current architecture, minimizes customer setup friction, and is the faster path to market. Option B can be pursued later for customers with strict self-hosting requirements.

---

## 3. SaaS Listing: Technical Integration Requirements

### 3.1 Partner Program Enrollment

1. Join [Google Cloud Partner Advantage](https://cloud.google.com/partners) program
2. Accept the Cloud Marketplace agreement in Partner Hub
3. Create a dedicated GCP project (e.g., `think41-public`) for Marketplace artifacts
4. Grant IAM roles to Marketplace service accounts:
   - `cloud-commerce-marketplace-onboarding@twosync-src.google.com`
   - `cloud-commerce-producer@system.gserviceaccount.com` (Config Editor)

### 3.2 Billing Integration

Three Google APIs must be integrated into the ExtraSuite server:

| API | Purpose | Implementation Effort |
|-----|---------|----------------------|
| **Pub/Sub** | Receive subscription lifecycle events (signup, plan change, cancellation) | Medium — new endpoint + Pub/Sub subscriber |
| **Partner Procurement API** | Create/manage customer accounts, link to Marketplace purchases | Medium — new module for account lifecycle |
| **Service Control API** | Report usage metrics (if usage-based pricing) | Low–Medium — instrument existing token generation calls |

**New server components needed:**

```
src/extrasuite/server/
├── marketplace/
│   ├── __init__.py
│   ├── procurement.py      # Procurement API client
│   ├── pubsub_handler.py   # Pub/Sub subscription events
│   ├── usage_reporting.py  # Service Control API (if usage-based)
│   └── models.py           # Marketplace-specific data models
```

### 3.3 Frontend Integration (Sign-Up Flow)

When a customer clicks "Subscribe" on the Marketplace listing, Google sends an HTTP POST with a JWT to a sign-up URL. The ExtraSuite server must:

1. Decode and validate the JWT
2. Extract the customer's procurement account ID and Google account ID
3. Create or link the customer's ExtraSuite account
4. Redirect to the ExtraSuite onboarding flow (OAuth consent, domain-wide delegation setup)

**New endpoint:**
```
POST /api/marketplace/signup
```

### 3.4 Account Lifecycle

The server must handle these Pub/Sub events:

| Event | Action |
|-------|--------|
| `ENTITLEMENT_CREATION_REQUESTED` | Approve/reject the new subscription |
| `ENTITLEMENT_ACTIVE` | Provision customer resources |
| `ENTITLEMENT_PLAN_CHANGE_REQUESTED` | Handle plan upgrades/downgrades |
| `ENTITLEMENT_PLAN_CHANGED` | Update customer's plan in Firestore |
| `ENTITLEMENT_CANCELLED` | Deactivate customer, revoke service accounts |
| `ENTITLEMENT_DELETED` | Clean up all customer data |

### 3.5 Firestore Schema Additions

New collection for Marketplace customers:

```
marketplace_accounts/
├── {procurement_account_id}
│   ├── google_account_id: string
│   ├── domain: string
│   ├── plan: string
│   ├── entitlement_id: string
│   ├── status: "active" | "suspended" | "cancelled"
│   ├── created_at: timestamp
│   └── updated_at: timestamp
```

---

## 4. Pricing Model Options

| Model | How It Works | Fit for ExtraSuite |
|-------|-------------|-------------------|
| **Subscription (monthly/annual)** | Flat fee per domain/org | Good — simple, predictable |
| **Per-user subscription** | Fee per active user (service account) | Good — aligns with 1:1 SA model |
| **Usage-based** | Metered by API calls or token generations | Possible — requires Service Control integration |
| **BYOL (Bring Your Own License)** | Customer provides license key | Simpler integration but less Marketplace value |
| **Free trial + paid** | Trial period then paid | Recommended for adoption |

**Recommended pricing strategy:**
- Per-domain monthly subscription with tiered pricing (by number of users/service accounts)
- 14-day free trial to reduce friction
- This aligns naturally with the current per-user service account model

---

## 5. Kubernetes App Listing: Requirements (If Pursued Later)

### 5.1 Artifacts Required

| Artifact | Description |
|----------|-------------|
| **Deployer image** | Docker image with Helm chart + `schema.yaml` at `/data/` |
| **Application image** | The ExtraSuite server container |
| **`schema.yaml`** | Declares all configurable parameters and images |
| **Helm chart** | Templates for Deployment, Service, ConfigMap, Secrets, etc. |

### 5.2 Schema Parameters

```yaml
x-google-marketplace:
  schemaVersion: v2
  applicationApiVersion: v1beta1
  partnerId: think41
  solutionId: extrasuite

  publishedVersion: '1.0.0'
  publishedVersionMetadata:
    releaseNote: Initial release

properties:
  name:
    type: string
    x-google-marketplace:
      type: NAME
  namespace:
    type: string
    x-google-marketplace:
      type: NAMESPACE
  googleCloudProject:
    type: string
    title: GCP Project ID
    description: Project with Firestore and IAM enabled
  googleClientId:
    type: string
    title: OAuth Client ID
  googleClientSecret:
    type: string
    x-google-marketplace:
      type: MASKED_FIELD
  secretKey:
    type: string
    x-google-marketplace:
      type: GENERATED_PASSWORD
      generatedPassword:
        length: 64
  baseDomain:
    type: string
    title: Server domain
  delegationEnabled:
    type: boolean
    title: Enable domain-wide delegation
```

### 5.3 Helm Chart Structure

```
chart/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml        # Cloud Run → K8s Deployment
│   ├── service.yaml           # ClusterIP or LoadBalancer
│   ├── ingress.yaml           # TLS termination
│   ├── configmap.yaml         # Non-secret env vars
│   ├── secret.yaml            # OAuth credentials, SECRET_KEY
│   ├── serviceaccount.yaml    # K8s SA with Workload Identity
│   └── application.yaml       # Marketplace Application CRD
```

### 5.4 Migration Considerations (Cloud Run → GKE)

| Concern | Cloud Run (current) | GKE (self-hosted) |
|---------|--------------------|--------------------|
| Firestore access | ADC via Cloud Run SA | Workload Identity Federation |
| IAM SA creation | ADC | Workload Identity + IAM roles on node SA |
| Health checks | Docker HEALTHCHECK | K8s liveness/readiness probes |
| TLS | Managed by Cloud Run | Ingress controller or cert-manager |
| Scaling | Automatic | HPA based on CPU/request metrics |
| Logging | Stdout → Cloud Logging | Stdout → Cloud Logging (via GKE integration) |

---

## 6. Implementation Roadmap

### Phase 1: SaaS Listing Foundation (Weeks 1–3)

- [ ] Enroll in Google Cloud Partner Advantage
- [ ] Create dedicated Marketplace GCP project
- [ ] Implement Procurement API client module
- [ ] Implement Pub/Sub event handler for entitlement lifecycle
- [ ] Add `/api/marketplace/signup` endpoint with JWT validation
- [ ] Add `marketplace_accounts` Firestore collection and CRUD operations
- [ ] Write tests for all Marketplace integration code

### Phase 2: Billing & Pricing (Weeks 3–5)

- [ ] Define pricing tiers in Producer Portal
- [ ] Implement usage metering (if usage-based pricing chosen)
- [ ] Integrate Service Control API for usage reporting
- [ ] Add plan enforcement logic (user limits per tier)
- [ ] Test end-to-end subscription flow in sandbox

### Phase 3: Listing & Review (Weeks 5–8)

- [ ] Prepare product listing content (description, screenshots, docs links)
- [ ] Submit Product Details for review
- [ ] Submit Pricing for review
- [ ] Submit Technical Integration for review (after Pricing approval)
- [ ] Address reviewer feedback
- [ ] Publish listing

### Phase 4 (Future): Kubernetes App Listing

- [ ] Build Helm chart for self-hosted deployment
- [ ] Create deployer image with `schema.yaml`
- [ ] Build setup wizard for customer-side GCP configuration
- [ ] Publish K8s listing

---

## 7. Estimated Engineering Effort

| Work Item | Effort | Notes |
|-----------|--------|-------|
| Partner enrollment & project setup | 1–2 days | Admin work, mostly paperwork |
| Procurement API integration | 3–5 days | New module, REST client, tests |
| Pub/Sub event handler | 2–3 days | Subscriber setup, event routing |
| Marketplace signup endpoint | 2–3 days | JWT validation, account linking |
| Firestore schema additions | 1 day | New collection, indexes |
| Pricing/metering integration | 2–4 days | Depends on pricing model |
| Listing content & review | 3–5 days | Screenshots, docs, iteration with Google |
| **Total (SaaS listing)** | **~3–5 weeks** | Assumes one engineer |
| Helm chart + K8s deployer (future) | 2–3 weeks | Significant additional effort |

---

## 8. Key Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Partner program approval delay | Blocks everything | Start enrollment immediately |
| Procurement API complexity | Development time | Use [Google's codelab](https://developers.google.com/codelabs/gcp-marketplace-saas) as reference implementation |
| Pricing model mismatch | Revenue impact | Start with simple per-domain subscription; iterate based on customer feedback |
| Review rejection | Delays launch | Study [listing requirements](https://docs.cloud.google.com/marketplace/docs/partners/integrated-saas) thoroughly before submission |
| Self-hosted demand | Missing market segment | Plan K8s listing as Phase 4 but don't block SaaS launch |

---

## 9. References

- [Setting up SaaS for Cloud Marketplace](https://docs.cloud.google.com/marketplace/docs/partners/integrated-saas/set-up-environment)
- [Offering SaaS products](https://docs.cloud.google.com/marketplace/docs/partners/integrated-saas)
- [Backend integration guide](https://docs.cloud.google.com/marketplace/docs/partners/integrated-saas/backend-integration)
- [Frontend integration guide](https://docs.cloud.google.com/marketplace/docs/partners/integrated-saas/frontend-integration)
- [Technical integration setup](https://docs.cloud.google.com/marketplace/docs/partners/integrated-saas/technical-integration-setup)
- [SaaS integration codelab (Python)](https://developers.google.com/codelabs/gcp-marketplace-saas)
- [Sample code on GitHub](https://github.com/googlecodelabs/gcp-marketplace-integrated-saas)
- [Kubernetes app packaging requirements](https://docs.cloud.google.com/marketplace/docs/partners/kubernetes/create-app-package)
- [K8s deployer schema reference](https://github.com/GoogleCloudPlatform/marketplace-k8s-app-tools/blob/master/docs/schema.md)
- [Offer products overview](https://docs.cloud.google.com/marketplace/docs/partners/offer-products)
- [Google Cloud Marketplace overview](https://cloud.google.com/marketplace)
