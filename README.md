# arb-scanner

Telegram bot that finds **sportsbook arbitrage opportunities** — where odds
across DraftKings / FanDuel / BetMGM / Caesars / ESPN BET / BetRivers /
Pinnacle disagree enough that you can stake both sides for **guaranteed
profit regardless of outcome**.

```
   ┌─────────────────────┐
   │   The Odds API      │  free tier: 500 req/month
   │   (NFL, NBA, MLB,   │
   │    NHL, UFC, EPL)   │
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │  arb_finder.py      │  for each event, group by market+line
   │                     │  → take best price per side across books
   │                     │  → arb if Σ(1/decimal_odds) < 1.0
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │     Telegram        │
   │   • Per-arb alerts  │
   │   • Stake split per │
   │     $1000 bankroll  │
   └─────────────────────┘
```

## How the math works

For a 2-leg arb on decimal odds `d1` and `d2`:

- **Implied probability sum**: `1/d1 + 1/d2`
- If this is **< 1.0**, you have an arb. Profit margin = `(1 / sum) - 1`.
- **Stake allocation** for total bankroll `B`: `stake_i = B × (1/d_i) / sum`
- Payout (regardless of outcome): `B / sum`

Example: 49ers ML at DraftKings (+155 → 2.55) and Cowboys ML at FanDuel
(+125 → 2.25). `1/2.55 + 1/2.25 = 0.392 + 0.444 = 0.836`. Sum is < 1, so
this is an arb of `(1/0.836 − 1) = 19.6%`. (In reality, gaps that wide
basically never happen in major US sports — typical arbs are 1–4%.)

## Setup

```bash
git clone https://github.com/andycheigh/arb-scanner.git
cd arb-scanner
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in 3 keys: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ODDS_API_KEY
python main.py
```

## Required keys

| Var | Where to get it |
|---|---|
| `TELEGRAM_BOT_TOKEN` | `@BotFather` on Telegram → `/newbot`. Recommended: a fresh bot separate from any other notifier so you can mute independently. |
| `TELEGRAM_CHAT_ID` | DM your new bot once, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` |
| `ODDS_API_KEY` | [the-odds-api.com](https://the-odds-api.com/) — free tier 500 req/month, no card |

## Tuning (in `.env`)

| Var | Default | Notes |
|---|---|---|
| `MIN_PROFIT_PCT` | `1.0` | raise to 2.0 to cut "blink-and-miss" alerts |
| `BANKROLL_USD` | `1000` | stake-allocation reference; you scale on execution |
| `SPORTS` | NFL, NBA, MLB, NHL, EPL | comma-separated `the-odds-api` sport keys |
| `BOOKS` | DK, FD, BetMGM, Caesars, BetRivers, ESPN, William Hill, Pinnacle | bookmaker keys |

Default scan cadence is **6×/day** (every 4 hours: 3a/7a/11a/3p/7p/11p PT).
With 5 sports × 6 scans = 30 reqs/day = ~900/month — fits inside the
**1000/month** budget you get from running two free-tier keys
(`ODDS_API_KEY` + `ODDS_API_KEY_2`, round-robined automatically).
The bot warns you when any single key drops to ≤50 remaining.

## Deploy to a Linux box

```bash
./deploy.sh user@your-devbox
```

Sets up a venv, installs deps, drops a `systemd` unit, starts the
service. Idempotent — re-run to push code changes.

## What this does NOT do

- **Auto-execute bets.** Clicking through is on you. (Account-safety,
  legal, and "books ban arbers fast" reasons.)
- **Player props.** Names aren't standardized across books — needs an
  LLM-driven normalization pass. Coming in v2.
- **Live / in-play.** Lines move every few seconds; free tier can't keep up.
- **Account management.** No bankroll tracking, no P&L history, no
  bet recording.

## Reality check

Arb bots are real but the books are also real about catching arbers.
Expect 3–6 months of clean play before sharp books (DK, FD especially)
limit your stakes. Mitigations: round-number stakes, mix in some
recreational losing bets, rotate accounts, prefer smaller-variance arbs.

## Files

| | |
|---|---|
| `config.py` | env + tuning |
| `odds_api.py` | The Odds API client |
| `arb_finder.py` | core arb math (h2h, spreads, totals) |
| `telegram_bot.py` | per-arb alert formatter |
| `state.py` | dedup store |
| `engine.py` | scan + alert orchestration |
| `main.py` | entry |
| `deploy.sh` | systemd installer for Linux hosts |

## License

MIT
