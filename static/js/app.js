/**
 * CarePulse - Global JavaScript Utilities
 * Handles sidebar toggling, toast notifications, audio chime, and timestamp formatting.
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Sidebar Toggle for Mobile / Tablet
  const sidebar = document.getElementById('appSidebar');
  const toggleBtn = document.getElementById('sidebarToggleBtn');
  const closeBtn = document.getElementById('sidebarCloseBtn');

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', () => {
      sidebar.classList.toggle('show');
    });
  }

  if (closeBtn && sidebar) {
    closeBtn.addEventListener('click', () => {
      sidebar.classList.remove('show');
    });
  }

  // Close sidebar on click outside on mobile
  document.addEventListener('click', (e) => {
    if (sidebar && sidebar.classList.contains('show')) {
      if (!sidebar.contains(e.target) && (!toggleBtn || !toggleBtn.contains(e.target))) {
        sidebar.classList.remove('show');
      }
    }
  });

  // 2. Relative time updater
  updateRelativeTimestamps();
  setInterval(updateRelativeTimestamps, 10000);
});

/**
 * Creates and displays an interactive Toast notification.
 */
function showCarePulseToast(title, message, type = 'info') {
  const container = document.getElementById('carepulseToastContainer');
  if (!container) return;

  const toastId = 'toast_' + Date.now();
  let bgClass = 'bg-white';
  let iconClass = 'fa-solid fa-circle-info text-primary';
  let borderClass = 'border-primary';

  if (type === 'critical' || type === 'danger') {
    iconClass = 'fa-solid fa-triangle-exclamation text-danger';
    borderClass = 'border-danger border-2';
    playAlertTone();
  } else if (type === 'warning') {
    iconClass = 'fa-solid fa-circle-exclamation text-warning';
    borderClass = 'border-warning';
  } else if (type === 'success') {
    iconClass = 'fa-solid fa-circle-check text-success';
    borderClass = 'border-success';
  }

  const toastHtml = `
    <div id="${toastId}" class="toast show ${bgClass} shadow-lg ${borderClass} mb-2" role="alert" aria-live="assertive" aria-atomic="true">
      <div class="toast-header border-bottom-0 pb-1">
        <i class="${iconClass} me-2 fs-5"></i>
        <strong class="me-auto text-dark">${title}</strong>
        <small class="text-muted">Just now</small>
        <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
      <div class="toast-body pt-0 text-secondary">
        ${message}
      </div>
    </div>
  `;

  container.insertAdjacentHTML('beforeend', toastHtml);
  const toastEl = document.getElementById(toastId);
  if (toastEl) {
    setTimeout(() => {
      toastEl.classList.remove('show');
      setTimeout(() => toastEl.remove(), 300);
    }, 6000);
  }
}

/**
 * Plays a pleasant synthetic alert chime via Web Audio API (no external MP3 needed).
 */
function playAlertTone() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, ctx.currentTime); // A5
    osc.frequency.exponentialRampToValueAtTime(587.33, ctx.currentTime + 0.3); // D5

    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.35);
  } catch (e) {
    // Audio context may be restricted by browser policy before first interaction
  }
}

/**
 * Formats timestamps nicely
 */
function updateRelativeTimestamps() {
  const elements = document.querySelectorAll('[data-timestamp]');
  elements.forEach(el => {
    const ts = el.getAttribute('data-timestamp');
    if (ts) {
      const date = new Date(ts);
      if (!isNaN(date.getTime())) {
        const diffSeconds = Math.floor((Date.now() - date.getTime()) / 1000);
        if (diffSeconds < 5) el.textContent = 'Just now';
        else if (diffSeconds < 60) el.textContent = `${diffSeconds}s ago`;
        else if (diffSeconds < 3600) el.textContent = `${Math.floor(diffSeconds / 60)}m ago`;
        else el.textContent = `${Math.floor(diffSeconds / 3600)}h ago`;
      }
    }
  });
}


// 3. Global Hardware Status Pill Real-Time Synchronizer
async function syncGlobalHardwarePill() {
  const pill = document.getElementById('globalDemoPill');
  if (!pill) return;
  try {
    const res = await fetch('/api/device-status?device_id=ESP32-001');
    if (!res.ok) return;
    const data = await res.json();
    if (data.success && data.is_connected) {
      pill.className = 'demo-banner-pill bg-success-subtle border-success-subtle text-success';
      pill.innerHTML = '<span class="demo-dot" style="background: #10B981;"></span><span class="demo-text text-success fw-bold"><i class="fa-solid fa-wifi me-1"></i> LIVE HARDWARE (ESP32)</span>';
    } else {
      pill.className = 'demo-banner-pill';
      pill.innerHTML = '<span class="demo-dot"></span><span class="demo-text">🟡 AWAITING ESP32</span>';
    }
  } catch (e) {}
}

document.addEventListener('DOMContentLoaded', () => {
  syncGlobalHardwarePill();
  setInterval(syncGlobalHardwarePill, 2000);
});
