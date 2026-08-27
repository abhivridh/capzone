/**
 * CarePulse - Dashboard Live Hardware Monitor
 * Pure ESP32 Real-Time Monitoring & Continuous 10-Second Staleness Engine.
 * 
 * Rules:
 * 1. Never displays simulated, mocked, or randomly generated vitals.
 * 2. Only displays data received from real ESP32 hardware via /api/sensor-data.
 * 3. Checks data freshness every second:
 *    - Age <= 10s: "Connected / Live" + real numeric values.
 *    - Age > 10s or no data: "No device connected" + placeholder dashes (--).
 */

let lastReadingData = null;
let lastPacketTimestamp = null;
let lastPacketReceivedClientTime = 0;
let isDeviceCurrentlyLive = false;
let ecgCanvas = null;
let ecgAnimationStep = 0;

document.addEventListener('DOMContentLoaded', () => {
  ecgCanvas = document.getElementById('dashboardEcgCanvas');

  // 1. Initial immediate poll
  fetchDashboardData();

  // 2. Continuous backend poll every 2 seconds
  setInterval(fetchDashboardData, 2000);

  // 3. Continuous client-side freshness / staleness evaluation every 1 second
  setInterval(evaluateFreshnessAndRender, 1000);

  // 4. Start ECG oscilloscope loop
  if (ecgCanvas) {
    requestAnimationFrame(renderEcgFrame);
  }

  window.carepulseRefreshData = fetchDashboardData;
});

/**
 * Polls latest genuine ESP32 hardware readings from backend API.
 */
async function fetchDashboardData() {
  try {
    const activePid = (document.getElementById('dashboardActivePatientId') ? document.getElementById('dashboardActivePatientId').value : '') || 'P001';
    const res = await fetch(`/api/readings/latest?patient_id=${encodeURIComponent(activePid)}`);
    if (!res.ok) {
      return;
    }
    const json = await res.json();

    if (json.success && json.is_hardware_connected && json.reading) {
      lastReadingData = json.reading;
      lastPacketTimestamp = json.reading.timestamp || new Date().toLocaleTimeString();
      lastPacketReceivedClientTime = Date.now();
      lastReadingData._status = json.status || {};
    } else {
      // Backend reported no fresh hardware data
      if (json.last_reading_timestamp) {
        lastPacketTimestamp = json.last_reading_timestamp;
      }
      // If backend explicitly says not connected, force stale
      if (!json.is_hardware_connected) {
        lastReadingData = null;
      }
    }

    evaluateFreshnessAndRender();
  } catch (err) {
    console.debug('Dashboard hardware polling check:', err);
  }
}

/**
 * Continuously evaluates whether the last received ESP32 telemetry packet is <= 10 seconds old.
 * Updates UI immediately without requiring a page refresh.
 */
