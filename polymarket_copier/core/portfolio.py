"""Portfolio state tracking with SQLite persistence (aiosqlite, WAL mode)."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite

from polymarket_copier.core.risk_manager import ExitReason, Position, Side

logger = logging.getLogger("polymarket_copier")

# US long-term capital-gains threshold: assets held > 1 year. Prediction-market
# positions are almost always short-term, but tracking the split is the whole
# point of a tax-lot ledger, so the boundary is recorded per disposal.
_LONG_TERM_HOLDING_SECONDS = 365 * 86_400

_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    position_id     TEXT PRIMARY KEY,
    market_id       TEXT NOT NULL,
    token_id        TEXT NOT NULL,
    trader_address  TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    tp_price        REAL NOT NULL,
    sl_price        REAL NOT NULL,
    peak_price      REAL NOT NULL,
    size_shares     REAL NOT NULL,
    entry_time      REAL NOT NULL,
    resolve_time    REAL,
    status          TEXT NOT NULL DEFAULT 'open',
    exit_price      REAL,
    exit_reason     TEXT,
    realized_pnl    REAL,
    closed_at       REAL
);

-- Realized-PnL tax-lot ledger. One immutable row per disposal (position close),
-- capturing cost basis, proceeds, holding period and short/long-term character.
-- This is the foundation for year-end realized-gain reporting; the positions
-- table alone only keeps the latest realized_pnl and can't be aggregated by
-- tax year or holding term.
CREATE TABLE IF NOT EXISTS realized_lots (
    lot_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id     TEXT NOT NULL,
    token_id        TEXT NOT NULL,
    trader_address  TEXT NOT NULL,
    shares          REAL NOT NULL,
    cost_basis      REAL NOT NULL,   -- USDC paid to acquire (entry_price * shares)
    proceeds        REAL NOT NULL,   -- USDC received on disposal (exit_price * shares)
    realized_pnl    REAL NOT NULL,   -- proceeds - cost_basis
    acquired_at     REAL NOT NULL,   -- position entry_time (Unix)
    disposed_at     REAL NOT NULL,   -- close time (Unix)
    holding_seconds REAL NOT NULL,
    term            TEXT NOT NULL     -- 'short' or 'long'
);
CREATE INDEX IF NOT EXISTS idx_realized_lots_disposed ON realized_lots (disposed_at);
-- Cover realized_lots lookups by position (e.g. audit queries and cascade checks).
CREATE INDEX IF NOT EXISTS idx_realized_lots_position ON realized_lots (position_id);
-- Cover get_trader_pnl / get_trader_win_rate (both filter trader_address + status='closed')
-- and the Kelly sizing queries that fire on every copy decision.
CREATE INDEX IF NOT EXISTS idx_positions_trader_status ON positions (trader_address, status);
-- Cover get_position_by_token / get_positions_by_token (token_id + status='open')
-- and position_count, eliminating full table scans on the per-tick exit-evaluation path.
CREATE INDEX IF NOT EXISTS idx_positions_token_status ON positions (token_id, status);
"""


