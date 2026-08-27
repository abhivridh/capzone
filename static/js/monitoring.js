/**
 * CarePulse - Live Monitoring Page Script
 * Pure ESP32 Real-Time Monitoring & Continuous 10-Second Staleness Engine.
 */

let liveHrChart = null;
let liveSpo2Chart = null;
let liveTempChart = null;
let lastMonitoringPacketTime = 0;
let lastMonitoringReading = null;
let isMonitoringLive = false;
let oscCanvas = null;

document.addEventListener('DOMContentLoaded', () => {
  initLiveMonitoring();
});

function initLiveMonitoring() {
  const hrCanvas = document.getElementById('liveHrChart');
  const spo2Canvas = document.getElementById('liveSpo2Chart');
  const tempCanvas = document.getElementById('liveTempChart');
  oscCanvas = document.getElementById('ecgOscilloscope');

  // Chart configs
  if (hrCanvas) {
    liveHrChart = createLiveLineChart(hrCanvas, 'Heart Rate (BPM)', '#FF5C7A', 'rgba(255, 92, 122, 0.12)', 50, 140);
  }
  if (spo2Canvas) {
    liveSpo2Chart = createLiveLineChart(spo2Canvas, 'SpO2 (%)', '#17B6C4', 'rgba(23, 182, 196, 0.12)', 85, 100);
  }
  if (tempCanvas) {
    liveTempChart = createLiveLineChart(tempCanvas, 'Temperature (°C)', '#E08E24', 'rgba(224, 142, 36, 0.12)', 35.0, 40.0);
  }

  // Start oscilloscope
  if (oscCanvas) {
    startHighResEcg(oscCanvas);
  }

  // Polling loop every 2 seconds
  fetchLiveMonitoringData();
  setInterval(fetchLiveMonitoringData, 2000);

  // Staleness check every 1 second
  setInterval(evaluateMonitoringFreshness, 1000);

  window.carepulseRefreshData = fetchLiveMonitoringData;
}

function createLiveLineChart(canvas, label, borderColor, backgroundColor, minY, maxY) {
  const ctx = canvas.getContext('2d');
  const initialLabels = Array(15).fill('');
  const initialData = Array(15).fill(null);

  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: initialLabels,
      datasets: [{
        label: label,
        data: initialData,
        borderColor: borderColor,
        backgroundColor: backgroundColor,
        fill: true,
        tension: 0.35,
        borderWidth: 2.5,
        pointRadius: 2,
        pointBackgroundColor: borderColor
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: { display: false },
        y: {
          min: minY,
          max: maxY,
          grid: { color: 'rgba(230, 238, 241, 0.6)' },
          ticks: { font: { size: 10, family: 'Inter' } }
        }
      }
    }
  });
}

async function fetchLiveMonitoringData() {
  try {
    const res = await fetch('/api/readings/latest?patient_id=P001');
    if (!res.ok) return;
    const json = await res.json();

    if (json.success && json.is_hardware_connected && json.reading) {
      lastMonitoringReading = json.reading;
      lastMonitoringReading._status = json.status || {};
      lastMonitoringPacketTime = Date.now();

      // Push into Chart.js only when fresh genuine data is received
      const nowLabel = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      appendDataPoint(liveHrChart, nowLabel, parseFloat(json.reading.heart_rate));
      appendDataPoint(liveSpo2Chart, nowLabel, parseFloat(json.reading.spo2));
      appendDataPoint(liveTempChart, nowLabel, parseFloat(json.reading.temperature));
    } else {
      if (!json.is_hardware_connected) {
        lastMonitoringReading = null;
      }
    }

    evaluateMonitoringFreshness();
  } catch (e) {
    console.debug('Live monitoring poll err:', e);
  }
}

