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

## Sprint 2 — Market Data

- [x] Framework di ingestion con interfaccia comune (`fetch_data → validate_data → normalize_data → save_data → log_execution`), log di ogni esecuzione (`ingestion_runs`) e `data_version` (hash dei dati salvati)
- [x] Connettore **Eurostat Comext** (DS-045409): valore unitario all'import UE (EUR/kg) e volumi per origine, dal 2019
- [x] Upload manuale CSV di osservazioni di mercato (solo platform admin, con fonte originale obbligatoria)
- [x] Import CSV acquisti: mapping colonne (nomi italiani/inglesi), validazione per riga, anteprima, import parziale, annullamento
- [x] Analisi acquisti: prezzo medio ponderato (WAPP) per fornitore, prodotto e mese, mai mescolando unità o valute
- [x] Pagine Market Intelligence e My Purchases, grafici storici in dashboard, provenienza e date di aggiornamento visibili

**Cosa misura il benchmark.** Il lemon concentrate ai prezzi di mercato è dichiarato in dogana sotto **CN 20093939** ("succo di un solo agrume, Brix 20–67, > 30 €/100 kg, senza zuccheri aggiunti"). Il codice non è solo limone (include altri agrumi esclusi arancia e pompelmo): i codici CN specifici per il limone esistono solo per la fascia ≤ 30 €/100 kg, che non corrisponde ai prezzi del concentrato. È un valore doganale medio, non un prezzo spot o contrattuale, ed è etichettato così ovunque.

**Regole di qualità** (deterministiche): senza valore o quantità → scartato; volume mensile < 50 t → `unvalidated`; valore unitario oltre 3× o sotto 1/3 della mediana della serie → `rejected`; altrimenti `validated`. Grafici e KPI usano solo i mesi `validated`.

**Aggiornamento.** Un workflow GitHub Actions (`.github/workflows/ingest-eurostat.yml`) lancia l'import il 20 di ogni mese; un platform admin può lanciarlo anche dalla pagina Market Intelligence.

## Sprint 3 — Analytics

- [x] Pipeline di forecasting riproducibile (1/3/6 mesi) sul benchmark Eurostat: naive, seasonal naive, exponential smoothing (con e senza stagionalità), ARIMA (ordine scelto per AIC), ensemble ETS+ARIMA, regressione pooled sulle importazioni di 8 Paesi UE e media ETS+pooled (vedi `docs/valutazione-fattori-esterni.md`)
- [x] Backtesting rolling-origin su 36 origini: ogni previsione usa solo i dati disponibili a quella data (test automatico anti look-ahead)
- [x] Metriche: MAE, WAPE, directional accuracy, copertura degli intervalli; un modello viene usato **solo se batte la miglior baseline**, altrimenti la previsione è marcata `below_baseline` e mostrata come "nessuna variazione"
- [x] Intervalli di previsione all'80% empirici (quantile degli errori di backtest); scenari prezzi più bassi / base / più alti = estremi dell'intervallo e previsione centrale, non generati da un LLM
- [x] Ogni run salva `input_data_version` (hash della serie usata), `model_version` (pipeline + librerie) e parametri: stesso input → stessa previsione
- [x] Cost model per organizzazione (volumi, prezzo attuale e target, pass-through, quota di costo) e Cost Simulator (WAPP, impatto sul periodo, annualizzato, risparmi)
- [x] Dashboard: KPI previsioni 3/6 mesi, esposizione di costo, grafici Forecast vs storico, Mercato vs prezzo cliente, scenari di impatto

**Regole di confronto.** Prezzo cliente e benchmark si confrontano solo in EUR/kg; tonnellate e libbre convertite con fattori fissi; altre valute e unità di volume (che richiederebbero una densità dipendente dal Brix) sono escluse e segnalate. Il gap è indicativo: il benchmark è un valore doganale di un codice più ampio.

**Formule (spec 3.4).** variazione prezzo = variazione benchmark × pass-through; impatto periodo = (prezzo scenario − prezzo attuale) × quantità; annualizzato = impatto mensile × 12.

**XGBoost** non è usato: con ~90 osservazioni mensili un modello ad albero non è giustificato dai dati.

La previsione viene ricalcolata in background dopo ogni import Eurostat riuscito (manuale o mensile); un platform admin può lanciarla anche dalla pagina Forecasting.

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
   - `PLATFORM_ADMIN_EMAILS`: email degli operatori CostPilot che gestiscono i dati di mercato condivisi.
   - `INGESTION_TOKEN`: segreto lungo e casuale per l'import mensile automatico (vedi sotto).
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

### 4. Import mensile Eurostat (GitHub Actions)

GitHub → repository → *Settings → Secrets and variables → Actions*:
- *Secrets*: `INGESTION_TOKEN` = lo stesso valore impostato su Render.
- *Variables*: `API_URL` = `https://<servizio>.onrender.com`.

Il workflow gira il 20 di ogni mese; si può lanciare a mano da *Actions → Ingest Eurostat Comext → Run workflow*.

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
