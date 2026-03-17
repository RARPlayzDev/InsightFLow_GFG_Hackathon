# InsightFlow

<p align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![React](https://img.shields.io/badge/React-18-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![SQLite](https://img.shields.io/badge/Database-SQLite-orange)
![Groq](https://img.shields.io/badge/LLM-Groq-red)
![License](https://img.shields.io/badge/License-MIT-purple)

</p>

<p align="center">
<b>Smart BI Dashboards from Plain English</b>
</p>

<p align="center">
Ask a business question → Instantly get SQL, charts, KPIs, and AI insights.
</p>

<p align="center">
Built for the <b>GeeksforGeeks Classroom × MVSR Hyderabad Hackathon 2026</b>
</p>

---

# Overview

**InsightFlow** converts natural-language business questions into **interactive BI dashboards** in seconds.

Instead of writing SQL or building dashboards manually, users simply ask:

```

Compare average online vs store spending by gender and city tier

```

InsightFlow instantly:

• Generates SQL  
• Executes it safely  
• Builds charts  
• Displays KPI cards  
• Writes an AI insight  
• Suggests follow-up questions  

All in **~2 seconds**.

---

# Key Capabilities

| | |
|---|---|
| **Natural Language Queries** | Ask business questions without SQL |
| **Automatic Charts** | Deterministic selection from 6 chart types |
| **KPI Cards** | Key metrics with ₹ formatting |
| **Conversational Analytics** | Follow-up questions refine dashboards |
| **CSV Upload** | Upload any dataset |
| **AI Dataset Overview** | Instant plain-English summary |
| **Smart Follow-ups** | 3 contextual next questions |
| **Query History** | Track all previous queries |
| **PNG Export** | Download individual charts |
| **PDF Export** | Export full dashboards |
| **SQL Transparency** | See the exact SQL generated |
| **Honest AI** | Refuses impossible questions |

---

# Example Workflow

```

User Question
│
▼
"Compare average online vs store spending by gender and city tier"

```

InsightFlow automatically:

```

→ Generates SQL using LLM
→ Validates the query
→ Executes on read-only SQLite
→ Determines optimal chart
→ Builds KPI cards
→ Generates insight
→ Suggests follow-up queries

```

Result: **Instant BI dashboard**

---

# Tech Stack

| Layer | Technology |
|------|-------------|
| Backend | FastAPI · Python |
| Database | SQLite (WAL mode) |
| LLM | Groq API |
| Model | llama-3.3-70b-versatile |
| Frontend | React 18 · Vite |
| Charts | Recharts |
| Export | html-to-image · jsPDF |
| Sessions | In-memory store (TTL) |

---

# Architecture

```

User Question
│
▼
Schema Context Builder
• Token trimming
• Column alias injection

```
  ▼
```

LLM (Groq)
• SQL generation only
• Response cache
• Key rotation on rate limits

```
  ▼
```

SQL Validator
• Blocklist protection
• Table verification
• Regex validation

```
  ▼
```

SQLite Execution
• Read-only mode
• Per-session databases

```
  ▼
```

Visualization Engine
• Deterministic chart selection

```
  ▼
```

Post Processor
• 8 correction rules

```
  ▼
```

Honesty Gate
• Rejects impossible queries

```
  ▼
```

React Dashboard
• Charts
• KPIs
• AI Insights

````

---

# Quick Start

## 1 Clone Repository

```bash
git clone https://github.com/your-username/insightflow.git
cd insightflow
````

---

## 2 Configure Environment

```bash
cp .env.example .env
```

Edit `.env`

```
GROQ_API_KEY=gsk_primary_key
GROQ_API_KEY_2=gsk_second_key
GROQ_API_KEY_3=gsk_third_key
GROQ_MODEL=llama-3.3-70b-versatile
```

Tip: multiple keys allow **instant rate-limit failover**.

---

## 3 Launch InsightFlow

```bash
python start.py
```

This single command automatically:

• Creates Python virtual environment
• Installs backend dependencies
• Installs frontend dependencies
• Starts FastAPI on **8000**
• Starts Vite on **5173**
• Opens browser automatically

Open:

```
http://localhost:5173
```

---

# Manual Setup

## Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Windows:

```
venv\Scripts\activate
```

---

## Frontend

```bash
cd frontend
npm install
npm run dev
```

---

# Project Structure

```
insightflow
│
├── backend
│   ├── main.py
│   ├── ingest.py
│   ├── query_pipeline.py
│   ├── post_processor.py
│   ├── session_store.py
│   ├── schema_context.py
│   └── requirements.txt
│
├── frontend
│   └── src
│       ├── pages
│       │   ├── Landing.jsx
│       │   ├── Dashboard.jsx
│       │   ├── Upload.jsx
│       │   └── History.jsx
│       │
│       ├── components
│       │   ├── DynamicChart.jsx
│       │   ├── SharedComponents.jsx
│       │   ├── ExportButton.jsx
│       │   └── DiagnosticModal.jsx
│       │
│       └── utils
│           ├── api.js
│           ├── session.js
│           └── formatters.js
│
├── data
│   └── Customer_Behaviour__Online_vs_Offline_.csv
│
├── start.py
└── .env.example
```

---

# Visualization Engine

Chart types are determined **algorithmically**, not by the LLM.

| Result Shape                 | Chart       |
| ---------------------------- | ----------- |
| 2 text + 1 numeric           | grouped bar |
| 1 text + 2+ numeric          | grouped bar |
| 2 numeric                    | scatter     |
| 1 text + 1 numeric (ordinal) | line        |
| ≤8 rows                      | pie         |
| >8 rows                      | bar         |

Mixed-scale columns are automatically filtered.

---

# Post-Processing Rules

InsightFlow applies **8 visualization corrections**:

1. Empty result guard
2. Row limit protection
3. Bar/line truncation
4. Pie tail merge
5. Pie dominance detection
6. Grouped bar pivoting
7. Pearson correlation calculation
8. Ambiguity warnings

---

# Rate Limit Strategy

InsightFlow prevents API disruptions with **three layers**.

### Key Rotation

Multiple Groq keys rotate automatically on **429 errors**.

### Response Cache

SHA-256 hashing prevents duplicate API calls.

### Token Trimming

Only relevant schema information is sent to the LLM.

Typical reduction:

```
~55% fewer tokens per query
```

---

# Security

### SQL Protection

Blocked keywords:

```
DROP
INSERT
UPDATE
DELETE
ATTACH
PRAGMA
SQLITE_MASTER
```

Validated using **word-boundary regex**.

---

### Read-Only Databases

SQLite runs in:

```
?mode=ro
```

Writes are impossible.

---

### Session Isolation

Each session gets its **own database file**.

---

### File Upload Safety

• CSV only
• 5MB limit
• UTF-8 / latin-1 support

---

# Demo Queries

After loading the dataset try:

```
Show customer distribution by shopping preference and city tier
Compare average online vs store spending by gender and city tier
Show age distribution of customers by shopping preference
Show distribution of daily internet hours by city tier
Compare brand loyalty scores across shopping preferences
Show monthly online orders vs store visits by city tier
```

---

# Dataset

Bundled dataset:

**Customer Behaviour: Online vs Offline**

```
11,789 customers
25 columns
```

Categories:

| Group         | Columns                                             |
| ------------- | --------------------------------------------------- |
| Demographics  | age, gender, city_tier, monthly_income              |
| Spending      | avg_online_spend, avg_store_spend                   |
| Behaviour     | monthly_online_orders, monthly_store_visits         |
| Digital       | daily_internet_hours, smartphone_usage_years        |
| Psychographic | brand_loyalty, discount_sensitivity, impulse_buying |

---

# Environment Variables

| Variable       | Required | Description      |
| -------------- | -------- | ---------------- |
| GROQ_API_KEY   | Yes      | Primary Groq key |
| GROQ_API_KEY_2 | No       | Backup key       |
| GROQ_API_KEY_3 | No       | Backup key       |
| GROQ_MODEL     | No       | Model name       |

Default model:

```
llama-3.3-70b-versatile
```

---

# Why InsightFlow

Traditional BI tools require:

• SQL knowledge
• Manual dashboards
• Long setup

InsightFlow removes those barriers by turning **plain English into instant analytics**.

---

<p align="center">
<b>InsightFlow</b><br>
Smart dashboards from plain English
</p>
```
