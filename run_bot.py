import os
import time
import logging
import subprocess

# Configure logging
logging.basicConfig(level=logging.INFO, filename='bot.log',
                    format='%(asctime)s:%(levelname)s:%(message)s')

def run_vk_bot():
    while True:
        try:
            # Start the vk_bot.py script
            logging.info("Starting vk_bot...")
            subprocess.run(['python', 'vk_bot.py'], check=True)
        except Exception as e:
            logging.error(f"vk_bot crashed with error: {e}")
            logging.info("Restarting vk_bot...")
            time.sleep(5)  # Delay before restart

if __name__ == '__main__':
    run_vk_bot()