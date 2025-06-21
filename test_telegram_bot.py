#!/usr/bin/env python3
"""
Test script for Telegram Bot Integration
Use this to verify your bot token and chat ID are working correctly
"""

import os
import sys
from telegram_bot import telegram_client

def test_telegram_setup():
    """Test the Telegram bot configuration"""
    print("🤖 Testing Telegram Bot Setup...")
    print("=" * 50)
    
    # Check if bot is configured
    if not telegram_client.is_configured():
        print("❌ Telegram bot not configured!")
        print("\nMissing environment variables:")
        if not os.getenv('TELEGRAM_BOT_TOKEN'):
            print("  - TELEGRAM_BOT_TOKEN")
        if not os.getenv('TELEGRAM_CHAT_ID'):
            print("  - TELEGRAM_CHAT_ID")
        print("\nPlease set these environment variables and try again.")
        return False
    
    print(f"✅ Bot Token: {'*' * 20}{telegram_client.bot_token[-10:] if telegram_client.bot_token else 'None'}")
    print(f"✅ Chat ID: {telegram_client.chat_id}")
    print()
    
    # Test bot connection
    print("Testing bot connection...")
    if telegram_client.test_connection():
        print("✅ Bot connection successful!")
    else:
        print("❌ Bot connection failed!")
        return False
    
    print()
    
    # Test sending a message
    print("Testing message sending...")
    test_data = {
        'event': 'Test Message',
        'description': 'This is a test message from your MLB GIF Dashboard',
        'away_team': 'TEST',
        'home_team': 'BOT',
        'impact_score': 1.0,
        'inning': '9',
        'half_inning': 'th',
        'batter': 'Test Batter',
        'pitcher': 'Test Pitcher',
        'away_score': 5,
        'home_score': 4,
        'timestamp': '2025-06-20T20:30:00'
    }
    
    if telegram_client.send_gif_notification(test_data):
        print("✅ Test message sent successfully!")
        print("Check your Telegram chat to see the message.")
    else:
        print("❌ Failed to send test message!")
        return False
    
    print()
    print("🎉 All tests passed! Your Telegram bot is ready to use.")
    return True

if __name__ == "__main__":
    success = test_telegram_setup()
    sys.exit(0 if success else 1) 