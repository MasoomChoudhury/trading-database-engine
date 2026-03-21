from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from database.supabase_client import RemoteDBWatcher

router = APIRouter(prefix="/data", tags=["Data"])
templates = Jinja2Templates(directory="templates")


@router.post("/prune-estimate", response_class=HTMLResponse)
async def prune_estimate(request: Request, start_date: str = Form(None), end_date: str = Form(None)):
    if not end_date:
        return HTMLResponse("<p class='text-red-400 text-xs'>Please select a date range.</p>")

    db = RemoteDBWatcher()
    info = db.get_chunk_info(end_date)

    if "error" in info:
        return HTMLResponse(f"""
            <div class='bg-yellow-900/20 border border-yellow-500/30 p-3 rounded-lg'>
                <p class='text-[10px] text-yellow-400 uppercase font-bold mb-1'>⚠️ Limited Access</p>
                <p class='text-xs text-slate-300'>{info['error']}</p>
                <p class='text-[10px] text-slate-500 mt-2'>
                    Supabase shared plans may restrict TimescaleDB catalog access.
                    Pruning via direct DELETE is still possible.
                </p>
            </div>
        """)

    chunks = info.get("chunks", [])
    total = info.get("total_chunks", 0)

    if total == 0:
        return HTMLResponse(f"""
            <div class='bg-green-900/20 border border-green-500/30 p-3 rounded-lg'>
                <p class='text-xs text-green-400 font-bold'>✅ No chunks older than {end_date}</p>
                <p class='text-[10px] text-slate-500 mt-1">Nothing to prune for this date range.</p>
            </div>
        """)

    chunk_rows = ""
    for c in chunks[:10]:  # show first 10
        chunk_rows += f"""
            <tr class='border-b border-slate-800 text-xs'>
                <td class='py-1 px-2 text-slate-400'>{c.get('name', 'N/A')}</td>
                <td class='py-1 px-2 text-slate-400'>{c.get('end', 'N/A')}</td>
                <td class='py-1 px-2 text-blue-400 font-mono'>{c.get('size', 'N/A')}</td>
            </tr>"""
    if len(chunks) > 10:
        chunk_rows += f"""
            <tr class='border-b border-slate-800 text-xs'>
                <td colspan='3' class='py-1 px-2 text-slate-500 text-center'>
                    + {len(chunks) - 10} more chunks...
                </td>
            </tr>"""

    return HTMLResponse(f"""
        <div class='bg-blue-900/20 border border-blue-500/30 p-3 rounded-lg'>
            <p class='text-[10px] text-blue-400 uppercase font-bold mb-1'>Chunks to be dropped</p>
            <table class='w-full text-left mb-2'>
                <thead>
                    <tr class='text-[10px] text-slate-500 uppercase'>
                        <th class='py-1 px-2'>Chunk</th>
                        <th class='py-1 px-2'>Range End</th>
                        <th class='py-1 px-2'>Size</th>
                    </tr>
                </thead>
                <tbody>{chunk_rows}</tbody>
            </table>
            <p class='text-xs text-blue-200'>
                <strong>{total}</strong> chunk(s) will be dropped.
            </p>
        </div>
    """)


@router.post("/prune-execute", response_class=HTMLResponse)
async def prune_execute(request: Request, end_date: str = Form(None)):
    if not end_date:
        return HTMLResponse("<div class='text-red-400'>No target date provided.</div>")

    db = RemoteDBWatcher()
    result = db.drop_chunks(end_date)

    if result.get("success"):
        method = result.get("method", "unknown")
        if method == "drop_chunks":
            return HTMLResponse(f"""
                <div class='bg-green-900/40 border border-green-500 p-4 rounded-xl text-green-100 shadow-lg'>
                    <p class='font-bold'>✅ drop_chunks() executed successfully!</p>
                    <p class='text-xs opacity-80 mt-1'>
                        Hypertable chunks older than <strong>{end_date}</strong> have been dropped.
                    </p>
                </div>
            """)
        else:
            return HTMLResponse(f"""
                <div class='bg-green-900/40 border border-green-500 p-4 rounded-xl text-green-100 shadow-lg'>
                    <p class='font-bold'>✅ Old rows deleted successfully!</p>
                    <p class='text-xs opacity-80 mt-1'>
                        Deleted <strong>{result.get('rows_deleted', 0)}</strong> rows older than <strong>{end_date}</strong>.
                    </p>
                </div>
            """)
    else:
        return HTMLResponse(f"""
            <div class='bg-red-900/40 border border-red-500/50 p-4 rounded-xl text-red-200'>
                <p class='font-bold text-red-400'>❌ Pruning failed</p>
                <p class='text-xs mt-1 font-mono'>{result.get('error', 'Unknown error')}</p>
            </div>
        """)


