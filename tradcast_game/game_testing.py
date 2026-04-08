import sys, os
_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_dir))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from game.price_flow import PriceFlow, spike_df_map
from game.wallet import FuturesWallet
import json
import random
import time
import uuid
import asyncio
from datetime import datetime, timezone
from collections import deque
from utils.auth_utils import decrypt
from utils.main_server_energy import sync_game_cache_energy_from_main
from configs.config import WS_ALLOWED_ORIGINS, CORS_ALLOWED_ORIGINS, SECRET
from storage.firestore_client import firestore_manager, firestore_read_counter
firestore_manager.cache_only = True
from storage.local_trades_db import trades_db
from storage.energy_manager import EnergyManager
import requests
import threading

energy_manager = EnergyManager(firestore_manager, cache_only=True)

MAIN_API_URL = os.getenv("MAIN_API_URL", "http://localhost:6001")
SECRET_KEY = SECRET

game_app = FastAPI()

game_app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def increase_tracker_thread(fid, timeout=10):
    """Synchronous call to main API's increase_tracker endpoint."""
    try:
        requests.get(
            f"{MAIN_API_URL}/increase_tracker",
            params={"fid": fid},
            timeout=timeout,
        )
    except requests.Timeout:
        print(f"Tracker increase for FID {fid} timed out")
    except Exception as e:
        print(f"Error increasing tracker: {e}")


def notify_score_update_thread(
    fid: str,
    profit: float,
    session_id: str = "",
    trade_env_id: str = "",
    final_pnl: float = 0.0,
    created_at: float = 0.0,
    timeout=10,
):
    """Notify the main server to update leaderboard cache + sync trade summary."""
    payload = {
        "fid": fid,
        "profit": profit,
        "secret": SECRET_KEY,
        "session_id": session_id,
        "trade_env_id": trade_env_id,
        "final_pnl": final_pnl,
        "created_at": created_at,
    }
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{MAIN_API_URL}/internal/update_score",
                json=payload,
                timeout=timeout,
            )
            if resp.status_code == 200:
                return
            last_err = resp.status_code
            time.sleep(0.5 * (attempt + 1))
        except Exception as e:
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    print(f"Error notifying score update after retries: {last_err}")


@game_app.on_event("startup")
async def startup():
    await firestore_manager.db.collection("_warmup").document("_ping").get()
    firestore_read_counter.inc("startup_warmup")
    print("Firestore connection warmed up")
    await firestore_manager.load_all_users()
    await firestore_manager.start_keep_alive()
    asyncio.create_task(energy_manager.start_reenergization_loop())


@game_app.get('/')
async def game_router_status():
    return {'status': 'running'}