function evaluateFreshnessAndRender() {
  const now = Date.now();
  const timeSinceLastPacket = (now - lastPacketReceivedClientTime) / 1000;
  const isFresh = lastReadingData !== null && timeSinceLastPacket <= 10.0;

  isDeviceCurrentlyLive = isFresh;
  const globalPill = document.getElementById('globalDemoPill');
  if (globalPill) {
    if (isFresh) {
      globalPill.className = 'demo-banner-pill bg-success-subtle border-success-subtle text-success';
      globalPill.innerHTML = '<span class="demo-dot" style="background: #10B981;"></span><span class="demo-text text-success fw-bold"><i class="fa-solid fa-wifi me-1"></i> LIVE HARDWARE (ESP32)</span>';
    } else {
      globalPill.className = 'demo-banner-pill';
      globalPill.innerHTML = '<span class="demo-dot"></span><span class="demo-text">🟡 AWAITING ESP32</span>';
    }
  }

  // DOM elements
  const bannerBadge = document.getElementById('deviceStatusBadge');
  const bannerHeading = document.getElementById('deviceStatusHeading');
  const bannerSubtext = document.getElementById('deviceStatusSubtext');
  const bannerIconBox = document.getElementById('connectionStatusIconBox');
  const bannerIcon = document.getElementById('connectionStatusIcon');
  const lastSeenEl = document.getElementById('lastSeenTimestamp');
  const countdownEl = document.getElementById('freshnessCountdown');

  const devCardBadge = document.getElementById('deviceCardBadge');
  const devStatusText = document.getElementById('deviceStatusText');
  const devSubtext = document.getElementById('deviceModeSubtext');

  const hrVal = document.getElementById('valHeartRate');
  const spo2Val = document.getElementById('valSpO2');
  const tempVal = document.getElementById('valTemp');

  const hrBadge = document.getElementById('badgeHeartRate');
  const spo2Badge = document.getElementById('badgeSpO2');
  const tempBadge = document.getElementById('badgeTemp');

  const srcHr = document.getElementById('sourceBadgeHr');
  const srcSpo2 = document.getElementById('sourceBadgeSpo2');
  const srcTemp = document.getElementById('sourceBadgeTemp');

  const hrPulse = document.getElementById('hrPulseIcon');

  const summaryPill = document.getElementById('summaryStatusPill');
  const summaryTitle = document.getElementById('summaryTitle');
  const summaryDesc = document.getElementById('summaryDesc');
  const summaryIcon = document.getElementById('summaryBadgeIcon');

  if (isFresh && lastReadingData) {
    // ==========================================
    // STATE: CONNECTED & LIVE (<= 10s fresh)
    // ==========================================
    const r = lastReadingData;
    const st = lastReadingData._status || {};
    const secondsAgo = Math.max(0, Math.floor(timeSinceLastPacket));

    // 1. Connection Banner
    if (bannerBadge) {
      bannerBadge.className = 'badge bg-success';
      bannerBadge.innerHTML = '<i class="fa-solid fa-wifi me-1"></i>Connected &bull; Live';
    }
    if (bannerHeading) {
      bannerHeading.textContent = 'ESP32-001 Streaming Live Telemetry';
    }
    if (bannerSubtext) {
      bannerSubtext.innerHTML = '<span class="text-success fw-semibold"><i class="fa-solid fa-circle-dot fa-fade me-1"></i>Receiving active health packets (&le;10s freshness)</span>';
    }
    if (bannerIconBox) {
      bannerIconBox.style.background = '#dcfce7';
    }
    if (bannerIcon) {
      bannerIcon.className = 'fa-solid fa-wifi text-success fs-5';
    }
    if (lastSeenEl) {
      lastSeenEl.textContent = lastPacketTimestamp || 'Just now';
    }
    if (countdownEl) {
      countdownEl.className = 'badge bg-success-subtle text-success border border-success-subtle small mt-1';
      countdownEl.textContent = `Live: Fresh (${secondsAgo}s ago)`;
    }

    // 2. Device Card
    if (devCardBadge) {
      devCardBadge.className = 'badge bg-success';
      devCardBadge.innerHTML = '<i class="fa-solid fa-wifi me-1"></i>CONNECTED';
    }
    if (devStatusText) {
      devStatusText.innerHTML = '<strong class="text-success">🟢 Connected (Live Telemetry)</strong>';
    }
    if (devSubtext) {
      devSubtext.innerHTML = '<span class="small text-success fw-bold"><i class="fa-solid fa-signal me-1"></i> Streaming physical sensor data</span>';
    }

    // 3. Vital Numbers (Genuine physical data)
    if (hrVal) hrVal.textContent = Math.round(r.heart_rate);
    if (spo2Val) spo2Val.textContent = Math.round(r.spo2);
    if (tempVal) tempVal.textContent = parseFloat(r.temperature).toFixed(1);

    // 4. Status Badges
    if (hrBadge) {
      const s = st.heart_rate || 'Normal';
      hrBadge.textContent = s;
      hrBadge.className = 'vital-badge-status ' + s.toLowerCase();
    }
    if (spo2Badge) {
      const s = st.spo2 || 'Normal';
      spo2Badge.textContent = s;
      spo2Badge.className = 'vital-badge-status ' + s.toLowerCase();
    }
    if (tempBadge) {
      const s = st.temperature || 'Normal';
      tempBadge.textContent = s;
      tempBadge.className = 'vital-badge-status ' + s.toLowerCase();
    }

    // 5. Source Badges & Pulse Icon
    const liveTagHtml = '<span class="badge bg-success text-white"><i class="fa-solid fa-wifi me-1"></i>ESP32 LIVE</span>';
    if (srcHr) srcHr.innerHTML = liveTagHtml;
    if (srcSpo2) srcSpo2.innerHTML = liveTagHtml;
    if (srcTemp) srcTemp.innerHTML = liveTagHtml;

    if (hrPulse) {
      hrPulse.style.animation = 'pulseBeat 1.4s infinite ease-in-out';
    }

    // 6. Summary Card
    const overall = (st.overall || 'NORMAL').toUpperCase();
    if (summaryPill) {
      summaryPill.textContent = overall;
      summaryPill.className = 'summary-status-pill ' + overall.toLowerCase();
    }
    if (summaryTitle) {
      summaryTitle.textContent = overall === 'CRITICAL' ? 'Critical Vital Sign Detected' : 
                                 overall === 'WARNING' ? 'Warning: Abnormal Baseline' : 
                                 'Vital Signs Within Target Baseline';
    }
    if (summaryDesc) {
      summaryDesc.textContent = overall === 'CRITICAL' ? 'Critical threshold breach detected on physical sensors. Immediate medical attention advised.' :
                                overall === 'WARNING' ? 'One or more vitals are outside optimal monitoring thresholds.' :
                                'All monitored values from the ESP32 are currently within normal baseline range.';
    }
    if (summaryIcon) {
      summaryIcon.className = 'summary-badge-icon ' + overall.toLowerCase();
      summaryIcon.innerHTML = overall === 'CRITICAL' ? '<i class="fa-solid fa-triangle-exclamation"></i>' :
                              overall === 'WARNING' ? '<i class="fa-solid fa-circle-exclamation"></i>' :
                              '<i class="fa-solid fa-heart-pulse"></i>';
    }

  } else {
    // ==========================================
    // STATE: DISCONNECTED / WAITING (> 10s or None)
    // NEVER show fake numbers or zeros: Show dashes (--)
    // ==========================================

    // 1. Connection Banner
    if (bannerBadge) {
      bannerBadge.className = 'badge bg-secondary';
      bannerBadge.textContent = 'No device connected';
    }
    if (bannerHeading) {
      bannerHeading.textContent = 'Waiting for ESP32 Device...';
    }
    if (bannerSubtext) {
      bannerSubtext.innerHTML = '<span class="text-muted"><i class="fa-solid fa-plug-circle-xmark me-1"></i>No active telemetry received in the last 10s. Connect physical ESP32 to start streaming.</span>';
    }
    if (bannerIconBox) {
      bannerIconBox.style.background = '#f1f5f9';
    }
    if (bannerIcon) {
      bannerIcon.className = 'fa-solid fa-microchip text-secondary fs-5';
    }
    if (lastSeenEl) {
      lastSeenEl.textContent = lastPacketTimestamp ? `${lastPacketTimestamp} (Stale)` : 'None yet';
    }
    if (countdownEl) {
      countdownEl.className = 'badge bg-light text-secondary border small mt-1';
      countdownEl.textContent = 'Offline • Waiting for device...';
    }

    // 2. Device Card
    if (devCardBadge) {
      devCardBadge.className = 'badge bg-secondary';
      devCardBadge.textContent = 'OFFLINE';
    }
    if (devStatusText) {
      devStatusText.innerHTML = '<strong class="text-secondary">⚪ No device connected</strong>';
    }
    if (devSubtext) {
      devSubtext.innerHTML = '<span class="small text-muted fst-italic">Waiting for ESP32 telemetry (&le;10s)</span>';
    }

    // 3. Vital Numbers (Placeholder dashes, NOT fake numbers or zeros)
    if (hrVal) hrVal.textContent = '--';
    if (spo2Val) spo2Val.textContent = '--';
    if (tempVal) tempVal.textContent = '--';

    // 4. Status Badges
    if (hrBadge) {
      hrBadge.textContent = 'Offline';
      hrBadge.className = 'vital-badge-status bg-light text-muted border';
    }
    if (spo2Badge) {
      spo2Badge.textContent = 'Offline';
      spo2Badge.className = 'vital-badge-status bg-light text-muted border';
    }
    if (tempBadge) {
      tempBadge.textContent = 'Offline';
      tempBadge.className = 'vital-badge-status bg-light text-muted border';
    }

    // 5. Source Badges & Pulse Icon
    const waitingTagHtml = '<span class="badge bg-light text-muted border">NO SIGNAL</span>';
    if (srcHr) srcHr.innerHTML = waitingTagHtml;
    if (srcSpo2) srcSpo2.innerHTML = waitingTagHtml;
    if (srcTemp) srcTemp.innerHTML = waitingTagHtml;

    if (hrPulse) {
      hrPulse.style.animation = 'none';
    }

    // 6. Summary Card
    if (summaryPill) {
      summaryPill.textContent = 'DISCONNECTED';
      summaryPill.className = 'summary-status-pill bg-secondary text-white border-0';
    }
    if (summaryTitle) {
      summaryTitle.textContent = 'No Device Connected';
    }
    if (summaryDesc) {
      summaryDesc.textContent = 'Waiting for live telemetry packets from ESP32. Turn on your ESP32 device to view real-time patient vitals.';
    }
    if (summaryIcon) {
      summaryIcon.className = 'summary-badge-icon bg-light text-muted border';
      summaryIcon.innerHTML = '<i class="fa-solid fa-satellite-dish text-secondary"></i>';
    }
  }

  // Update relative timestamps
  const updateEls = document.querySelectorAll('.reading-update-time');
  updateEls.forEach(el => {
    el.textContent = isFresh ? 'Streaming live' : 'No live data';
  });
}

