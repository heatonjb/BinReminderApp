// Set default dates to today for date inputs
document.addEventListener('DOMContentLoaded', function() {
    const dateInputs = document.querySelectorAll('input[type="date"]');
    const today = new Date().toISOString().split('T')[0];
    
    dateInputs.forEach(input => {
        if (!input.value) {
            input.value = today;
        }
    });
    
    // Set frequency select values based on existing data
    const schedules = document.querySelectorAll('tr');
    schedules.forEach(schedule => {
        const binType = schedule.querySelector('td:first-child')?.textContent.toLowerCase();
        const frequency = schedule.querySelector('td:last-child')?.textContent.toLowerCase();
        
        if (binType && frequency) {
            const select = document.querySelector(`input[value="${binType}"]`)
                ?.closest('form')
                ?.querySelector('select');
            if (select) {
                select.value = frequency;
            }
        }
    });
});