class PortfolioManager:
    """SQLite-backed store of open and closed copy-trade positions."""

    def __init__(self, db_path: str = "data/positions.db"):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        """Open the SQLite connection, enable WAL mode, and create the schema if absent."""
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.executescript(_SCHEMA)
        await self._migrate()
        await self._db.commit()
        logger.info("Portfolio DB initialized: %s", self._db_path)

    async def _migrate(self) -> None:
        """Additive schema migrations for databases created before a column existed.

        `mode` tags each position with the trading mode it was opened under, so
        the forward-paper gate (live mode requires N closed PAPER trades with
        positive net PnL) can tell paper evidence from live evidence. Added
        WITHOUT a DEFAULT: a database created before this column existed may
        contain positions opened under LIVE mode (the bot has always supported
        it), and defaulting those rows to 'paper' would let them silently
        satisfy the forward-paper gate with zero actual paper trades. Legacy
        rows stay NULL ("unknown provenance") and get_forward_paper_stats()
        excludes anything that isn't explicitly mode='paper'.
        """
        cursor = await self._db.execute("PRAGMA table_info(positions)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "mode" not in columns:
            await self._db.execute("ALTER TABLE positions ADD COLUMN mode TEXT")
            logger.info("Migrated positions table: added 'mode' column (NULL for pre-existing rows)")

    async def close(self) -> None:
        """Close the underlying SQLite connection if it is open."""
        if self._db:
            await self._db.close()

    def _require_db(self) -> aiosqlite.Connection:
        """Return the live connection or fail loudly if init() was never awaited.

        Without this guard, every query below would raise a cryptic
        ``AttributeError: 'NoneType' object has no attribute 'execute'`` that
        gives no hint about the real cause (a missing ``await portfolio.init()``).
        """
        if self._db is None:
            raise RuntimeError("PortfolioManager is not initialized. Call `await portfolio.init()` before using it.")
        return self._db

    async def open_position(self, pos: Position, mode: str = "paper") -> None:
        """Insert a new open position row into the positions table and commit."""
        db = self._require_db()
        await db.execute(
            """INSERT INTO positions
               (position_id, market_id, token_id, trader_address, entry_price,
                tp_price, sl_price, peak_price, size_shares, entry_time, resolve_time, status, mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
            (
                pos.position_id,
                pos.market_id,
                pos.token_id,
                pos.trader_address,
                pos.entry_price,
                pos.tp_price,
                pos.sl_price,
                pos.peak_price,
                pos.size_shares,
                pos.entry_time,
                pos.resolve_time,
                mode,
            ),
        )
        await db.commit()
        logger.info("Position opened in DB: %s (mode=%s)", pos.position_id, mode)

    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: ExitReason,
        filled_shares: Optional[float] = None,
    ) -> Optional[float]:
        """Record a filled disposal, reducing or closing the position as appropriate."""
        db = self._require_db()
        pos = await self.get_position(position_id)
        if pos is None:
            logger.warning("Position %s not found for closing", position_id)
            return None

        shares = pos.size_shares if filled_shares is None else filled_shares
        if not 0.0 < shares <= pos.size_shares:
            raise ValueError(f"filled_shares must be in (0, {pos.size_shares}], got {shares}")
        pnl = pos.pnl_at(exit_price) * shares / pos.size_shares
        closed_at = time.time()

        if shares < pos.size_shares:
            cur = await db.execute(
                """UPDATE positions SET size_shares=?, realized_pnl=COALESCE(realized_pnl, 0) + ?
                   WHERE position_id=? AND status='open' AND size_shares=?""",
                (pos.size_shares - shares, pnl, position_id, pos.size_shares),
            )
        else:
            cur = await db.execute(
                """UPDATE positions SET status='closed', exit_price=?, exit_reason=?,
                   realized_pnl=COALESCE(realized_pnl, 0) + ?, closed_at=?
                   WHERE position_id=? AND status='open'""",
                (exit_price, reason.name, pnl, closed_at, position_id),
            )
        if cur.rowcount != 1:
            logger.warning("Position %s was already closed or changed", position_id)
            return None

        cost_basis = pos.entry_price * shares
        proceeds = exit_price * shares
        holding_seconds = max(0.0, closed_at - pos.entry_time)
        term = "long" if holding_seconds > _LONG_TERM_HOLDING_SECONDS else "short"
        await db.execute(
            """INSERT INTO realized_lots
                (position_id, token_id, trader_address, shares, cost_basis,
                 proceeds, realized_pnl, acquired_at, disposed_at,
                 holding_seconds, term)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                position_id,
                pos.token_id,
                pos.trader_address,
                shares,
                cost_basis,
                proceeds,
                pnl,
                pos.entry_time,
                closed_at,
                holding_seconds,
                term,
            ),
        )
        await db.commit()
        action = "reduced" if shares < pos.size_shares else "closed"
        logger.info("Position %s: %s reason=%s pnl=%.4f", action, position_id, reason.name, pnl)
        return pnl

    async def realized_pnl_report(self, year: Optional[int] = None) -> dict:
        """Aggregate the realized-lot ledger into a tax-style summary.

        Pass ``year`` (UTC) to scope to a single tax year by disposal date;
        omit it for an all-time report. Returns total proceeds, cost basis,
        net realized PnL, the short/long-term split, and disposal count.
        """
        db = self._require_db()
        where = ""
        params: tuple = ()
        if year is not None:
            start = datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp()
            where = "WHERE disposed_at >= ? AND disposed_at < ?"
            params = (start, end)
        cursor = await db.execute(
            f"""SELECT
                   COUNT(*),
                   COALESCE(SUM(proceeds), 0),
                   COALESCE(SUM(cost_basis), 0),
                   COALESCE(SUM(realized_pnl), 0),
                   COALESCE(SUM(CASE WHEN term='short' THEN realized_pnl ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN term='long'  THEN realized_pnl ELSE 0 END), 0)
               FROM realized_lots {where}""",
            params,
        )
        row = await cursor.fetchone()
        return {
            "year": year,
            "disposals": int(row[0]) if row else 0,
            "proceeds": float(row[1]) if row else 0.0,
            "cost_basis": float(row[2]) if row else 0.0,
            "net_realized_pnl": float(row[3]) if row else 0.0,
            "short_term_pnl": float(row[4]) if row else 0.0,
            "long_term_pnl": float(row[5]) if row else 0.0,
        }

    async def get_open_positions(self) -> List[Position]:
        """Return all positions whose status is 'open'."""
        db = self._require_db()
        cursor = await db.execute("SELECT * FROM positions WHERE status='open'")
        rows = await cursor.fetchall()
        return [_row_to_position(row) for row in rows]

    async def get_position(self, position_id: str) -> Optional[Position]:
        """Return the position with the given id, or None if not found."""
        db = self._require_db()
        cursor = await db.execute("SELECT * FROM positions WHERE position_id=?", (position_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_position(row)

    async def get_position_by_token(self, token_id: str) -> Optional[Position]:
        """Return a single open position for the given token id, or None if none exists."""
        db = self._require_db()
        cursor = await db.execute("SELECT * FROM positions WHERE token_id=? AND status='open'", (token_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_position(row)

    async def get_positions_by_token(self, token_id: str) -> List[Position]:
        """Return ALL open positions on a token.

        Two different tracked traders can each be copied into a SEPARATE
        position (unique position_id) on the same token. The singular
        get_position_by_token() returns only one of them, so per-tick exit
        evaluation and source-exit mirroring must use this plural query to
        avoid orphaning the second (and beyond) position on a shared token.
        """
        db = self._require_db()
        cursor = await db.execute("SELECT * FROM positions WHERE token_id=? AND status='open'", (token_id,))
        rows = await cursor.fetchall()
        return [_row_to_position(row) for row in rows]

    async def position_count(self) -> int:
        """Return the number of currently open positions."""
        db = self._require_db()
        cursor = await db.execute("SELECT COUNT(*) FROM positions WHERE status='open'")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def update_peak_price(self, position_id: str, peak_price: float) -> None:
        """Update the stored peak_price for a position (used for trailing-stop tracking)."""
        db = self._require_db()
        await db.execute(
            "UPDATE positions SET peak_price=? WHERE position_id=?",
            (peak_price, position_id),
        )
        await db.commit()

    async def batch_update_peak_prices(self, updates: dict) -> None:
        """Update peak_price for multiple positions in a single transaction (H11 debounced flush).

        Accepts a dict of {position_id: new_peak_price}. A single commit amortises
        the SQLite I/O cost so the per-tick hot path writes zero bytes to disk.
        """
        if not updates:
            return
        db = self._require_db()
        for position_id, peak in updates.items():
            await db.execute(
                "UPDATE positions SET peak_price=? WHERE position_id=?",
                (peak, position_id),
            )
        await db.commit()

    async def get_open_unrealized_pnl_conservative(self) -> float:
        """Return sum of (sl_price - entry_price)*size_shares for all open positions.

        Always <= 0: represents the maximum realizable loss if every open stop
        is hit simultaneously — used as a conservative mark-to-market by the
        daily-loss circuit breaker.

        Computed via a single SQL aggregate instead of loading every open
        Position into Python, which avoids O(n) object construction on the
        entry-decision hot path when many positions are held.
        """
        db = self._require_db()
        cursor = await db.execute(
            "SELECT COALESCE(SUM((sl_price - entry_price) * size_shares), 0.0) FROM positions WHERE status = 'open'"
        )
        row = await cursor.fetchone()
        return float(row[0]) if row else 0.0

    async def get_trader_pnl(self, trader_address: str) -> float:
        """Return the summed realized PnL of all closed positions copied from a trader."""
        db = self._require_db()
        cursor = await db.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0) FROM positions WHERE trader_address=? AND status='closed'",
            (trader_address,),
        )
        row = await cursor.fetchone()
        return float(row[0]) if row else 0.0

    async def get_trader_win_rate(self, trader_address: str) -> tuple[float, int]:
        """Return (win_rate, sample_size) over CLOSED positions for a trader.

        A closed position with ``realized_pnl > 0`` counts as a win. The win
        rate is wins / sample_size in [0, 1]. With no closed positions for the
        trader, returns ``(0.0, 0)`` so callers can gate on sample size.
        """
        db = self._require_db()
        cursor = await db.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) "
            "FROM positions WHERE trader_address=? AND status='closed'",
            (trader_address,),
        )
        row = await cursor.fetchone()
        total = int(row[0]) if row and row[0] is not None else 0
        wins = int(row[1]) if row and row[1] is not None else 0
        if total == 0:
            return 0.0, 0
        return wins / total, total

    async def get_forward_paper_stats(self) -> dict:
        """Closed-PAPER-trade evidence for the forward-paper gate.

        Only positions explicitly tagged mode='paper' count — positions from a
        database predating the mode column are NULL (unknown provenance, not
        assumed paper) and positions opened under mode='live' are excluded, so
        neither can silently satisfy "prove it in paper mode first".
        """
        db = self._require_db()
        cursor = await db.execute(
            """SELECT COUNT(*),
                      COALESCE(SUM(realized_pnl), 0),
                      SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)
               FROM positions WHERE status='closed' AND mode='paper'"""
        )
        row = await cursor.fetchone()
        closed_trades = int(row[0]) if row and row[0] is not None else 0
        net_pnl = float(row[1]) if row else 0.0
        wins = int(row[2]) if row and row[2] is not None else 0
        return {
            "closed_trades": closed_trades,
            "net_pnl": net_pnl,
            "win_rate": (wins / closed_trades) if closed_trades else 0.0,
        }

    async def summary(self) -> str:
        """Return a formatted text summary of open count, closed trades, win rate, and realized PnL."""
        db = self._require_db()
        open_count = await self.position_count()
        cursor = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(realized_pnl), 0), "
            "SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) "
            "FROM positions WHERE status='closed'"
        )
        row = await cursor.fetchone()
        total = row[0] if row else 0
        realized = row[1] if row else 0
        wins = row[2] if row and row[2] is not None else 0
        wr = (wins / total * 100) if total > 0 else 0
        return (
            "=== Portfolio Summary ===\n"
            f"Open positions: {open_count}\n"
            f"Closed trades: {total}\n"
            f"Win rate: {wr:.1f}%\n"
            f"Realized P&L: ${realized:.2f}"
        )


def _row_to_position(row) -> Position:
    return Position(
        position_id=row[0],
        market_id=row[1],
        token_id=row[2],
        trader_address=row[3],
        entry_price=row[4],
        tp_price=row[5],
        sl_price=row[6],
        peak_price=row[7],
        size_shares=row[8],
        entry_time=row[9],
        resolve_time=row[10],
        side=Side.BUY,
    )
