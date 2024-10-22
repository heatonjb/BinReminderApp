// Phone number validation
function validatePhoneNumber(phone) {
    const phoneRegex = /^\+?1?\d{10,12}$/;
    return phoneRegex.test(phone.replace(/[-\s()]/g, ''));
}

// Calculate next collection date based on frequency
function calculateNextCollection(frequency, currentDate) {
    const date = new Date(currentDate);
    if (frequency === 'weekly') {
        date.setDate(date.getDate() + 7);
    } else if (frequency === 'biweekly') {
        date.setDate(date.getDate() + 14);
    }
    return date.toISOString().split('T')[0];
}

document.addEventListener('DOMContentLoaded', function() {
    // Phone number validation
    const phoneInput = document.getElementById('phone');
    if (phoneInput) {
        phoneInput.addEventListener('input', function() {
            const isValid = validatePhoneNumber(this.value);
            this.classList.toggle('is-invalid', !isValid);
            const submitBtn = this.closest('form').querySelector('button[type="submit"]');
            submitBtn.disabled = !isValid;
        });
    }

    // Date and frequency handling
    const forms = document.querySelectorAll('form[action="/schedule/update"]');
    forms.forEach(form => {
        const frequencySelect = form.querySelector('select[name="frequency"]');
        const dateInput = form.querySelector('input[type="date"]');
        const binType = form.querySelector('input[name="bin_type"]').value;
        
        // Set initial date if empty
        if (!dateInput.value) {
            dateInput.value = new Date().toISOString().split('T')[0];
        }

        // Add min date constraint
        dateInput.min = new Date().toISOString().split('T')[0];

        // Update next collection preview when frequency changes
        frequencySelect?.addEventListener('change', function() {
            const nextDate = calculateNextCollection(this.value, dateInput.value);
            const previewDiv = form.querySelector('.next-collection-preview') || 
                             document.createElement('div');
            previewDiv.className = 'next-collection-preview alert alert-info mt-2';
            previewDiv.textContent = `Next collection after this will be: ${nextDate}`;
            dateInput.closest('.mb-3').appendChild(previewDiv);
        });

        // Style bin rows in the table
        const binRows = document.querySelectorAll('tbody tr');
        binRows.forEach(row => {
            const type = row.cells[0].textContent.toLowerCase();
            row.classList.add(`bin-${type}`);
        });
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
