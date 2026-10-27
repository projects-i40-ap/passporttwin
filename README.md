# PassportTwin

### Instrument Reliability & Circularity Digital Twin

> An Industry 4.0 platform for building traceable digital passports for laboratory instruments by combining a canonical lifecycle data model, Asset Administration Shell interoperability, reliability analytics and decision-support capabilities.

**Master's Final Project — Industry 4.0**  
Universitat Politècnica de Catalunya (UPC) · 2026

Developed by **[Alexander Castillo](https://github.com/alexanderj-castillo)** and **[Pau Modolell](https://github.com/paumr90)**.

**MVP status — 27 October 2026:** instrument passports, document review, explainable lifecycle Health Score, experimental tolerance-risk forecasts and a Metabase fleet dashboard are implemented. A reproducible local demo is available. Synthetic evaluation supports technical acceptance; final academic and real-world validation remain pending.

[Run the local demo](#-quick-start) · [Demo walkthrough](docs/demo-usability.md) · [Install the fleet dashboard](bi/README.md) · [Synthetic risk evaluation](experiments/acceptance/README.md)

---

## 🎯 The Challenge

Laboratory instruments generate technical, operational, calibration and documentary information throughout their lifecycle, but this information is often fragmented across different systems, formats and processes.

This fragmentation makes it difficult to answer questions such as:

- How reliable is an instrument today?
- Is its calibration behaviour starting to drift?
- Which calibration and source documents support its current state?
- What is its estimated risk of intervention?
- How can technical and lifecycle information be consolidated into a traceable digital passport?
- How could this information support future reuse, refurbishment or reassignment decisions?

**PassportTwin** explores how Digital Twin concepts, lifecycle data, analytics and Asset Administration Shell interoperability can be combined to address these challenges.

---

## 💡 The Solution

PassportTwin builds a digital representation of each laboratory instrument around a **canonical lifecycle model in PostgreSQL**.

The current MVP uses PostgreSQL as the **Source of Truth** and projects interoperable passport information toward **Eclipse BaSyx** through Asset Administration Shell submodels.

The platform is being developed incrementally around:

- canonical instrument and lifecycle data;
- document ingestion, validation and human review;
- calibration history and traceability;
- Asset Administration Shell interoperability;
- reliability, drift and risk analytics;
- QR-based passport access;
- BI and visualization;
- future circularity decision support.

Not all target capabilities are complete. The repository explicitly distinguishes implemented MVP functionality from planned analytical, circularity and experimental-validation work.

---

## 🏗️ MVP Architecture

```mermaid
flowchart LR

    Sources[Instrument, CSV & Document Sources]
        --> Ingestion[Ingestion & Human Review]

    Ingestion --> Backend[FastAPI Backend]

    Backend --> DB[(PostgreSQL<br/>Canonical Source of Truth)]

    DB --> AASBuilder[AASBuilder]
    AASBuilder --> BaSyx[Eclipse BaSyx<br/>AAS Projection]

    DB --> Analytics[Analytics Services]
    Analytics --> Risk[Drift / Risk / Health Indicators]

    Backend --> QR[QR / Passport Resolution]

    DB --> BI[BI & Visualization]
    Risk --> BI

    BaSyx --> Interop[Industry 4.0<br/>Interoperability]
    BI --> Users[Technical & Business Users]
```

### Architectural principle

**PostgreSQL is the canonical system of record.**

The AAS layer is an interoperable projection of the canonical state rather than an independent source of truth.

This separation allows the AAS representation to be rebuilt from PostgreSQL when required.

---

## 🧩 Current MVP Capabilities

### 🪪 Asset Administration Shell Passport

The current MVP integrates four AAS submodels:

| Submodel | Purpose | Current state |
| --- | --- | --- |
| `Nameplate` | Instrument identity and technical characteristics | Integrated |
| `OperationalState` | Lifecycle state, criticality, location and installation information | Integrated |
| `CalibrationHistory` | Complete multi-event calibration history | Integrated |
| `DocumentProvenance` | Accepted source documents, hashes and provenance metadata | Integrated |

`Nameplate` uses an external AAS semantic reference.

`OperationalState`, `CalibrationHistory` and `DocumentProvenance` currently use **PassportTwin-specific semantic identifiers for the MVP**. They must not be interpreted as standardized IDTA submodel templates.

### 🔄 Full AAS Reconstruction

The endpoint:

```text
POST /api/v1/instruments/{id}/sync
```

rebuilds the complete AAS projection for an instrument from the canonical PostgreSQL state.

The synchronization currently covers:

- Nameplate;
- OperationalState;
- complete CalibrationHistory;
- complete accepted DocumentProvenance.

The instrument is marked as `SYNCED` only when all four projections complete successfully.

### 📄 Document Review & Traceability

PassportTwin includes a human-in-the-loop document workflow for calibration information.

The implemented flow supports document extraction and review, field correction, revalidation, canonical acceptance and projection of accepted information toward the AAS layer.

Document provenance includes:

- document identifier;
- original filename;
- source type;
- SHA-256 hash;
- processing status;
- upload timestamp.

Internal infrastructure paths are intentionally not exposed through the AAS passport.

### 📊 Calibration History

Calibration events are persisted canonically in PostgreSQL.

The AAS `CalibrationHistory` submodel represents the complete ordered event history rather than only the latest calibration.

Each projected event can contain:

- calibration event identifier;
- calibration date;
- next due date;
- measured error;
- tolerance;
- calibration result;
- creation timestamp.

### 🏭 Instrument Management & Ingestion

The backend currently supports instrument registration and instrument synchronization through FastAPI.

CSV-based fleet ingestion is also available for creating canonical instrument records and projecting their initial AAS identity and operational state.

### 🔗 QR & Passport Resolution

QR codes resolve to a React instrument passport using a stable public UUID. The frontend supports search by serial number or location, identity and operational state, calibration history, measurement units, linked document review and instrument audit navigation.

The passport distinguishes live calculations from saved BI results and shows when the saved result is missing or stale after data changes.

### 📈 Explainable Health Score & Experimental Risk

The lifecycle Health Score combines four configurable components with default weights: calibration status (30%), predicted risk (30%), recent incidents (20%) and data quality (20%). It displays each contribution and actions for missing information. If a required component cannot be estimated, the score is **not calculated**.

The tolerance-risk model estimates the probability of exceeding tolerance at target dates 30, 60 and 90 days ahead, using a linear calibration-error trend and Gaussian predictive uncertainty. It checks history sufficiency and uses calibration history after the latest maintenance when applicable. These probabilities are experimental and are not experimentally calibrated guarantees.

- [Lifecycle Health Score contract](docs/architecture/lifecycle-health-v2.md)
- [Tolerance-risk model and limitations](docs/architecture/tolerance-risk.md)
- [Frozen synthetic evaluation protocol and results](experiments/acceptance/README.md)

### 📊 Fleet Dashboard & Saved Analytics

The Metabase provisioner creates ten cards covering fleet KPIs, status, intervention priorities, upcoming calibration deadlines, snapshot freshness, Health Score and experimental risk. Family/location filters and links back to instrument passports are included.

Analytical snapshots retain calculation dates, model versions, weights and an input manifest. Refresh is explicit; stale or unavailable results are not presented as current numerical values. Dashboard setup requires a Metabase administrator, a database connection and a target collection; starting the containers alone does not install it.

See [dashboard setup](bi/README.md) and the [snapshot contract](docs/architecture/analytics-snapshots.md).

---

## 🔬 Digital Twin Scope

PassportTwin is intended to go beyond a static dashboard.

The current technical foundation includes:

- a physical asset represented by an instrument;
- a canonical digital state;
- lifecycle and calibration history;
- document provenance;
- an interoperable AAS representation;
- mechanisms to update and reconstruct that representation;
- explainable lifecycle indicators, experimental risk forecasts and versioned BI snapshots.

The following areas remain necessary to complete and academically validate the Digital Twin proposition:

- experimental validation of analytical models;
- extension of the existing synthetic evaluation to the final experimental protocol;
- validation of temporal evolution and risk under real operating conditions;
- final decision-support workflows;
- validation of the complete demonstrator against the TFM objectives.

---

## 🚧 Current Technical Status

The integrated MVP includes the canonical PostgreSQL lifecycle model, FastAPI, React/Vite passports, document review and provenance, CSV ingestion, four AAS projections, QR navigation, lifecycle Health Score, experimental tolerance risk, BI snapshots and Metabase provisioning.

The [27 October usability checkpoint](docs/demo-usability.md#evidencia-de-esta-entrega--27102026) records 164 passing backend/BI tests, a successful frontend build, browser checks and queries against a disposable Metabase instance. These are dated technical checks, not a claim of academic validation or a permanent test count.

Four synthetic scenarios support local rehearsal: healthy, expired calibration, document review and insufficient history. The demo preserves manual corrections and refreshes its saved analytics when rerun. It does not exercise ingestion or AAS synchronization.

**Final end-to-end rehearsal, shared deployment and academic validation remain pending.**

---

## ⚠️ Current Limitations

The current MVP has known limitations that are intentionally kept visible:

- Eclipse BaSyx currently uses in-memory persistence in the development environment;
- `/documents/{id}/accept` is not yet idempotent;
- AAS synchronization does not yet implement robust retry and recovery policies;
- synchronization error reporting can be improved;
- some AAS semantics are PassportTwin-specific rather than standardized templates;
- synthetic risk evaluation is available, but analytical outputs still require final experimental and real-world validation;
- the implemented BI and passport workflows still need final end-to-end rehearsal and shared-environment configuration.

These limitations are treated as implementation or research debt and are not presented as validated capabilities.

---

## 🛠️ Technology Stack

### Backend & Data

`Python` · `FastAPI` · `PostgreSQL` · `SQLAlchemy` · `Pydantic`

### Digital Twin & Interoperability

`Asset Administration Shell (AAS)` · `Eclipse BaSyx` · `Digital Product Passport` · `Industry 4.0`

### Analytics & AI

`Python` · `Data Analytics` · `Drift Analysis` · `Risk & Health Indicators`

### Visualization

`React` · `Vite` · `Metabase`

### Infrastructure & Development

`Docker` · `Docker Compose` · `Git` · `GitHub`

---

## 📁 Repository Structure

```text
passporttwin/
│
├── ai/                    # Analytics, datasets and model development
│
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI endpoints
│   │   ├── core/          # Application configuration
│   │   ├── database/      # Database connection and sessions
│   │   ├── models/        # Domain / database models
│   │   ├── schemas/       # Data validation and API schemas
│   │   └── services/      # Business logic, analytics and AAS services
│   └── tests/             # Automated backend tests
│
├── frontend/              # Visualization / application frontend
├── bi/                    # Fleet SQL views and Metabase provisioning
├── experiments/           # Synthetic evaluation protocols and results
├── tools/                 # Cross-platform local start/demo launcher
├── generators/            # Data and utility generators
├── docs/                  # Architecture and project documentation
├── infra/                 # Infrastructure configuration
│   └── postgres/
│
├── .github/               # GitHub workflows and collaboration templates
├── .env.example           # Environment configuration template
├── docker-compose.yml     # Local multi-service environment
├── CONTRIBUTING.md        # Collaboration workflow
├── CHANGELOG.md           # Project evolution
├── LICENSE                # Copyright and reuse terms
└── README.md
```

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/projects-i40-ap/passporttwin.git
cd passporttwin
```

### 2. Start services and prepare the demo

Requirements: Docker running with Compose v2 supporting `up --wait`, and Python 3.10+ for the launcher. Application dependencies run inside containers.

On **Windows PowerShell**, from the repository root:

```powershell
py tools/dev.py start
py tools/dev.py demo
```

On **Linux/macOS**, use `python3` instead of `py`.

`start` creates `.env` from `.env.example` only if absent, waits for PostgreSQL, ensures the internal Metabase database exists and starts the services. Review local configuration before starting if you need different values. Keep `.env` out of Git.

`demo` applies the analytics migration and BI views, prepares four synthetic instruments and refreshes their snapshots. It preserves existing fixtures and manual corrections; it is not a reset command. It does not execute document ingestion or AAS synchronization.

| Demo serial | Initial scenario |
| --- | --- |
| `PTWIN-DEMO-SANO` | No calibration or document alerts |
| `PTWIN-DEMO-VENCIDO` | Expired calibration |
| `PTWIN-DEMO-REVISION` | Document serial requiring human correction |
| `PTWIN-DEMO-SIN-HISTORIAL` | Insufficient history; score/risk unavailable |

The command prints passport URLs. You can also find these instruments from the application home page. Existing fixture dates do not move forward when the command is repeated.

### 3. Open the local services

| Service | Default URL |
| --- | --- |
| PassportTwin application | http://localhost:5173 |
| FastAPI documentation | http://localhost:8000/docs |
| Metabase | http://localhost:3003 |

If a service is still starting, check `docker compose ps`. Follow the [demo walkthrough](docs/demo-usability.md) to review documents, inspect score changes and refresh saved results.

**Metabase requires initial setup:** create your administrator, connect the application database and select a collection, then run the [dashboard provisioner](bi/README.md). `demo` prepares the SQL views and data, not the dashboard itself. Optionally set `VITE_METABASE_DASHBOARD_URL` to the installed dashboard URL and recreate/rebuild the frontend.

### 4. Run checks separately

Run tests only against a disposable test database; tests may create or modify records. See the [backend test notes](backend/tests/README.md), [BI checks](bi/README.md#pruebas) and CI workflows in `.github/workflows/` for configuration. Local rehearsal is separate from the synthetic acceptance experiments and final TFM validation.

---

## ✅ Development Principles

PassportTwin is developed incrementally around several principles:

1. **PostgreSQL as canonical Source of Truth**
2. **End-to-end value before unnecessary complexity**
3. **Reproducible Docker-based development**
4. **Traceability between source documents, canonical data and AAS projection**
5. **Human review where automated extraction is uncertain**
6. **Clear separation between implementation, testing, integration and validation**
7. **Documentation alongside implementation**
8. **Collaborative development through Git and GitHub**

A feature is not considered academically validated merely because it has been implemented or technically tested.

---

## 🤝 Human–AI Development Methodology

PassportTwin is developed using a controlled **human–AI collaborative workflow**.

Generative AI is used as a technical copilot for architecture, implementation, testing, debugging, documentation, project coordination and academic review. However, AI-generated proposals are not treated as evidence and are not accepted automatically.

The project follows an evidence-driven development cycle:

```text
STATUS → inspect → minimal change → test → evidence → Git → checkpoint
```

Technical work is tracked using explicit evidence states:

```text
PROPOSED → IMPLEMENTED → TESTED → INTEGRATED → VALIDATED
```

These states are intentionally different. Implementing a feature does not mean that it has been tested, integrating it does not mean that it has been experimentally validated, and AI-generated output is not considered validation evidence by itself.

The workflow combines:

- human supervision and final decision-making;
- incremental changes;
- inspection before modification;
- automated testing;
- RED → GREEN development when appropriate;
- Git status and diff review before commits;
- controlled branch integration;
- explicit technical checkpoints;
- traceability between code, tests, documentation and project decisions;
- canonical sources for different types of project information.

The approach incorporates elements associated with emerging **vibe coding** practices, while adding software-engineering controls intended to improve traceability, reproducibility and quality.

For this reason, PassportTwin treats vibe coding as a context for AI-assisted software development rather than as a replacement for engineering methodology.

The methodology itself is being documented and evaluated as part of the Master's Final Project. Its academic analysis will consider benefits, limitations, reproducibility, error control, human supervision and the evidence generated during the development of PassportTwin.

---

## 🗺️ Roadmap

### Foundation

- [x] Repository and collaboration structure
- [x] Docker development environment
- [x] FastAPI backend architecture
- [x] PostgreSQL integration
- [x] Instrument domain and API
- [x] Eclipse BaSyx integration

### Digital Twin & Data

- [x] Core instrument lifecycle model
- [x] CSV inventory ingestion
- [x] Document review and human-in-the-loop workflow
- [x] Calibration-history persistence
- [x] AAS Nameplate
- [x] AAS OperationalState
- [x] AAS CalibrationHistory
- [x] AAS DocumentProvenance
- [x] Full AAS reconstruction from PostgreSQL
- [ ] Persistent / production-grade AAS storage
- [ ] Complete synthetic and experimental datasets

### Analytics

- [x] Initial drift / risk / health analytics service
- [x] Synthetic tolerance-risk protocol and baseline definition
- [x] Frozen synthetic evaluation with held-out forecasts
- [x] Synthetic metric reporting, including adverse stress-test results
- [ ] Real-world and final experimental validation
- [x] Explainable lifecycle Health Score and versioned analytics snapshots
- [ ] Final explainability and reproducibility analysis
- [ ] Final analytical conclusions

### Circularity

- [ ] Circularity criteria
- [ ] Reuse / refurbishment logic
- [ ] Recommendation engine
- [ ] Validation of circularity recommendations

### Decision Support

- [x] QR generation and passport resolution endpoints
- [x] MVP BI views and explicit snapshot freshness
- [x] Metabase fleet overview and intervention priorities
- [x] React instrument passport visualization
- [x] Health Score and experimental risk dashboard cards
- [x] Reproducible four-scenario local demo
- [ ] Shared-environment setup and final end-to-end rehearsal
- [ ] Circularity decision-support views

### Validation & TFM Delivery

- [x] Technical PostgreSQL → AAS integration
- [x] Automated backend test suite
- [ ] Experimental validation
- [ ] Final end-to-end demonstrator
- [ ] Reproducible experiment package
- [ ] Final Master's thesis documentation

### Development Methodology

- [x] Human–AI collaborative workflow defined and applied
- [x] Evidence states defined
- [x] Git / testing / checkpoint workflow applied
- [ ] Systematic methodology evidence collection
- [ ] Methodology analysis in the Master's thesis
- [ ] Evaluation of benefits, limitations and threats to validity

---

## 👥 Authors

PassportTwin is a **joint Master's Final Project** developed by:

### Alexander Castillo

[GitHub](https://github.com/alexanderj-castillo)

Electromechanical Engineer · Industrial Automation · OT/IT Integration · Industry 4.0

### Pau Modolell

[GitHub](https://github.com/paumr90)

Chemical Engineer · Business & Digital Transformation Consultant · Project Manager · Industry 4.0

The project is collaboratively developed. Individual technical contributions and project evolution are traceable through the repository's Git history.

---

## 🎓 Academic Context

PassportTwin is developed as the **Master's Final Project of the Master's Degree in Industry 4.0 at Universitat Politècnica de Catalunya (UPC)**.

The project explores the practical integration of:

**Digital Twins · Asset Administration Shell · Data Analytics · Artificial Intelligence · Business Intelligence · Circular Economy**

within an Industry 4.0 use case.

The academic objective is not only to implement the platform, but also to evaluate its architecture, analytical capabilities, interoperability and usefulness through reproducible evidence.

The project additionally documents and analyses the use of a controlled human–AI collaborative development methodology as part of its engineering process.

---

## 🔐 Data & Privacy

The public repository is intended to contain the software architecture, source code, documentation and examples required to understand and demonstrate the project.

Credentials, local environment configuration, private datasets and confidential information must remain outside version control.

Environment-specific values are managed through `.env` files and other local resources excluded through `.gitignore`.

---

## 📄 License

Copyright © 2026 Alexander Castillo and Pau Modolell Rodríguez.  
**All rights reserved.**

PassportTwin is currently shared publicly for **academic review, demonstration and portfolio purposes**.

Reuse, modification, redistribution, commercialization or creation of derivative works from the original project materials is not permitted without prior written permission from both authors.

See the [`LICENSE`](LICENSE) file for full terms.

---

**PassportTwin · UPC · 2026**
