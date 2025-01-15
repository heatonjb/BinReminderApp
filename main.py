import os
import atexit
from app import app, scheduler, logger

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shut down successfully")

if __name__ == "__main__":
    # Register scheduler shutdown
    atexit.register(shutdown_scheduler)

    # Start the scheduler
    if not scheduler.running:
        scheduler.start()
        logger.info("Notification scheduler started successfully")

    # Use environment port if available, otherwise default to 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)