@router.get("/audit", response_class=HTMLResponse)
async def audit_data(request: Request):
    """Detects gaps in 5-minute candle time-series over the last 24 hours."""
    try:
        db = RemoteDBWatcher()
        audit = db.audit_candle_gaps(hours_back=24)

        gaps = audit.get("gaps", [])
        total = audit.get("total_rows", 0)
        method = audit.get("method", "unknown")

        if "error" in audit:
            return HTMLResponse(f"""
                <div class='flex items-center space-x-2 text-xs font-bold'>
                    <span class='w-2 h-2 rounded-full bg-yellow-500'></span>
                    <span class='text-yellow-400'>Audit unavailable: {audit['error']}</span>
                </div>
            """)

        if len(gaps) == 0:
            return HTMLResponse(f"""
                <div class='flex items-center space-x-2 text-xs font-bold'>
                    <span class='w-2 h-2 rounded-full bg-green-500'></span>
                    <span class='text-green-400'>Data Integrity: Perfect — {total} candles, 0 gaps</span>
                </div>
            """)
        else:
            # Build a tooltip with gap details
            gap_lines = ""
            for g in gaps[:5]:
                prev = g.get("previous_candle", "N/A")
                gap_s = g.get("gap_seconds", 0)
                mins = round(gap_s / 60, 1)
                gap_lines += f"  {prev}  +{mins}m gap\n"
            if len(gaps) > 5:
                gap_lines += f"  ... and {len(gaps) - 5} more"

            return HTMLResponse(f"""
                <div class='flex items-center space-x-2 text-xs font-bold'
                     title="Gaps (first 5):&#10;{gap_lines.strip()}">
                    <span class='w-2 h-2 rounded-full bg-red-500 animate-pulse'></span>
                    <span class='text-red-400'>⚠ Data Alarm: {len(gaps)} gap(s) in last {total} candles</span>
                </div>
            """)
    except Exception as e:
        return HTMLResponse(f"<span class='text-red-400 text-[10px]'>Audit Error: {str(e)}</span>")


@router.get("/chart", response_class=JSONResponse)
async def chart_data():
    """Returns OHLCV data for TradingView Lightweight Charts (last 200 candles)."""
    try:
        db = RemoteDBWatcher()
        response = db.supabase.table("market_data").select(
            "timestamp, Open, High, Low, Close, Volume"
        ).order("timestamp", desc=False).limit(200).execute()

        formatted_data = []
        if response.data:
            for row in response.data:
                ts_str = row.get("timestamp", "")
                # LightweightCharts expects Unix timestamp in seconds
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    ts = int(dt.timestamp())
                except Exception:
                    continue

                formatted_data.append({
                    "time": ts,
                    "open": row.get("Open"),
                    "high": row.get("High"),
                    "low": row.get("Low"),
                    "close": row.get("Close"),
                    "volume": row.get("Volume"),
                })

        return formatted_data
    except Exception as e:
        print(f"Chart data error: {e}")
        return []


@router.get("/chart-update", response_class=JSONResponse)
async def chart_update():
    """
    Returns the latest candle + any new candles since last poll.
    The frontend polls this every 30s and updates the chart live.
    """
    try:
        db = RemoteDBWatcher()
        response = db.supabase.table("market_data").select(
            "timestamp, Open, High, Low, Close, Volume"
        ).order("timestamp", desc=False).limit(5).execute()

        candles = []
        if response.data:
            for row in response.data:
                ts_str = row.get("timestamp", "")
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    ts = int(dt.timestamp())
                except Exception:
                    continue

                candles.append({
                    "time": ts,
                    "open": row.get("Open"),
                    "high": row.get("High"),
                    "low": row.get("Low"),
                    "close": row.get("Close"),
                    "volume": row.get("Volume"),
                })

        return candles
    except Exception as e:
        print(f"Chart update error: {e}")
        return []