@game_app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()
    print('accepted')

    trade_actions = []
    trade_env_id = str(uuid.uuid4())
    fid = None
    auth_time = None
    session_timeout = 250
    session_end_time = None

    rate_limit_window = deque(maxlen=15)
    rate_limit_duration = 1.0

    def is_rate_limited() -> bool:
        now = time.time()
        while rate_limit_window and rate_limit_window[0] < now - rate_limit_duration:
            rate_limit_window.popleft()

        if len(rate_limit_window) >= 15:
            return True

        rate_limit_window.append(now)
        return False

    def is_session_expired() -> bool:
        if session_end_time is not None:
            current_time = datetime.now(timezone.utc)
            if current_time >= session_end_time:
                return True

        if auth_time is None:
            return False
        return time.time() - auth_time >= session_timeout

    try:
        auth_message = await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
        auth_data = json.loads(auth_message)
        print(auth_data)

        encrypted_token = auth_data.get('encrypted_token')
        print(encrypted_token)

        if not encrypted_token:
            try:
                await websocket.send_json({"error": "No encrypted_token provided"})
            except Exception as e:
                print(e)
                pass
            await websocket.close(code=1008)
            return

        try:
            print(encrypted_token)
            decrypted_json = decrypt(encrypted_token, SECRET_KEY)
            print('decrypt failed')
            payload = json.loads(decrypted_json)
            print(payload)

            fid = payload.get('fid')
            if fid:
                fid = fid.lower().strip()
            session_end = payload.get('session_end')

            if session_end:
                try:
                    session_end_time = datetime.fromisoformat(session_end.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) >= session_end_time:
                        try:
                            await websocket.send_json({
                                "error": "session_expired",
                                "message": "Session end time has passed"
                            })
                        except Exception:
                            pass
                        await websocket.close(code=1008)
                        return
                except ValueError:
                    pass

            await sync_game_cache_energy_from_main(
                firestore_manager, MAIN_API_URL, SECRET_KEY, str(fid)
            )

            resp = await firestore_manager.reduce_energy(str(fid))
            if resp:
                auth_time = time.time()
                thread = threading.Thread(target=increase_tracker_thread, args=(fid,), daemon=True)
                thread.start()

                try:
                    await websocket.send_json({"authenticated": True, "fid": fid})
                except Exception:
                    return
            else:
                try:
                    await websocket.send_json({"error": "no energy"})
                except Exception:
                    pass
                await websocket.close(code=1008)
                return
            
            try:
                await firestore_manager.handle_daily_games(fid)
            except Exception as e:
                print('error handle daily games: ', e)
                return

        except Exception as e:
            print(f"Authentication failed: {e}")
            try:
                await websocket.send_json({"error": "Authentication failed"})
            except Exception:
                pass
            await websocket.close(code=1008)
            return

    except asyncio.TimeoutError:
        await websocket.close(code=1008)
        return
    except json.JSONDecodeError:
        await websocket.close(code=1008)
        return
    except WebSocketDisconnect:
        return

    sending_task = None
    handle_wallet_task = None
    timeout_task = None

    keys = list(spike_df_map.keys())
    random_token = random.choice(keys)

    price_flow = PriceFlow(token_selection=random_token)
    futures_wallet = FuturesWallet(leverage=20, token_selection=random_token)

    async def auto_close_after_timeout():
        try:
            if session_end_time:
                seconds_until_end = (session_end_time - datetime.now(timezone.utc)).total_seconds()
                timeout_duration = min(session_timeout, max(0, seconds_until_end))
            else:
                timeout_duration = session_timeout

            await asyncio.sleep(timeout_duration)
            try:
                await websocket.send_json({"type": "session_timeout", "message": "Session expired"})
                await websocket.close(code=1000, reason="Session timeout")
            except Exception:
                pass
        except asyncio.CancelledError:
            pass

    async def handle_wallet():
        try:
            while True:
                if is_session_expired():
                    try:
                        await websocket.send_json({
                            "type": "session_expired",
                            "message": "Session end time has passed"
                        })
                    except Exception:
                        pass
                    break

                await futures_wallet.consume_queue()
                await futures_wallet.calculate_final_balance(price_flow.current_index)

                try:
                    await websocket.send_json({
                        "type": "wallet",
                        "wallet": await futures_wallet.get_wallet_state()
                    })
                except Exception:
                    break

                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in handle_wallet: {e}")

    async def stream_rows():
        try:
            window = await price_flow.initialize_dict()
            await websocket.send_json({"count": price_flow.window_size, "window": window})
            await asyncio.sleep(1)
            await price_flow.handle_websocket_flow(websocket)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Error in stream_rows: {e}")
            raise

    try:
        timeout_task = asyncio.create_task(auto_close_after_timeout())

        while True:
            if is_session_expired():
                try:
                    await websocket.send_json({
                        "type": "session_expired",
                        "message": "Session end time has passed"
                    })
                except Exception:
                    pass
                break

            message = await websocket.receive_text()

            if message == "start":
                if sending_task is None or sending_task.done():
                    futures_wallet = FuturesWallet(leverage=20, token_selection=random_token)
                    sending_task = asyncio.create_task(stream_rows())
                    handle_wallet_task = asyncio.create_task(handle_wallet())
                    await asyncio.sleep(0.01)
                    try:
                        await websocket.send_text("Streaming started.")
                    except Exception:
                        break
                else:
                    try:
                        await websocket.send_text("Already streaming.")
                    except Exception:
                        break

            elif message == "stop":
                if sending_task:
                    sending_task.cancel()
                    handle_wallet_task.cancel()
                    await asyncio.sleep(0.01)
                    try:
                        await websocket.send_text("Streaming stopped.")
                    except Exception:
                        break
                else:
                    try:
                        await websocket.send_text("Nothing is streaming.")
                    except Exception:
                        break

            elif message in ("long", "short", "close"):
                if is_rate_limited():
                    try:
                        await websocket.send_json({
                            "error": "Rate limit exceeded",
                            "message": "Maximum 15 actions per second"
                        })
                    except Exception:
                        break
                    continue

                index = price_flow.current_index
                current_time = time.time()

                if message == "long":
                    print('long')
                    await futures_wallet.push_order_long(index)
                elif message == "short":
                    print('short')
                    await futures_wallet.push_order_short(index)

                elif message == "close":
                    print('close')
                    await futures_wallet.push_close(index)

                trade_actions.append({
                    "action": message,
                    "time": current_time,
                    "index": index,
                })

            else:
                try:
                    await websocket.send_text(f"Message received: {message}")
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Error in WebSocket loop: {e}")
    finally:
        if sending_task:
            sending_task.cancel()
        if handle_wallet_task:
            handle_wallet_task.cancel()
        if timeout_task:
            timeout_task.cancel()

        if fid and trade_actions:
            try:
                wallet_state = await futures_wallet.get_wallet_state()
                final_profit = wallet_state.get('balance_total', 0.0)
                if final_profit != 0.0:
                    final_profit = final_profit - 1000
                final_pnl = final_profit / 10

                await firestore_manager.save_game_session_result(
                    fid=str(fid),
                    final_pnl=final_pnl,
                    final_profit=final_profit,
                )

                import time as _t
                _now = _t.time()
                trades_db.insert_trade(
                    session_id=trade_env_id,
                    fid=str(fid),
                    trade_env_id=random_token,
                    actions=trade_actions,
                    final_pnl=final_pnl,
                    final_profit=final_profit,
                )

                thread = threading.Thread(
                    target=notify_score_update_thread,
                    kwargs={
                        "fid": str(fid),
                        "profit": final_profit,
                        "session_id": trade_env_id,
                        "trade_env_id": random_token,
                        "final_pnl": final_pnl,
                        "created_at": _now,
                    },
                    daemon=True,
                )
                thread.start()
            except Exception as e:
                print(f"Error saving session on disconnect: {e}")



