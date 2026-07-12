let equityChart;
let journal = [];

async function fetchLiveState() {
    try {
        const res = await fetch('/api/state');
        if (!res.ok) throw new Error("Failed to fetch state");
        const data = await res.json();
        updateDashboard(data);
    } catch (e) {
        console.log("Waiting for bot to start...", e);
        document.getElementById('goalPhase').textContent = "OFFLINE";
        document.getElementById('goalPhase').style.background = "rgba(255, 51, 102, 0.1)";
        document.getElementById('goalPhase').style.color = "#ff3366";
    }
}

// Utility to animate number counting up
function animateValue(obj, start, end, duration, isCurrency=false) {
    if (!obj) return;
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        
        // easing (easeOutQuart)
        const easeOut = 1 - Math.pow(1 - progress, 4);
        const current = start + (end - start) * easeOut;
        
        if (isCurrency) {
            obj.innerHTML = `$${current.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        } else {
            obj.innerHTML = current.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
        
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

function updateDashboard(state) {
    const config = state.config || {};
    journal = state.trade_journal || [];
    
    // Topbar
    const accLabel = document.getElementById('accountLabel');
    if (accLabel) {
        if (config.active_firm) {
            accLabel.textContent = config.active_firm.split('_')[0]; // Show just the name
        } else {
            accLabel.textContent = `${config.phase || "LIVE"} Account`;
        }
    }
    
    // Update Dropdown Data
    const dropdownAccId = document.getElementById('dropdownAccId');
    if (dropdownAccId) {
        dropdownAccId.textContent = config.account_login ? config.account_login.toString() : "Not Connected";
    }
    
    const dropdownFirmName = document.getElementById('dropdownFirmName');
    if (dropdownFirmName) {
        dropdownFirmName.textContent = config.active_firm || "Custom Hybrid";
    }
    
    const goalPhase = document.getElementById('goalPhase');
    if (goalPhase) {
        goalPhase.textContent = config.phase || "LIVE";
        goalPhase.style.background = "rgba(0, 204, 255, 0.1)";
        goalPhase.style.color = "#00ccff";
    }
    
    const settingDailyDd = document.getElementById('settingDailyDd');
    if (settingDailyDd) {
        settingDailyDd.value = (config.max_daily_dd !== undefined) ? config.max_daily_dd.toString() : "5.0";
    }
    const settingGlobalDd = document.getElementById('settingGlobalDd');
    if (settingGlobalDd) {
        settingGlobalDd.value = (config.max_global_dd !== undefined) ? config.max_global_dd.toString() : "10.0";
    }

    const balance = config.starting_balance || 0;
    const equity = state.equity || balance;
    
    // Process History
    let sniperWins = 0, sniperTotal = 0;
    let asianWins = 0, asianTotal = 0;
    let totalWinAmt = 0, totalWins = 0;
    let totalLossAmt = 0, totalLosses = 0;
    let pairPnl = {};
    let totalPnl = 0;
    
    // Render Full History
    const historyBody = document.getElementById('historyBody');
    document.getElementById('historyCount').textContent = journal.length;
    historyBody.innerHTML = '';
    
    const reversedJournal = [...journal].reverse();
    if (reversedJournal.length === 0) {
        historyBody.innerHTML = `<tr><td colspan="5" class="empty-state">No trade history yet.</td></tr>`;
    } else {
        reversedJournal.forEach(t => {
            const pnl = t.pnl || 0;
            totalPnl += pnl;
            const isAsian = t.strategy === "ASIAN";
            
            if (isAsian) {
                asianTotal++;
                if (pnl > 0) asianWins++;
            } else {
                sniperTotal++;
                if (pnl > 0) sniperWins++;
            }
            
            if (pnl > 0) {
                totalWins++;
                totalWinAmt += pnl;
            } else if (pnl < 0) {
                totalLosses++;
                totalLossAmt += Math.abs(pnl);
            }
            
            if (!pairPnl[t.pair]) pairPnl[t.pair] = 0;
            pairPnl[t.pair] += pnl;

            const pnlCls = pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
            const sign = pnl >= 0 ? '+' : '';
            const strategyBadge = isAsian ? 
                `<span class="badge" style="background: rgba(16, 185, 129, 0.1); color: #10B981;">ASIAN</span>` : 
                `<span class="badge" style="background: rgba(139, 92, 246, 0.1); color: #8B5CF6;">SNIPER</span>`;

            historyBody.innerHTML += `
                <tr>
                    <td><strong>${t.pair || '--'}</strong></td>
                    <td>${strategyBadge}</td>
                    <td class="${pnlCls}">${sign}$${pnl.toFixed(2)}</td>
                    <td class="${pnlCls}">${sign}$${pnl.toFixed(2)}</td>
                    <td>${t.reason.replace('_', ' ')}</td>
                </tr>
            `;
        });
    }
    
    // Render Full Ledger for Order List View
    const fullHistoryBody = document.getElementById('fullHistoryBody');
    document.getElementById('fullHistoryCount').textContent = reversedJournal.length;
    fullHistoryBody.innerHTML = '';
    if (reversedJournal.length === 0) {
        fullHistoryBody.innerHTML = `<tr><td colspan="7" class="empty-state">No trades executed yet.</td></tr>`;
    } else {
        reversedJournal.forEach(t => {
            const pnl = t.pnl || 0;
            const isAsian = t.strategy === "ASIAN";
            const pnlCls = pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
            const sign = pnl >= 0 ? '+' : '';
            const strategyBadge = isAsian ? 
                `<span class="badge" style="background: rgba(16, 185, 129, 0.1); color: #10B981;">ASIAN</span>` : 
                `<span class="badge" style="background: rgba(139, 92, 246, 0.1); color: #8B5CF6;">SNIPER</span>`;
            
            const entryTime = new Date(t.entry_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            const exitTime = new Date(t.exit_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

            fullHistoryBody.innerHTML += `
                <tr>
                    <td><strong>${t.pair}</strong></td>
                    <td>${strategyBadge}</td>
                    <td>${entryTime}</td>
                    <td>${exitTime}</td>
                    <td>${t.original_lots || 1.0}</td>
                    <td class="${pnlCls}">${sign}$${pnl.toFixed(2)}</td>
                    <td>${t.reason.replace('_', ' ')}</td>
                </tr>
            `;
        });
    }

    // Render Economic Calendar (Live News Data)
    const calendarBody = document.querySelector('#view-calendar tbody');
    if (calendarBody) {
        calendarBody.innerHTML = '';
        if (!state.news_calendar || state.news_calendar.length === 0) {
            calendarBody.innerHTML = `<tr><td colspan="5" class="empty-state">No upcoming economic events scheduled.</td></tr>`;
        } else {
            state.news_calendar.forEach(news => {
                let badgeStyle = "background: rgba(255, 255, 255, 0.1); color: #fff;";
                if (news.impact === "HIGH") badgeStyle = "background: rgba(255, 51, 102, 0.1); color: #ff3366;";
                else if (news.impact === "MEDIUM") badgeStyle = "background: rgba(255, 153, 0, 0.1); color: #ff9900;";
                else if (news.impact === "LOW") badgeStyle = "background: rgba(0, 204, 255, 0.1); color: #00ccff;";
                
                calendarBody.innerHTML += `
                    <tr>
                        <td>${news.date}</td>
                        <td>${news.time}</td>
                        <td><strong>${news.currency}</strong></td>
                        <td><span class="badge" style="${badgeStyle}">${news.impact}</span></td>
                        <td>${news.title}</td>
                    </tr>
                `;
            });
        }
    }

    // Top Row: Chart & Loss Analysis
    const currentBal = balance + totalPnl;
    const balElem = document.getElementById('valBalance');
    if (balElem && !balElem.dataset.animated) {
        animateValue(balElem, 0, currentBal, 2000, true);
        balElem.dataset.animated = "true";
    } else if (balElem) {
        balElem.textContent = `$${currentBal.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    }

    const valEqElem = document.getElementById('valEquity');
    if (valEqElem && !valEqElem.dataset.animated) {
        animateValue(valEqElem, 0, equity, 2000, true);
        valEqElem.dataset.animated = "true";
    } else if (valEqElem) {
        valEqElem.textContent = `$${equity.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    }

    // Update Bot Status Badge
    const statusBadge = document.getElementById('botStatusBadge');
    if (statusBadge && state.bot_status) {
        statusBadge.textContent = state.bot_status;
        if (state.bot_status.includes("ACTIVE")) {
            statusBadge.style = "background: rgba(0, 255, 0, 0.1); color: #00ff00; padding: 6px 12px; font-size: 0.8rem; margin-right: 15px;";
        } else if (state.bot_status.includes("SLEEPING")) {
            statusBadge.style = "background: rgba(255, 153, 0, 0.1); color: #ff9900; padding: 6px 12px; font-size: 0.8rem; margin-right: 15px;";
        } else if (state.bot_status.includes("EMBARGO")) {
            statusBadge.style = "background: rgba(255, 51, 102, 0.1); color: #ff3366; padding: 6px 12px; font-size: 0.8rem; margin-right: 15px;";
        }
    }
    
    // Hardcoded Loss Analysis Limits for demo matching E8
    const totalDdLimit = balance * 0.10; // 10%
    const dailyDdLimit = balance * 0.05; // 5%
    
    let peakBal = balance;
    let maxDrawdown = 0;
    let runningBal = balance;
    journal.forEach(t => {
        runningBal += t.pnl;
        if (runningBal > peakBal) peakBal = runningBal;
        let dd = peakBal - runningBal;
        if (dd > maxDrawdown) maxDrawdown = dd;
    });
    
    document.getElementById('valTotalDdLimit').textContent = `$${totalDdLimit.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    document.getElementById('valTotalDdCurrent').textContent = `$${maxDrawdown.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    
    let totalDdPct = (maxDrawdown / totalDdLimit) * 100;
    if (totalDdPct > 100) totalDdPct = 100;
    document.getElementById('totalDdFill').style.width = `${totalDdPct}%`;

    // (Assuming daily DD is just a fraction of total for UI placeholder)
    let dailyDrawdown = maxDrawdown * 0.4; 
    document.getElementById('valDailyDdLimit').textContent = `$${dailyDdLimit.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    document.getElementById('valDailyDdCurrent').textContent = `$${dailyDrawdown.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    let dailyDdPct = (dailyDrawdown / dailyDdLimit) * 100;
    document.getElementById('dailyDdFill').style.width = `${dailyDdPct}%`;

    const winValElem = document.getElementById('valAvgWin');
    const lossValElem = document.getElementById('valAvgLoss');
    if (winValElem) animateValue(winValElem, 0, (totalWins > 0 ? totalWinAmt/totalWins : 0), 1500, true);
    if (lossValElem) animateValue(lossValElem, 0, (totalLosses > 0 ? Math.abs(totalLossAmt)/totalLosses : 0), 1500, true);
    
    // Middle Row: Stats
    const avgWin = totalWins > 0 ? (totalWinAmt / totalWins) : 0;
    const avgLoss = totalLosses > 0 ? (totalLossAmt / totalLosses) : 0;
    const winRatio = journal.length > 0 ? ((totalWins / journal.length) * 100) : 0;
    const sniperWR = sniperTotal > 0 ? ((sniperWins / sniperTotal) * 100) : 0;
    const asianWR = asianTotal > 0 ? ((asianWins / asianTotal) * 100) : 0;
    
    document.getElementById('valAvgWin').textContent = `$${avgWin.toFixed(2)}`;
    document.getElementById('valAvgLoss').textContent = `-$${avgLoss.toFixed(2)}`;
    document.getElementById('valWinRatio').textContent = `${winRatio.toFixed(0)}%`;
    document.getElementById('valSniperWR').textContent = `${sniperWR.toFixed(0)}%`;
    document.getElementById('valAsianWR').textContent = `${asianWR.toFixed(0)}%`;
    
    const pnlSign = totalPnl >= 0 ? '+' : '';
    const valTotalPnl = document.getElementById('valTotalPnl');
    valTotalPnl.textContent = `${pnlSign}$${Math.abs(totalPnl).toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    valTotalPnl.className = `stat-value ${totalPnl >= 0 ? 'highlight-cyan' : 'loss-val'}`;

    let bestPair = '--', maxPairPnl = -Infinity;
    for (const [pair, amt] of Object.entries(pairPnl)) {
        if (amt > maxPairPnl) { maxPairPnl = amt; bestPair = pair; }
    }
    document.getElementById('valBestPair').textContent = `Best Pair: ${bestPair !== '--' ? `${bestPair} (+$${maxPairPnl.toFixed(0)})` : '--'}`;

    // Bottom Row: Goals
    document.getElementById('goalMaxTrades').textContent = config.max_daily_trades || 6;
    document.getElementById('goalCurrentTrades').textContent = state.daily_trades_count || 0;
    
    const targetAmt = balance * ((config.profit_target_pct || 10) / 100);
    document.getElementById('goalTarget').textContent = `$${targetAmt.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    document.getElementById('goalCurrent').textContent = `$${Math.max(0, totalPnl).toLocaleString(undefined, {minimumFractionDigits: 2})}`;

    // Target Check Logic
    const phaseBadge = document.getElementById('goalPhase');
    if (totalPnl >= targetAmt && targetAmt > 0) {
        phaseBadge.textContent = "PASSED";
        phaseBadge.style.background = "rgba(0, 229, 255, 0.2)";
        phaseBadge.style.color = "#00e5ff";
        phaseBadge.style.border = "1px solid #00e5ff";
        phaseBadge.style.animation = "pulse 1.5s infinite";
        // Also update the center text
        phaseBadge.parentElement.nextElementSibling.querySelector('.goal-val').textContent = "EVALUATION PASSED";
        phaseBadge.parentElement.nextElementSibling.querySelector('.goal-val').style.color = "#00e5ff";
    } else {
        phaseBadge.textContent = config.phase || "LIVE";
        phaseBadge.style.animation = "none";
    }

    // Active Trades
    const active = state.managed_positions || {};
    const activeIds = Object.keys(active);
    document.getElementById('activeCount').textContent = activeIds.length;
    const activeBody = document.getElementById('activeTradesBody');
    if (activeIds.length === 0) {
        activeBody.innerHTML = `<tr><td colspan="6" class="empty-state">No active positions.</td></tr>`;
    } else {
        activeBody.innerHTML = '';
        activeIds.forEach(id => {
            const t = active[id];
            const dir = t.direction === 1 ? 'LONG' : 'SHORT';
            const dirCls = t.direction === 1 ? 'pnl-pos' : 'pnl-neg';
            const strategyBadge = t.strategy === "ASIAN" ? 
                `<span class="badge" style="background: rgba(16, 185, 129, 0.1); color: #10B981;">ASIAN</span>` : 
                `<span class="badge" style="background: rgba(139, 92, 246, 0.1); color: #8B5CF6;">SNIPER</span>`;

            activeBody.innerHTML += `
                <tr>
                    <td><strong>${t.pair}</strong></td>
                    <td>${strategyBadge}</td>
                    <td class="${dirCls}">${dir}</td>
                    <td>${t.entry_price.toFixed(5)}</td>
                    <td>${t.original_lots}</td>
                    <td><span class="badge passed">Open</span></td>
                </tr>
            `;
        });
    }

    // News Calendar
    const newsCalendar = state.news_calendar || [];
    document.getElementById('newsCount').textContent = newsCalendar.length;
    const newsBody = document.getElementById('newsCalendarBody');
    const fullNewsBody = document.getElementById('fullNewsCalendarBody');
    
    if (newsCalendar.length === 0) {
        if(newsBody) newsBody.innerHTML = `<tr><td colspan="5" class="empty-state">No upcoming high-impact news.</td></tr>`;
        if(fullNewsBody) fullNewsBody.innerHTML = `<tr><td colspan="5" class="empty-state">No upcoming economic events scheduled.</td></tr>`;
    } else {
        if(newsBody) newsBody.innerHTML = '';
        if(fullNewsBody) fullNewsBody.innerHTML = '';
        
        newsCalendar.forEach(ev => {
            const impactCls = ev.impact === 'HIGH' ? 'pnl-neg' : 'highlight';
            const rowHTML = `
                <tr>
                    <td>${ev.date}</td>
                    <td><strong>${ev.time}</strong></td>
                    <td>${ev.currency}</td>
                    <td><span class="badge" style="background: ${ev.impact === 'HIGH' ? 'rgba(255, 51, 102, 0.1)' : 'rgba(0, 229, 255, 0.1)'}; color: ${ev.impact === 'HIGH' ? '#ff3366' : '#00e5ff'};">${ev.impact}</span></td>
                    <td>${ev.title}</td>
                </tr>
            `;
            if(newsBody) newsBody.innerHTML += rowHTML;
            if(fullNewsBody) fullNewsBody.innerHTML += rowHTML;
        });
    }

    // Chart Update
    updateChart(journal);
    
    // Manage Chart Loading Overlay
    const hasChartData = journal.length > 0;
    const overlay = document.getElementById('chartOverlay');
    if (overlay && hasChartData) {
        overlay.classList.add('hidden');
    } else if (overlay && !hasChartData) {
        overlay.classList.remove('hidden');
    }
}

function initChart() {
    const ctx = document.getElementById('equityChart').getContext('2d');
    
    // Create Cyan Gradient Fill
    let gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(0, 229, 255, 0.3)');
    gradient.addColorStop(1, 'rgba(0, 229, 255, 0.0)');

    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Realized P&L',
                data: [],
                borderColor: '#00e5ff',
                backgroundColor: gradient,
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 6,
                pointHoverBackgroundColor: '#00e5ff',
                pointHoverBorderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { 
                    display: true, 
                    grid: { display: false },
                    ticks: { color: '#8A8D93', maxTicksLimit: 6 }
                },
                y: { 
                    display: true,
                    grid: { color: 'rgba(255,255,255,0.02)', drawBorder: false },
                    ticks: { color: '#8A8D93' }
                }
            }
        }
    });
}

function updateChart(journal) {
    if (!equityChart) return;
    
    let cumPnl = 0;
    const data = [0];
    const labels = ['00:00'];

    journal.forEach((t, i) => {
        cumPnl += (t.pnl || 0);
        data.push(cumPnl);
        let d = new Date(t.exit_time);
        labels.push(d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
    });

    // If negative, switch to Crimson Red
    if (cumPnl < 0) {
        equityChart.data.datasets[0].borderColor = '#ff3366';
        let grad = document.getElementById('equityChart').getContext('2d').createLinearGradient(0,0,0,300);
        grad.addColorStop(0, 'rgba(255, 51, 102, 0.3)');
        grad.addColorStop(1, 'rgba(255, 51, 102, 0.0)');
        equityChart.data.datasets[0].backgroundColor = grad;
    } else {
        equityChart.data.datasets[0].borderColor = '#00e5ff';
        let grad = document.getElementById('equityChart').getContext('2d').createLinearGradient(0,0,0,300);
        grad.addColorStop(0, 'rgba(0, 229, 255, 0.3)');
        grad.addColorStop(1, 'rgba(0, 229, 255, 0.0)');
        equityChart.data.datasets[0].backgroundColor = grad;
    }

    equityChart.data.labels = labels;
    equityChart.data.datasets[0].data = data;
    equityChart.update();
}

function initUI() {
    // Nav Items Interactive Toggle & SPA Routing
    const views = {
        'Dashboard': 'view-dashboard',
        'Account Overview': 'view-account',
        'Order List': 'view-orders',
        'Settings': 'view-settings',
        'ML Engine Status': 'view-ml-engine',
        'Economic Calendar': 'view-calendar'
    };
    
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            if(item.classList.contains('toggle-switch') || item.closest('.sidebar-bottom')) return;
            
            // Visual toggle
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            item.classList.add('active');
            
            // SPA Routing
            const text = item.querySelector('span').textContent;
            if (views[text]) {
                document.querySelectorAll('.view-section').forEach(v => v.style.display = 'none');
                document.getElementById(views[text]).style.display = 'block';
            }
        });
    });

    // Chart Time Filters Interactive Toggle
    document.querySelectorAll('.time-filters span').forEach(span => {
        span.addEventListener('click', () => {
            document.querySelectorAll('.time-filters span').forEach(s => s.classList.remove('active'));
            span.classList.add('active');
            // Fake data reload for visual feedback
            const text = span.textContent;
            let mult = text === '1m' ? 1 : text === '15m' ? 1.2 : text === '1h' ? 0.8 : text === '4h' ? 1.5 : 1;
            if(equityChart && equityChart.data.datasets[0].data.length > 1) {
                const newData = equityChart.data.datasets[0].data.map((d, i) => i === 0 ? 0 : d * mult);
                equityChart.data.datasets[0].data = newData;
                equityChart.update();
            }
        });
    });

    // Account Dropdown Toggle
    const accSelector = document.getElementById('accountSelector');
    const accDropdown = document.getElementById('accountDropdown');
    if (accSelector && accDropdown) {
        accSelector.addEventListener('click', (e) => {
            accDropdown.classList.toggle('show');
            e.stopPropagation();
        });
        document.addEventListener('click', (e) => {
            if (!accSelector.contains(e.target)) {
                accDropdown.classList.remove('show');
            }
        });
    }

    // Loss Tabs Interactive Toggle
    document.querySelectorAll('.loss-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.loss-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            // Swap data dynamically
            if (tab.textContent === 'Current') {
                document.getElementById('valTotalDdCurrent').textContent = '$0.00';
                document.getElementById('totalDdFill').style.width = '0%';
            } else {
                // Trigger an immediate data fetch to restore the real "Max" values
                fetchLiveState();
            }
        });
    });

    // Dark Mode / Light Mode Toggle
    const toggle = document.querySelector('.toggle-switch');
    if (toggle) {
        toggle.addEventListener('click', () => {
            toggle.classList.toggle('active');
            document.body.classList.toggle('light-mode');
            
            // Update chart colors based on theme
            if(equityChart) {
                const isLight = document.body.classList.contains('light-mode');
                equityChart.options.scales.x.ticks.color = isLight ? '#64748B' : '#8A8D93';
                equityChart.options.scales.y.ticks.color = isLight ? '#64748B' : '#8A8D93';
                equityChart.options.scales.y.grid.color = isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.02)';
                equityChart.update();
            }
        });
    }
}

window.onload = () => {
    initUI();
    initChart();
    fetchLiveState();
    setInterval(fetchLiveState, 5000);
};
