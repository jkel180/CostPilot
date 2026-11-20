# Valutazione dei fattori esterni per la previsione (novembre 2026)

**Domanda.** La previsione del benchmark (valore unitario all'import UE, CN 20093939) usa solo la storia del prezzo. Aggiungere fattori esterni riduce l'errore?

**Risposta.** No, non con i dati disponibili oggi. Nessun fattore riduce l'errore in modo coerente sui tre orizzonti; alcuni lo aumentano molto. **Nessun fattore è stato integrato nel prodotto.**

## Metodo

- Serie: benchmark extra-UE, mesi validati, gennaio 2019 – settembre 2026 (93 mesi).
- Modello: regressione ridge diretta per orizzonte, `log(y[t+h] / y[t]) = a + b · x[t]`, con fattori standardizzati.
- Nessun dato futuro: ogni fattore è preso al mese di origine `t` o prima (ONI con almeno un mese di ritardo, perché la media trimestrale si chiude dopo).
- Stesse 36 origini e stessa metrica (MAE in €/kg) della pipeline in produzione; confronto con il modello naive e con l'exponential smoothing oggi selezionato (MAE 0,195 / 0,258 / 0,277 a 1 / 3 / 6 mesi).
- Due livelli di regolarizzazione (α = 1 e 10), fissati prima di vedere i risultati.
- Un solo test aggiuntivo dichiarato in anticipo (ENSO con ritardo 9–12 mesi), poi stop, per non cercare relazioni casuali a forza di tentativi.

## Fattori provati

| Fattore | Fonte | Variabili |
|---|---|---|
| Momentum del prezzo | Eurostat Comext | variazione 1 e 3 mesi, scarto dalla media 12 mesi |
| Argentina | Eurostat Comext | variazione del valore unitario, differenza vs benchmark |
| Volumi | Eurostat Comext | volume extra-UE anno su anno, quota Argentina |
| Cambio EUR/USD | BCE (EXR.M.USD.EUR.SP00.A) | variazione 1 e 3 mesi |
| El Niño | NOAA ONI | anomalia con ritardo 1, 6, 9 e 12 mesi |

## Risultati (variazione del MAE rispetto all'exponential smoothing attuale; negativo = meglio)

| Insieme di fattori (α = 10) | 1 mese | 3 mesi | 6 mesi |
|---|---|---|---|
| Solo momentum | +5% | +5% | +9% |
| + Argentina | +8% | +16% | +30% |
| + Volumi | +1% | +5% | +8% |
| + EUR/USD | −3% | +7% | +6% |
| + El Niño (rit. 1–6) | +7% | +17% | +31% |
| + El Niño (rit. 9–12) | +7% | +14% | +4% |
| Tutti insieme | −2% | +28% | +60% |

Con α = 1 i risultati sono simili o peggiori (tutti insieme: +63% e +142% a 3 e 6 mesi, tipico sovradattamento).

## Lettura

- Il cambio EUR/USD migliora leggermente solo a 1 mese (−1% / −3%): una differenza di questa dimensione su 36 prove è compatibile con il caso.
- Argentina ed El Niño peggiorano: con 93 mesi i modelli trovano relazioni che non si ripetono.
- La previsione resta quindi basata sulla sola storia del prezzo, con un intervallo ampio che rappresenta l'incertezza reale.

## Quando rifare la prova

- Con almeno 2–3 anni di dati in più.
- Con fonti più vicine al mercato (prezzi contrattuali o di broker su licenza), che descrivono il prezzo pagato e non solo il valore doganale.
- Con dati di raccolto mensili o stagionali (non solo annuali FAOSTAT).

Lo script dell'analisi è stato eseguito fuori dal prodotto; per ripeterla basta lo stesso schema di backtest della pipeline (`apps/api/app/forecasting/pipeline.py`).

---

# Seconda valutazione: dati più vicini al mercato e modello "pooled" (novembre 2026)

**Protocollo, fissato prima dei risultati.** Sviluppo e scelta solo sulle origini con target prima degli ultimi 12 mesi; gli ultimi 12 mesi usati **una sola volta** come conferma. Regola di adozione: il candidato deve battere l'exponential smoothing in media e su almeno 2 orizzonti su 3 nella finestra di conferma.

**Nuovi dati (Eurostat Comext).**
- Limoni freschi (CN 08055010), import extra-UE e intra-UE (soprattutto Spagna): la materia prima del concentrato.
- Lo stesso succo (CN 20093939) importato da 8 Paesi UE (IT, DE, NL, ES, FR, BE, PL, AT), da fuori e da dentro l'UE: 16 serie che seguono lo stesso mercato.
- Il portale Agri-food UE (prezzi dei limoni freschi) non risponde agli indirizzi API documentati: escluso.

**Idea.** Con ~90 mesi per serie una regressione non impara nulla di stabile; addestrandola su tutte le serie insieme ("pooled") gli esempi diventano circa 10 volte di più.

| Candidato (variazione MAE vs ETS) | Sviluppo 1 / 3 / 6 mesi | Conferma 1 / 3 / 6 mesi |
|---|---|---|
| Regressione sulla sola serie benchmark | +15% / +21% / +13% | +0% / +8% / +12% |
| Pooled (8 Paesi) | +3% / −5% / −7% | −4% / −6% / +7% |
| Pooled + limoni freschi | +14% / −4% / −7% | +6% / −2% / +6% |
| **Media ETS + pooled** | **−3% / −5% / −4%** | **−4% / −4% / +3%** |

**Esito.** La media ETS + pooled passa la regola (meglio in media e a 1 e 3 mesi), con un miglioramento piccolo. I limoni freschi non aiutano. Nel prodotto i due nuovi modelli sono stati aggiunti **come candidati**: la pipeline continua a scegliere, orizzonte per orizzonte, il modello con l'errore più basso nel backtest, e solo se batte la baseline.

**Effetto sulla prima previsione (dati fino a settembre 2026).** A 1 mese viene scelto ETS + pooled (errore −7,0% vs naive, contro −5,5% di ETS): €2,26/kg invece di €2,30, intervallo €1,94–2,57. A 3 e 6 mesi resta ETS.

Le 16 serie di supporto sono salvate come osservazioni Comext (`<paese>:<partner>`), incluse nell'`input_data_version` di ogni previsione e non mostrate nelle pagine di mercato.
