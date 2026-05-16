# STRATEGY — Berkshire vs GMOM

Dashboard di confronto tra due strategie sistematiche su ETF UCITS.

## Strategia A — Berkshire Style
- 9 ETF UCITS (Value, Quality, Dividend, Gold, Infrastructure, Cash)
- Filtro EMA200 per risk on/off
- AO normalizzato 100gg: BUY <0.25 · HOLD 0.25-0.75 · SELL >0.75
- Logica mean-reversion: accumula nella debolezza

## Strategia B — GMOM Style
- 9 ETF UCITS globali (World, EM, USA, Europe, Japan, Asia, Momentum)
- Filtro EMA200 per risk on/off
- AO direzionale lungo (SMA10-SMA50): BUY quando sale sopra 0
- Ranking momentum 1M/3M/6M (20%/30%/50%)

## Setup

1. Crea il repo su GitHub: `strategy`
2. Abilita GitHub Pages: Settings → Pages → Branch: main → / (root)
3. Esegui il workflow manualmente: Actions → Daily Update → Run workflow

## Aggiornamento

Il workflow gira ogni giorno feriale alle 22:00 UTC e aggiorna `data/bte_data.json`.