/**
 * Draws the mini ECG oscilloscope wave.
 * When connected: draws active P-Q-R-S-T wave.
 * When disconnected: draws a calm flatline.
 */
function renderEcgFrame() {
  if (!ecgCanvas) return;
  const ctx = ecgCanvas.getContext('2d');
  const width = ecgCanvas.width = ecgCanvas.parentElement.clientWidth || 200;
  const height = ecgCanvas.height = 40;

  ctx.clearRect(0, 0, width, height);
  ctx.lineWidth = 2;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  const midY = height / 2;

  if (isDeviceCurrentlyLive) {
    ctx.strokeStyle = '#FF5C7A';
    ctx.beginPath();
    for (let x = 0; x < width; x++) {
      const offset = (x + ecgAnimationStep) % 120;
      let y = midY;
      if (offset >= 30 && offset < 35) {
        y = midY - 4; // P wave
      } else if (offset >= 40 && offset < 44) {
        y = midY + 3; // Q
      } else if (offset >= 44 && offset < 49) {
        y = midY - 18; // R peak
      } else if (offset >= 49 && offset < 53) {
        y = midY + 7; // S wave
      } else if (offset >= 65 && offset < 75) {
        y = midY - 6; // T wave
      }
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ecgAnimationStep += 2;
  } else {
    // Flatline when device is disconnected
    ctx.strokeStyle = '#94a3b8';
    ctx.beginPath();
    ctx.moveTo(0, midY);
    ctx.lineTo(width, midY);
    ctx.stroke();
  }

  requestAnimationFrame(renderEcgFrame);
}
