/**
 * CarePulse - Alerts Page Script
 * Handles resolving alerts via AJAX and updating UI state dynamically.
 */

document.addEventListener('DOMContentLoaded', () => {
  const resolveButtons = document.querySelectorAll('.btn-resolve-alert');

  resolveButtons.forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const alertId = btn.getAttribute('data-alert-id');
      if (!alertId) return;

      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i> Resolving...';

      try {
        const res = await fetch(`/api/alerts/${alertId}/resolve`, { method: 'PUT' });
        const json = await res.json();
        if (json.success) {
          showCarePulseToast('Alert Resolved', `Alert #${alertId} marked as resolved.`, 'success');

          // Update card UI
          const card = document.getElementById(`alertCard_${alertId}`);
          if (card) {
            card.classList.remove('critical', 'warning');
            card.classList.add('resolved');
            const badge = card.querySelector('.alert-status-badge');
            if (badge) {
              badge.textContent = 'Resolved';
              badge.className = 'badge bg-success alert-status-badge';
            }
          }
          btn.outerHTML = '<span class="text-success small fw-bold"><i class="fa-solid fa-check me-1"></i> Resolved</span>';

          // Update sidebar counter
          const sidebarBadge = document.getElementById('sidebarAlertBadge');
          if (sidebarBadge) {
            const currentCount = parseInt(sidebarBadge.textContent) || 1;
            const newCount = Math.max(0, currentCount - 1);
            if (newCount === 0) {
              sidebarBadge.remove();
            } else {
              sidebarBadge.textContent = newCount;
            }
          }
        }
      } catch (err) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-check me-1"></i> Resolve';
        showCarePulseToast('Error', 'Could not resolve alert.', 'warning');
      }
    });
  });
});