function evaluateMonitoringFreshness() {
  const now = Date.now();
  const timeSince = (now - lastMonitoringPacketTime) / 1000;
  const isFresh = lastMonitoringReading !== null && timeSince <= 10.0;

  isMonitoringLive = isFresh;

  const liveBadge = document.getElementById('monitoringLiveBadge');
  const timerEl = document.getElementById('lastUpdatedTimer');
  const pulseIcon = document.getElementById('livePulseIcon');

  const mHr = document.getElementById('liveMeterHr');
  const mSpo2 = document.getElementById('liveMeterSpo2');
  const mTemp = document.getElementById('liveMeterTemp');

  const bHr = document.getElementById('liveBadgeHr');
  const bSpo2 = document.getElementById('liveBadgeSpo2');
  const bTemp = document.getElementById('liveBadgeTemp');

  if (isFresh && lastMonitoringReading) {
    const r = lastMonitoringReading;
    const st = r._status || {};
    const sec = Math.max(0, Math.floor(timeSince));

    if (liveBadge) {
      liveBadge.className = 'badge bg-success';
      liveBadge.innerHTML = `<i class="fa-solid fa-wifi me-1"></i>Connected &bull; Live (${sec}s ago)`;
    }
    if (timerEl) {
      timerEl.textContent = `Streaming ESP32 telemetry (Updated ${sec}s ago)`;
    }
    if (pulseIcon) {
      pulseIcon.style.animation = 'pulseBeat 1.4s infinite';
    }

    if (mHr) mHr.textContent = Math.round(r.heart_rate);
    if (mSpo2) mSpo2.textContent = Math.round(r.spo2);
    if (mTemp) mTemp.textContent = parseFloat(r.temperature).toFixed(1);

    if (bHr) { bHr.textContent = st.heart_rate || 'Normal'; bHr.className = 'vital-badge-status ' + (st.heart_rate || 'normal').toLowerCase(); }
    if (bSpo2) { bSpo2.textContent = st.spo2 || 'Normal'; bSpo2.className = 'vital-badge-status ' + (st.spo2 || 'normal').toLowerCase(); }
    if (bTemp) { bTemp.textContent = st.temperature || 'Normal'; bTemp.className = 'vital-badge-status ' + (st.temperature || 'normal').toLowerCase(); }
  } else {
    // DISCONNECTED / STALE (> 10s or null)
    // NEVER show fake numbers or zeros: Show dashes (--)
    if (liveBadge) {
      liveBadge.className = 'badge bg-secondary';
      liveBadge.textContent = 'No device connected';
    }
    if (timerEl) {
      timerEl.textContent = 'Status: Waiting for ESP32...';
    }
    if (pulseIcon) {
      pulseIcon.style.animation = 'none';
    }

    if (mHr) mHr.textContent = '--';
    if (mSpo2) mSpo2.textContent = '--';
    if (mTemp) mTemp.textContent = '--';

    if (bHr) { bHr.textContent = 'Offline'; bHr.className = 'vital-badge-status bg-light text-muted border'; }
    if (bSpo2) { bSpo2.textContent = 'Offline'; bSpo2.className = 'vital-badge-status bg-light text-muted border'; }
    if (bTemp) { bTemp.textContent = 'Offline'; bTemp.className = 'vital-badge-status bg-light text-muted border'; }
  }
}

function appendDataPoint(chart, label, value) {
  if (!chart) return;
  const labels = chart.data.labels;
  const dataset = chart.data.datasets[0];

  labels.push(label);
  dataset.data.push(value);

  if (labels.length > 20) {
    labels.shift();
    dataset.data.shift();
  }
  chart.update('none');
}

/**
 * High-resolution hospital ECG oscilloscope canvas with phosphor trail.
 * Flatlines when disconnected.
 */
function startHighResEcg(canvas) {
  const ctx = canvas.getContext('2d');
  let x = 0;
  let prevY = 0;

  function resize() {
    canvas.width = canvas.parentElement.clientWidth || 600;
    canvas.height = 160;
    prevY = canvas.height / 2;
  }
  resize();
  window.addEventListener('resize', resize);

  let stepCount = 0;

  function loop() {
    const w = canvas.width;
    const h = canvas.height;
    const mid = h / 2;

    // Draw fade erase strip ahead of beam
    ctx.fillStyle = 'rgba(6, 58, 82, 0.06)';
    ctx.fillRect(x, 0, 15, h);

    let y = mid;

    if (isMonitoringLive) {
      const phase = stepCount % 90;
      if (phase >= 20 && phase < 26) {
        y = mid - 8; // P wave
      } else if (phase >= 32 && phase < 35) {
        y = mid + 6; // Q
      } else if (phase >= 35 && phase < 40) {
        y = mid - 55; // R peak
      } else if (phase >= 40 && phase < 45) {
        y = mid + 16; // S
      } else if (phase >= 55 && phase < 68) {
        y = mid - 14; // T
      }
    }

    ctx.lineWidth = 2.5;
    ctx.strokeStyle = isMonitoringLive ? '#6FE0E6' : '#64748b';
    ctx.shadowBlur = isMonitoringLive ? 6 : 0;
    ctx.shadowColor = '#17B6C4';

    ctx.beginPath();
    ctx.moveTo(x === 0 ? 0 : x - 2, prevY);
    ctx.lineTo(x, y);
    ctx.stroke();

    prevY = y;
    x += 2;
    stepCount++;

    if (x >= w) {
      x = 0;
      prevY = mid;
    }

    requestAnimationFrame(loop);
  }

  requestAnimationFrame(loop);
}
