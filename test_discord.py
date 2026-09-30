#!/usr/bin/env python3
"""
Quick test script to send a Discord notification right now.
Usage: python3 test_discord.py
"""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not DISCORD_WEBHOOK_URL:
    print("Error: DISCORD_WEBHOOK_URL not set in environment")
    exit(1)

payload = {
    "content": "🧪 **Test Notification** — If you see this, your Discord webhook is working!",
    "embeds": [{
        "title": "✅ Webhook Test Successful",
        "description": "The Moodle tracker can now send you notifications.",
        "color": 0x27AE60,
        "fields": [
            {
                "name": "Status",
                "value": "Connected and working",
                "inline": True,
            },
        ]
    }],
}

try:
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    if resp.status_code == 204:
        print("✅ Test notification sent successfully!")
    else:
        print(f"❌ Failed to send notification (status {resp.status_code})")
        print(f"Response: {resp.text}")
        exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)
