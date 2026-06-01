// main.js — students will add JavaScript here as features are built

document.addEventListener('DOMContentLoaded', () => {
    if (window.lucide) {
        lucide.createIcons();
    }

    // Profile date filter — show the custom date inputs only when the
    // "Custom" range is selected. The form remains fully usable with JS off;
    // the server-rendered `hidden` attribute is the no-JS default.
    const range = document.getElementById('filter-range');
    const dates = document.getElementById('filter-dates');
    if (range && dates) {
        const syncDates = () => {
            if (range.value === 'custom') {
                dates.removeAttribute('hidden');
            } else {
                dates.setAttribute('hidden', '');
            }
        };
        range.addEventListener('change', syncDates);
    }
});