@game_app.get('/increase_tracker')
def increase_tracker(fid: int):
    resp = requests.get(
        f"{MAIN_API_URL}/increase_tracker",
        params={'fid': fid},
        timeout=10,
    )
    if resp.status_code == 200:
        return {'status': 'success'}
    return {'status': 'failed'}


@game_app.get('/get_tracker')
def get_tracker():
    resp = requests.get(f"{MAIN_API_URL}/get_tracker", timeout=10)
    return resp.json()

@game_app.get('/transactions', response_class=HTMLResponse)
async def get_transactions_page():
    """Serve the transactions visualization page"""
    
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transaction Data</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 30px;
        }
        
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        
        .refresh-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-bottom: 30px;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .refresh-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            font-size: 18px;
            color: #667eea;
        }
        
        .error {
            background: #fee;
            border: 1px solid #fcc;
            color: #c33;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            text-align: center;
        }
        
        .view-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }
        
        .chart-section {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .chart-title {
            font-size: 20px;
            font-weight: 600;
            color: #333;
            margin-bottom: 15px;
            text-align: center;
        }
        
        .chart-container {
            position: relative;
            height: 400px;
        }
        
        .selected-date-info {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 15px;
            text-align: center;
            font-weight: 600;
            display: none;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }
        
        .stat-label {
            font-size: 14px;
            opacity: 0.9;
            margin-bottom: 8px;
        }
        
        .stat-value {
            font-size: 28px;
            font-weight: bold;
        }

        @media (max-width: 768px) {
            .view-container {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Transaction Data Dashboard</h1>
        <p class="subtitle">View gameplay transactions per date and FID distribution</p>
        
        <button class="refresh-btn" onclick="fetchData()">Refresh Data</button>
        
        <div id="content">
            <div class="loading">Loading data...</div>
        </div>
    </div>

    <script>
        let dateChart, fidChart;
        let allData = {};
        let dataByDate = {};
        
        async function fetchData() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="loading">Loading data...</div>';
            
            try {
                const response = await fetch('/get_tracker');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                allData = await response.json();
                
                if (!allData || Object.keys(allData).length === 0) {
                    content.innerHTML = `
                        <div class="error">
                            <p>No transaction data available yet.</p>
                            <p style="margin-top: 10px; font-size: 14px;">Data will appear here after gameplay sessions.</p>
                        </div>
                    `;
                    return;
                }
                
                content.innerHTML = `
                    <div class="view-container">
                        <div class="chart-section">
                            <div class="chart-title">Total Transactions per Date</div>
                            <div style="text-align: center; margin-bottom: 15px;">
                                <label for="dateSelector" style="font-weight: 600; color: #333; margin-right: 10px;">Select Date:</label>
                                <select id="dateSelector" onchange="onDateSelected()" style="padding: 8px 15px; border: 2px solid #667eea; border-radius: 6px; font-size: 14px; cursor: pointer; background: white;">
                                    <option value="">Choose a date...</option>
                                </select>
                            </div>
                            <div class="chart-container">
                                <canvas id="dateChart"></canvas>
                            </div>
                        </div>
                        
                        <div class="chart-section">
                            <div class="selected-date-info" id="selectedDateInfo">
                                Selected Date: <span id="selectedDateText"></span>
                            </div>
                            <div class="chart-title">FID Distribution</div>
                            <div class="chart-container">
                                <canvas id="fidChart"></canvas>
                            </div>
                        </div>
                    </div>
                    
                    <div class="stats-grid" id="statsGrid"></div>
                `;
                
                loadData();
                
            } catch (error) {
                console.error('Error fetching data:', error);
                content.innerHTML = `
                    <div class="error">
                        <p>Failed to load data from API</p>
                        <p style="margin-top: 10px; font-size: 14px;">Error: ${error.message}</p>
                        <p style="margin-top: 10px; font-size: 14px;">Please try refreshing the page.</p>
                    </div>
                `;
            }
        }
        
        function loadData() {
            dataByDate = {};
            Object.keys(allData).forEach(fid => {
                const date = allData[fid].date;
                const count = allData[fid].count;
                
                if (!dataByDate[date]) {
                    dataByDate[date] = {
                        total: 0,
                        fids: {}
                    };
                }
                
                dataByDate[date].total += count;
                dataByDate[date].fids[fid] = count;
            });
            
            visualizeDateChart();
            updateStats();
        }
        
        function visualizeDateChart() {
            const dates = Object.keys(dataByDate).sort();
            const totals = dates.map(date => dataByDate[date].total);
            
            const dateSelector = document.getElementById('dateSelector');
            dateSelector.innerHTML = '<option value="">Choose a date...</option>';
            dates.forEach(date => {
                const option = document.createElement('option');
                option.value = date;
                option.textContent = date;
                dateSelector.appendChild(option);
            });
            
            if (dateChart) dateChart.destroy();
            
            const ctx = document.getElementById('dateChart').getContext('2d');
            dateChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: dates,
                    datasets: [{
                        label: 'Total Transactions',
                        data: totals,
                        backgroundColor: 'rgba(102, 126, 234, 0.8)',
                        borderColor: 'rgba(102, 126, 234, 1)',
                        borderWidth: 2,
                        borderRadius: 8,
                        hoverBackgroundColor: 'rgba(118, 75, 162, 0.9)'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    onClick: (event, elements) => {
                        if (elements.length > 0) {
                            const index = elements[0].index;
                            const selectedDate = dates[index];
                            const dateSelector = document.getElementById('dateSelector');
                            dateSelector.value = selectedDate;
                            visualizeFidChart(selectedDate);
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return 'Total: ' + context.parsed.y + ' transactions';
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1
                            }
                        },
                        x: {
                            ticks: {
                                font: {
                                    weight: 'bold'
                                }
                            }
                        }
                    }
                }
            });
            
            if (dates.length > 0) {
                const dateSelector = document.getElementById('dateSelector');
                dateSelector.value = dates[0];
                visualizeFidChart(dates[0]);
            }
        }
        
        function onDateSelected() {
            const dateSelector = document.getElementById('dateSelector');
            const selectedDate = dateSelector.value;
            if (selectedDate) {
                visualizeFidChart(selectedDate);
            }
        }
        
        function visualizeFidChart(selectedDate) {
            const fids = Object.keys(dataByDate[selectedDate].fids);
            const counts = fids.map(fid => dataByDate[selectedDate].fids[fid]);
            
            document.getElementById('selectedDateInfo').style.display = 'block';
            document.getElementById('selectedDateText').textContent = selectedDate;
            
            if (fidChart) fidChart.destroy();
            
            const ctx = document.getElementById('fidChart').getContext('2d');
            const colors = generateColors(fids.length);
            
            fidChart = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: fids.map(fid => `FID ${fid}`),
                    datasets: [{
                        data: counts,
                        backgroundColor: colors,
                        borderWidth: 2,
                        borderColor: '#fff'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: {
                                boxWidth: 15,
                                padding: 10,
                                font: {
                                    size: 12
                                }
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.label || '';
                                    const value = context.parsed || 0;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = ((value / total) * 100).toFixed(1);
                                    return `${label}: ${value} (${percentage}%)`;
                                }
                            }
                        }
                    }
                }
            });
        }
        
        function updateStats() {
            const totalFids = Object.keys(allData).length;
            const totalDates = Object.keys(dataByDate).length;
            const totalTransactions = Object.values(allData).reduce((sum, item) => sum + item.count, 0);
            const avgPerDate = totalDates > 0 ? (totalTransactions / totalDates).toFixed(2) : 0;
            
            const statsGrid = document.getElementById('statsGrid');
            statsGrid.innerHTML = `
                <div class="stat-card">
                    <div class="stat-label">Total FIDs</div>
                    <div class="stat-value">${totalFids}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total Dates</div>
                    <div class="stat-value">${totalDates}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total Transactions</div>
                    <div class="stat-value">${totalTransactions}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Avg per Date</div>
                    <div class="stat-value">${avgPerDate}</div>
                </div>
            `;
        }
        
        function generateColors(count) {
            const colors = [];
            for (let i = 0; i < count; i++) {
                const hue = (i * 360 / count) % 360;
                colors.push(`hsla(${hue}, 70%, 60%, 0.8)`);
            }
            return colors;
        }
        
        fetchData();
    </script>
</body>
</html>
    """
    
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("game_testing:game_app", port=6011, reload=False)
