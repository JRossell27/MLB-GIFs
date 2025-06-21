#!/usr/bin/env python3
"""
Telegram Bot Integration for Manual GIF Dashboard
Sends GIFs and notifications to Telegram
"""

import requests
import logging
from typing import Optional, Dict
import os
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not self.bot_token or not self.chat_id:
            logger.warning("⚠️  TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set - Telegram notifications disabled")
        else:
            logger.info("✅ Telegram bot configured")
            self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    def is_configured(self) -> bool:
        """Check if Telegram integration is configured"""
        return bool(self.bot_token and self.chat_id)
    
    def send_gif_notification(self, play_data: Dict, gif_path: Optional[str] = None) -> bool:
        """Send a play notification with optional GIF attachment"""
        if not self.is_configured():
            logger.debug("Telegram not configured - skipping notification")
            return False
        
        try:
            # Create formatted message for the play
            event = play_data.get('event', 'Baseball Play')
            description = play_data.get('description', '')
            away_team = play_data.get('away_team', 'Away')
            home_team = play_data.get('home_team', 'Home')
            impact_score = (play_data.get('impact_score', 0) * 100)
            inning = play_data.get('inning', '?')
            half_inning = play_data.get('half_inning', '')
            batter = play_data.get('batter', 'Unknown')
            pitcher = play_data.get('pitcher', 'Unknown')
            away_score = play_data.get('away_score', 0)
            home_score = play_data.get('home_score', 0)
            
            # Handle special pitch data
            pitch_details = play_data.get('pitch_details')
            if pitch_details:
                pitch_type = pitch_details.get('pitch_type', 'Unknown')
                velocity = pitch_details.get('velocity', 0)
                count = pitch_details.get('count', '0-0')
                result = pitch_details.get('result', 'Unknown')
                
                message = f"🎯 *{event}*\n\n"
                message += f"📊 *Pitch Details:*\n"
                message += f"• Type: {pitch_type}\n"
                message += f"• Velocity: {velocity} mph\n"
                message += f"• Count: {count}\n"
                message += f"• Result: {result}\n\n"
                message += f"🏏 *Batter:* {batter}\n"
                message += f"⚾ *Pitcher:* {pitcher}\n\n"
                message += f"🤖 *Manual MLB GIF Dashboard*"
            else:
                # Regular play message
                message = f"🎯 *{event}*\n\n"
                if description:
                    message += f"📝 {description}\n\n"
                
                message += f"⚾ *Matchup:* {away_team} @ {home_team}\n"
                message += f"📊 *Impact:* {impact_score:.1f}%\n"
                message += f"⏰ *Inning:* {inning}{half_inning}\n"
                message += f"🏏 *Batter:* {batter}\n"
                message += f"⚾ *Pitcher:* {pitcher}\n"
                message += f"📈 *Score:* {away_score}-{home_score}\n\n"
                message += f"🤖 *Manual MLB GIF Dashboard*"
            
            # Send with or without GIF
            if gif_path and os.path.exists(gif_path):
                # Send GIF with caption
                url = f"{self.base_url}/sendAnimation"
                
                with open(gif_path, 'rb') as gif_file:
                    files = {
                        'animation': gif_file
                    }
                    data = {
                        'chat_id': self.chat_id,
                        'caption': message,
                        'parse_mode': 'Markdown'
                    }
                    
                    response = requests.post(
                        url,
                        data=data,
                        files=files,
                        timeout=60  # Longer timeout for file uploads
                    )
            else:
                # Send text-only message
                url = f"{self.base_url}/sendMessage"
                data = {
                    'chat_id': self.chat_id,
                    'text': message,
                    'parse_mode': 'Markdown'
                }
                
                response = requests.post(
                    url,
                    json=data,
                    timeout=30
                )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    logger.info("✅ Telegram notification sent successfully")
                    return True
                else:
                    logger.error(f"❌ Telegram API error: {result.get('description', 'Unknown error')}")
                    return False
            else:
                logger.error(f"❌ Telegram request failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sending Telegram notification: {e}")
            return False
    
    def send_status_update(self, status_message: str) -> bool:
        """Send a simple status update to Telegram"""
        if not self.is_configured():
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': f"🤖 *System Status:* {status_message}",
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(
                url,
                json=data,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('ok', False)
            return False
            
        except Exception as e:
            logger.error(f"Error sending Telegram status update: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Test the Telegram bot connection"""
        if not self.is_configured():
            return False
        
        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    bot_info = result.get('result', {})
                    logger.info(f"✅ Telegram bot connected: @{bot_info.get('username', 'unknown')}")
                    return True
            
            logger.error(f"❌ Telegram bot connection failed: {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error testing Telegram connection: {e}")
            return False

# Create global instance
telegram_client = TelegramBot() 