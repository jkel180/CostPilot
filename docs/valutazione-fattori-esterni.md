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
