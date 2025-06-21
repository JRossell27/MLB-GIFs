#!/usr/bin/env python3
"""
Simple script to get your Telegram Chat ID
Make sure you've sent a message to your bot first!
"""

import requests
import json
import os

def get_chat_id():
    # Get bot token from environment or prompt
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        print("Enter your Telegram Bot Token:")
        bot_token = input().strip()
    
    if not bot_token:
        print("❌ No bot token provided!")
        return
    
    print(f"🤖 Using bot token: ...{bot_token[-10:]}")
    print()
    
    # Get updates from Telegram
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    
    try:
        print("📡 Fetching updates from Telegram...")
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ API request failed: {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        data = response.json()
        
        if not data.get('ok'):
            print(f"❌ Telegram API error: {data.get('description', 'Unknown error')}")
            return
        
        updates = data.get('result', [])
        
        if not updates:
            print("❌ No messages found!")
            print()
            print("Make sure you:")
            print("1. Started a chat with your bot")
            print("2. Sent at least one message to your bot")
            print("3. Your bot token is correct")
            return
        
        print(f"✅ Found {len(updates)} message(s)!")
        print()
        
        # Extract unique chat IDs
        chat_ids = set()
        for update in updates:
            message = update.get('message', {})
            chat = message.get('chat', {})
            chat_id = chat.get('id')
            chat_type = chat.get('type', 'unknown')
            
            if chat_id:
                chat_ids.add((chat_id, chat_type))
                
                # Show details about this chat
                first_name = chat.get('first_name', '')
                last_name = chat.get('last_name', '')
                username = chat.get('username', '')
                title = chat.get('title', '')
                
                print(f"💬 Chat found:")
                print(f"   Chat ID: {chat_id}")
                print(f"   Type: {chat_type}")
                if first_name or last_name:
                    print(f"   Name: {first_name} {last_name}".strip())
                if username:
                    print(f"   Username: @{username}")
                if title:
                    print(f"   Title: {title}")
                print()
        
        if chat_ids:
            print("🎯 CHAT ID(S) TO USE:")
            for chat_id, chat_type in chat_ids:
                print(f"   {chat_id} ({chat_type})")
            
            print()
            print("📝 Set your environment variable:")
            # Use the first chat ID as the example
            example_chat_id = list(chat_ids)[0][0]
            print(f"   export TELEGRAM_CHAT_ID=\"{example_chat_id}\"")
            
        else:
            print("❌ No chat IDs found in messages")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🔍 Telegram Chat ID Finder")
    print("=" * 30)
    get_chat_id() 