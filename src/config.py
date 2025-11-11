import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://paceman.gg/api/ars/liveruns?gameVersion=all&liveOnly=false"
ADMIN_ID = os.getenv("ADMIN_ID")
USERS_FILE_PATH= os.getenv("USERS_FILE_PATH")
POLL_INTERVAL = 5