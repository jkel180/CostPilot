# CostPilot AI

Commodity cost intelligence per aziende Food & Beverage. Prima commodity: **Lemon Juice Concentrate**.

Monolite modulare:

| Cartella | Contenuto |
|---|---|
| `apps/api` | Backend Python: FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| `apps/web` | Frontend: Next.js 16, React 19, TypeScript, Tailwind 4, Recharts |

Database e autenticazione: **Supabase** (PostgreSQL gestito + Supabase Auth).

## Stato: Sprint 1 — Foundation

- [x] Struttura del repository
- [x] Schema DB completo (sezione 6 del PRD) + `memberships` e `audit_logs`, con FK, indici, vincoli, campi di audit
- [x] Row Level Security su tutte le tabelle (verificata su PostgreSQL reale)
- [x] Autenticazione Supabase: login, registrazione, recupero password
- [x] Organizzazioni: registrazione, selezione, profilo, gestione utenti e ruoli (Admin / Analyst / Viewer)
- [x] Skeleton della dashboard (KPI, grafici, stato dati) — nessun valore inventato: ogni KPI resta "non disponibile" finché la pipeline relativa non esiste
- [x] Test automatici su autenticazione, ruoli, isolamento tra organizzazioni, migrazioni

## Modello di sicurezza

1. **Backend (barriera principale).** Ogni richiesta verifica il JWT Supabase (firma, scadenza, audience, issuer). Le API sui dati cliente richiedono l'header `X-Organization-Id`, controllano che l'utente sia membro dell'organizzazione e filtrano ogni query per `organization_id`. Un'organizzazione di cui non si è membri risponde `404`, così non si rivela che esiste.
2. **RLS (secondo livello).** Protegge l'accesso diretto via PostgREST con le chiavi pubbliche Supabase: `anon` non ha alcun privilegio; `authenticated` può solo **leggere** le righe delle proprie organizzazioni e i dati di riferimento. Tutte le scritture passano dal backend. `audit_logs` non è leggibile da PostgREST.
3. **Ruoli.** Admin: gestisce profilo e utenti. Analyst / Viewer: sola lettura sull'organizzazione (le differenze tra Analyst e Viewer arrivano con upload acquisti e simulazioni).

Un utente può appartenere a più organizzazioni (tabella `memberships`, che sostituisce `users.organization_id` / `users.role` del PRD).

## Deploy in cloud (da GitHub)

| Componente | Servizio | Deploy |
|---|---|---|
| Database + Auth | Supabase | già attivo |
| Backend `apps/api` | Render (`render.yaml`) | automatico a ogni push su `main`; le migrazioni girano all'avvio |
| Frontend `apps/web` | Vercel | automatico a ogni push su `main`; anteprime per ogni branch |

### 1. Backend su Render

1. render.com → accedi con GitHub → *New → Blueprint* → repository `CostPilot`.
2. Render legge `render.yaml` e chiede i valori segreti:
   - `DATABASE_URL`: la stringa del Session pooler Supabase con prefisso `postgresql+psycopg://` (password URL-encoded).
   - `SUPABASE_URL`: `https://<project-ref>.supabase.co`
   - `CORS_ORIGINS`: per ora `http://localhost:3000`; dopo il passo 2 diventa `https://<app>.vercel.app` (più indirizzi separati da virgola).
3. A deploy finito, `https://<servizio>.onrender.com/health` risponde `{"status":"ok"}`.

Il piano gratuito di Render sospende il servizio dopo 15 minuti di inattività: la prima richiesta successiva impiega ~1 minuto.

### 2. Frontend su Vercel

1. vercel.com → accedi con GitHub → *Add New → Project* → repository `CostPilot`.
2. **Root Directory: `apps/web`** (framework rilevato: Next.js).
3. Environment Variables:
   - `NEXT_PUBLIC_SUPABASE_URL` = `https://<project-ref>.supabase.co`
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` = la publishable key
   - `NEXT_PUBLIC_API_URL` = `https://<servizio>.onrender.com`
4. Deploy.

### 3. Collegamenti finali

- Render → servizio → *Environment*: `CORS_ORIGINS` = `https://<app>.vercel.app`.
- Supabase → *Authentication → URL Configuration*: Site URL `https://<app>.vercel.app`, Redirect URL `https://<app>.vercel.app/auth/callback`.

Le variabili `NEXT_PUBLIC_*` sono incluse nel build: dopo averle cambiate su Vercel serve un *Redeploy*.

## Setup locale

Prerequisiti: Node.js ≥ 20, Python 3.12, un progetto Supabase.

### 1. Supabase

1. Crea un progetto su supabase.com (regione UE).
2. *Authentication → URL Configuration*: Site URL `http://localhost:3000`, Redirect URL `http://localhost:3000/auth/callback`.
3. Annota: Project URL, publishable key, connection string del database (Session pooler).

### 2. Backend

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env      # poi compila DATABASE_URL e SUPABASE_URL
.venv\Scripts\alembic upgrade head
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 3. Frontend

```bash
cd apps/web
npm install
copy .env.example .env.local   # poi compila le variabili Supabase
npm run dev
```

App: http://localhost:3000

## Test

```bash
cd apps/api
.venv\Scripts\python -m pytest
```

```bash
cd apps/web
npm run lint
npm run build
```

## Principi sui dati

- Mai dati sintetici presentati come reali: le fonti sintetiche sono marcate (`data_sources.is_synthetic`) e la dashboard lo segnala.
- `market_observations.data_type` separa benchmark doganali, prezzi spot, prezzi contrattuali e indicatori: non si confrontano tra loro.
- Le previsioni avranno sempre modello, versione dei dati e confronto con le baseline (`forecasts`, `forecast_backtests`).

## Prossimi sprint

- **Sprint 2 — Market Data:** framework di ingestion (Eurostat Comext, UN Comtrade, FAOSTAT), upload CSV di osservazioni e acquisti, grafici storici, provenienza dei dati.
- **Sprint 3 — Analytics:** pipeline di forecasting con backtesting, WAPP, cost model, simulatore.
- **Sprint 4 — AI & Reporting:** Claude API, insights, report, alert.
