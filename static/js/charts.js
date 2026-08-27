/**
 * CarePulse - Analytics Charts Script
 * Renders high-quality Chart.js interactive historical graphs with gradients.
 */

document.addEventListener('DOMContentLoaded', () => {
  if (typeof window.initialAnalyticsData !== 'undefined') {
    renderAnalyticsCharts(window.initialAnalyticsData);
  }

  // Filter selector change
  const filterSelect = document.getElementById('analyticsTimeRange');
  if (filterSelect) {
    filterSelect.addEventListener('change', async (e) => {
      const val = e.target.value;
      const patientId = document.getElementById('analyticsPatientSelect')?.value || 'P001';
      try {
        const res = await fetch(`/api/readings/history?patient_id=${patientId}&time_filter=${val}&limit=50`);
        const json = await res.json();
        if (json.success) {
          const chrono = json.readings.reverse();
          renderAnalyticsCharts(chrono);
          updateAnalyticsStats(chrono);
        }
      } catch (err) {
        console.error('Failed to reload analytics range:', err);
      }
    });
  }
});

let hrChartInstance = null;
let spo2ChartInstance = null;
let tempChartInstance = null;

function renderAnalyticsCharts(dataPoints) {
  const labels = dataPoints.map(d => {
    const dt = new Date(d.timestamp);
    return isNaN(dt) ? d.timestamp : dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  });

  const hrData = dataPoints.map(d => parseFloat(d.heart_rate));
  const spo2Data = dataPoints.map(d => parseFloat(d.spo2));
  const tempData = dataPoints.map(d => parseFloat(d.temperature));

  // 1. Heart Rate Chart
  const hrCanvas = document.getElementById('analyticsHrChart');
  if (hrCanvas) {
    if (hrChartInstance) hrChartInstance.destroy();
    hrChartInstance = buildChart(hrCanvas, labels, hrData, 'Heart Rate (BPM)', '#FF5C7A', 'rgba(255, 92, 122, 0.15)', 50, 130);
  }

  // 2. SpO2 Chart
  const spo2Canvas = document.getElementById('analyticsSpo2Chart');
  if (spo2Canvas) {
    if (spo2ChartInstance) spo2ChartInstance.destroy();
    spo2ChartInstance = buildChart(spo2Canvas, labels, spo2Data, 'Oxygen Saturation (%)', '#17B6C4', 'rgba(23, 182, 196, 0.15)', 88, 100);
  }

  // 3. Temperature Chart
  const tempCanvas = document.getElementById('analyticsTempChart');
  if (tempCanvas) {
    if (tempChartInstance) tempChartInstance.destroy();
    tempChartInstance = buildChart(tempCanvas, labels, tempData, 'Temperature (°C)', '#0B6E86', 'rgba(11, 110, 134, 0.15)', 35.5, 39.5);
  }
}

function buildChart(canvas, labels, data, label, color, fillColor, minY, maxY) {
  const ctx = canvas.getContext('2d');
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: label,
        data: data,
        borderColor: color,
        backgroundColor: fillColor,
        fill: true,
        tension: 0.35,
        borderWidth: 2.5,
        pointRadius: 3,
        pointHoverRadius: 6,
        pointBackgroundColor: '#ffffff',
        pointBorderColor: color,
        pointBorderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#063A52',
          titleFont: { family: 'Inter', size: 12 },
          bodyFont: { family: 'Inter', size: 13, weight: 'bold' },
          padding: 10,
          cornerRadius: 8
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { family: 'Inter', size: 11 }, maxRotation: 0 }
        },
        y: {
          min: minY,
          max: maxY,
          grid: { color: 'rgba(230, 238, 241, 0.8)' },
          ticks: { font: { family: 'Inter', size: 11 } }
        }
      }
    }
  });
}

function updateAnalyticsStats(readings) {
  if (!readings || readings.length === 0) return;
  const hrs = readings.map(r => parseFloat(r.heart_rate));
  const spo2s = readings.map(r => parseFloat(r.spo2));
  const temps = readings.map(r => parseFloat(r.temperature));

  const setEl = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  setEl('statHrAvg', (hrs.reduce((a, b) => a + b, 0) / hrs.length).toFixed(1));
  setEl('statHrMin', Math.min(...hrs).toFixed(1));
  setEl('statHrMax', Math.max(...hrs).toFixed(1));
  setEl('statHrCurr', hrs[hrs.length - 1].toFixed(1));

  setEl('statSpo2Avg', (spo2s.reduce((a, b) => a + b, 0) / spo2s.length).toFixed(1));
  setEl('statSpo2Min', Math.min(...spo2s).toFixed(1));
  setEl('statSpo2Max', Math.max(...spo2s).toFixed(1));

  setEl('statTempAvg', (temps.reduce((a, b) => a + b, 0) / temps.length).toFixed(1));
  setEl('statTempMin', Math.min(...temps).toFixed(1));
  setEl('statTempMax', Math.max(...temps).toFixed(1));
}
