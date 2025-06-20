#!/usr/bin/env python3
"""
Discord Webhook Integration for Manual GIF Dashboard
Sends GIFs and notifications to Discord
"""

import requests
import logging
from typing import Optional, Dict
import os
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class DiscordWebhook:
    def __init__(self):
        self.webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        
        if not self.webhook_url:
            logger.warning("⚠️  DISCORD_WEBHOOK_URL not set - Discord notifications disabled")
        else:
            logger.info("✅ Discord webhook configured")
    
    def is_configured(self) -> bool:
        """Check if Discord integration is configured"""
        return bool(self.webhook_url)
    
    def send_gif_notification(self, play_data: Dict, gif_path: Optional[str] = None) -> bool:
        """Send a play notification with optional GIF attachment"""
        if not self.is_configured():
            logger.debug("Discord not configured - skipping notification")
            return False
        
        try:
            # Create embed for the play
            embed = {
                "title": f"🎯 {play_data.get('event', 'Baseball Play')}",
                "description": play_data.get('description', ''),
                "color": 0xFF6B35,
                "fields": [
                    {
                        "name": "⚾ Matchup",
                        "value": f"{play_data.get('away_team', 'Away')} @ {play_data.get('home_team', 'Home')}",
                        "inline": True
                    },
                    {
                        "name": "📊 Impact",
                        "value": f"{(play_data.get('impact_score', 0) * 100):.1f}%",
                        "inline": True
                    },
                    {
                        "name": "⏰ Inning",
                        "value": f"{play_data.get('inning', '?')}{play_data.get('half_inning', '')}",
                        "inline": True
                    },
                    {
                        "name": "🏏 Batter",
                        "value": play_data.get('batter', 'Unknown'),
                        "inline": True
                    },
                    {
                        "name": "⚾ Pitcher",
                        "value": play_data.get('pitcher', 'Unknown'),
                        "inline": True
                    },
                    {
                        "name": "📈 Score",
                        "value": f"{play_data.get('away_score', 0)}-{play_data.get('home_score', 0)}",
                        "inline": True
                    }
                ],
                "footer": {
                    "text": "Manual MLB GIF Dashboard"
                },
                "timestamp": datetime.now().isoformat()
            }
            
            payload = {
                "embeds": [embed],
                "username": "MLB GIF Dashboard",
                "avatar_url": "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/Baseball/3D/baseball_3d.png"
            }
            
            # Send with or without GIF
            if gif_path and os.path.exists(gif_path):
                # Send with GIF attachment
                with open(gif_path, 'rb') as gif_file:
                    files = {
                        'file': (f'{play_data.get("event", "play").replace(" ", "_")}.gif', gif_file, 'image/gif')
                    }
                    data = {
                        'payload_json': json.dumps(payload)
                    }
                    
                    response = requests.post(
                        self.webhook_url,
                        data=data,
                        files=files,
                        timeout=30
                    )
            else:
                # Send text-only
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=30
                )
            
            if response.status_code in [200, 204]:
                logger.info("✅ Discord notification sent successfully")
                return True
            else:
                logger.error(f"❌ Discord webhook failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sending Discord notification: {e}")
            return False
    
    def send_status_update(self, status_message: str) -> bool:
        """Send a simple status update to Discord"""
        if not self.is_configured():
            return False
        
        try:
            payload = {
                "content": f"🤖 **System Status**: {status_message}",
                "username": "MLB GIF Dashboard - System"
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=15
            )
            
            return response.status_code == 204
            
        except Exception as e:
            logger.error(f"Error sending status update: {e}")
            return False

# Create global instance
discord_client = DiscordWebhook() 