import requests
import time

last_seen_worlds = set() 

def fetch_live_runs():
    try:
        resp = requests.get("https://paceman.gg/api/ars/liveruns?gameVersion=all&liveOnly=false")
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print("Error fetching API:", e)
    return []
