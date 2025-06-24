#!/usr/bin/env python3
"""
Mets Scoring Plays Background Tracker
Automatically detects and creates GIFs for all Mets scoring plays (not just HRs)
Runs in background, sends GIFs via Telegram, includes keep-alive pings
"""

import os
import sys
import time
import json
import logging
import pickle
import requests
import threading
import queue
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Set
import pytz

# Import our existing integrations
from gif_integration import BaseballSavantGIFIntegration
from telegram_bot import telegram_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mets_scoring_tracker.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class MetsScoringPlay:
    """Represents a Mets scoring play with Statcast data"""
    play_id: str
    game_id: int
    game_date: str
    inning: int
    half_inning: str
    batter: str
    pitcher: str
    description: str
    event: str
    runs_scored: int
    rbi_count: int
    home_score: int
    away_score: int
    leverage_index: float
    wpa: float
    timestamp: datetime
    gif_created: bool = False
    gif_processing: bool = False
    
    def to_dict(self):
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

class MetsScoringBackgroundTracker:
    def __init__(self):
        self.monitoring = False
        self.api_base = "https://statsapi.mlb.com/api/v1"
        self.gif_integration = BaseballSavantGIFIntegration()
        
        # Storage for tracking
        self.scoring_plays: List[MetsScoringPlay] = []
        self.processed_plays: Dict[int, Set[str]] = {}  # Game ID -> Set of processed play keys
        self.processing_queue = queue.Queue(maxsize=50)
        
        # Statistics
        self.stats = {
            'plays_detected': 0,
            'gifs_created': 0,
            'notifications_sent': 0,
            'errors': 0,
            'uptime_start': None
        }
        
        # Threads
        self.monitoring_thread = None
        self.processing_thread = None
        
        # Timing
        self.last_check = None
        self.keep_alive_url = "https://mlb-gifs.onrender.com/"
        
        logger.info("✅ Mets Scoring Background Tracker initialized")
    
    def start_monitoring(self):
        """Start the background monitoring thread"""
        if not self.monitoring:
            self.monitoring = True
            self.start_time = datetime.now()
            threading.Thread(target=self._monitoring_loop, daemon=True).start()
            threading.Thread(target=self._processing_loop, daemon=True).start()
            logger.info("🎯 Started Mets scoring plays monitoring")
    
    def stop_monitoring(self):
        """Stop the background monitoring"""
        self.monitoring = False
        logger.info("⏹️ Stopped Mets scoring plays monitoring")
    
    def _monitoring_loop(self):
        """Main monitoring loop - checks every 2 minutes"""
        while self.monitoring:
            try:
                self._check_mets_games_for_scoring_plays()
                self._send_keep_alive_ping()
                self.last_check = datetime.now()
                logger.info("⏰ Waiting 2 minutes before next Mets scoring check...")
                time.sleep(120)
            except Exception as e:
                logger.error(f"Error in Mets scoring monitoring loop: {e}")
                self.stats['errors'] += 1
                time.sleep(30)  # Wait 30 seconds before retrying
    
    def _processing_loop(self):
        """Process queued scoring plays in background"""
        while self.monitoring:
            try:
                if not self.processing_queue.empty():
                    scoring_play = self.processing_queue.get()
                    self._process_scoring_play(scoring_play)
                else:
                    time.sleep(5)  # Check queue every 5 seconds
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                self.stats['errors'] += 1
                time.sleep(10)
    
    def _check_mets_games_for_scoring_plays(self):
        """Check all Mets games for new scoring plays"""
        try:
            # Get current date for game lookup
            current_date = self._get_current_date()
            
            # Get all games for current date
            url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={current_date}&hydrate=game(content(editorial(recap))),linescore,team,person"
            response = requests.get(url, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"Failed to get MLB schedule: {response.status_code}")
                return
            
            data = response.json()
            games = data.get('dates', [{}])[0].get('games', [])
            
            # Filter for Mets games
            mets_games = []
            for game in games:
                home_team = game.get('teams', {}).get('home', {}).get('team', {})
                away_team = game.get('teams', {}).get('away', {}).get('team', {})
                
                if (home_team.get('id') == 121 or away_team.get('id') == 121):  # 121 = Mets
                    mets_games.append(game)
            
            logger.info(f"Found {len(mets_games)} Mets games on {current_date}")
            
            for game in mets_games:
                game_id = game['gamePk']
                game_state = game.get('status', {}).get('detailedState', '')
                
                # Skip games that haven't started
                if game_state in ['Scheduled', 'Pre-Game', 'Warmup']:
                    continue
                
                logger.info(f"Checking Mets game {game_id} ({game_state})")
                
                try:
                    # Get detailed play-by-play data
                    play_url = f"https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live"
                    play_response = requests.get(play_url, timeout=15)
                    
                    if play_response.status_code != 200:
                        logger.warning(f"Failed to get play data for game {game_id}")
                        continue
                    
                    play_data = play_response.json()
                    all_plays = play_data.get('liveData', {}).get('plays', {}).get('allPlays', [])
                    
                    # Create unique game+play key for tracking
                    if game_id not in self.processed_plays:
                        self.processed_plays[game_id] = set()
                    
                    new_scoring_plays = []
                    
                    for play in all_plays:
                        about = play.get('about', {})
                        play_key = f"{about.get('atBatIndex', 0)}_{about.get('playIndex', 0)}"
                        
                        # Skip if we've already processed this play
                        if play_key in self.processed_plays[game_id]:
                            continue
                        
                        # Check if this is a Mets scoring play
                        scoring_play = self._check_if_mets_scoring_play(play, play_data.get('gameData', {}))
                        
                        if scoring_play:
                            # Mark as processed BEFORE adding to queue to avoid duplicates
                            self.processed_plays[game_id].add(play_key)
                            
                            # Check if we've already processed this exact scoring play
                            duplicate_found = False
                            for existing_play in self.scoring_plays:
                                if (existing_play.game_id == scoring_play.game_id and 
                                    existing_play.play_id == scoring_play.play_id):
                                    duplicate_found = True
                                    break
                            
                            if not duplicate_found:
                                new_scoring_plays.append(scoring_play)
                                self.scoring_plays.append(scoring_play)
                                self.stats['plays_detected'] += 1
                                
                                # Keep only recent 50 plays
                                if len(self.scoring_plays) > 50:
                                    self.scoring_plays.pop(0)
                                
                                logger.info(f"🎉 NEW Mets scoring play: {scoring_play.event} by {scoring_play.batter}")
                        else:
                            # Mark non-scoring plays as processed too
                            self.processed_plays[game_id].add(play_key)
                    
                    # Process new scoring plays
                    for scoring_play in new_scoring_plays:
                        if not self.processing_queue.full():
                            self.processing_queue.put(scoring_play)
                            logger.info(f"✅ Added scoring play to processing queue: {scoring_play.event}")
                        else:
                            logger.warning("GIF processing queue is full!")
                
                except Exception as e:
                    logger.error(f"Error processing Mets game {game_id}: {e}")
                    continue
                
        except Exception as e:
            logger.error(f"Error checking Mets games: {e}")
            self.stats['errors'] += 1
    
    def _get_current_date(self):
        """Get the current date in the format YYYY-MM-DD"""
        eastern = pytz.timezone('US/Eastern')
        return datetime.now(eastern).strftime('%Y-%m-%d')
    
    def _process_scoring_play(self, scoring_play: MetsScoringPlay):
        """Process a Mets scoring play - create GIF and send notification"""
        try:
            logger.info(f"🎬 Processing Mets scoring play: {scoring_play.event}")
            
            # Mark as processing
            scoring_play.gif_processing = True
            
            # Create GIF
            gif_path = self._create_gif_for_scoring_play(scoring_play)
            
            if gif_path and os.path.exists(gif_path):
                # Send to Telegram
                success = self._send_telegram_notification(scoring_play, gif_path)
                
                # Clean up GIF file
                try:
                    os.remove(gif_path)
                except:
                    pass
                
                if success:
                    scoring_play.gif_created = True
                    scoring_play.gif_processing = False
                    self.stats['gifs_created'] += 1
                    self.stats['notifications_sent'] += 1
                    logger.info(f"✅ Mets scoring play GIF sent successfully!")
                else:
                    scoring_play.gif_processing = False
                    logger.error(f"❌ Failed to send Mets scoring play GIF")
            else:
                scoring_play.gif_processing = False
                logger.warning(f"⚠️ No video available for Mets scoring play")
                
        except Exception as e:
            logger.error(f"Error processing Mets scoring play: {e}")
            scoring_play.gif_processing = False
            self.stats['errors'] += 1
    
    def _create_gif_for_scoring_play(self, scoring_play: MetsScoringPlay) -> Optional[str]:
        """Create GIF for the scoring play"""
        try:
            return self.gif_integration.create_gif_for_play(
                game_id=scoring_play.game_id,
                play_id=int(scoring_play.play_id.split('_')[1]),
                game_date=scoring_play.game_date,
                mlb_play_data={
                    'result': {'event': scoring_play.event},
                    'about': {'inning': scoring_play.inning},
                    'matchup': {'batter': {'fullName': scoring_play.batter}}
                }
            )
        except Exception as e:
            logger.error(f"Error creating GIF for scoring play: {e}")
            return None
    
    def _send_telegram_notification(self, scoring_play: MetsScoringPlay, gif_path: str) -> bool:
        """Send Telegram notification with GIF"""
        try:
            telegram_data = {
                'event': f"METS SCORE! {scoring_play.event}",
                'description': f"{scoring_play.batter}: {scoring_play.description} ({scoring_play.runs_scored} runs, {scoring_play.rbi_count} RBI)",
                'away_team': 'Various',
                'home_team': 'NYM',
                'impact_score': 1.0,  # Scoring plays are always high impact
                'inning': scoring_play.inning,
                'half_inning': scoring_play.half_inning,
                'batter': scoring_play.batter,
                'pitcher': scoring_play.pitcher,
                'away_score': scoring_play.away_score,
                'home_score': scoring_play.home_score,
                'timestamp': scoring_play.timestamp.isoformat(),
                'runs_scored': scoring_play.runs_scored,
                'rbi_count': scoring_play.rbi_count
            }
            
            return telegram_client.send_gif_notification(telegram_data, gif_path)
            
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            return False
    
    def _send_keep_alive_ping(self):
        """Send keep-alive ping to prevent Render sleeping"""
        try:
            response = requests.get(self.keep_alive_url, timeout=10)
            if response.status_code == 200:
                logger.info("💓 Keep-alive ping successful")
            else:
                logger.warning(f"Keep-alive ping returned {response.status_code}")
        except Exception as e:
            logger.warning(f"Keep-alive ping failed: {e}")
    
    def get_status(self) -> Dict:
        """Get current tracker status"""
        uptime = None
        if self.start_time:
            uptime_delta = datetime.now() - self.start_time
            uptime = str(uptime_delta).split('.')[0]  # Remove microseconds
        
        recent_plays = self.get_recent_scoring_plays(10)
        
        return {
            'monitoring': self.monitoring,
            'uptime': uptime,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'queue_size': self.processing_queue.qsize(),
            'processed_plays': len(self.processed_plays),
            'recent_scoring_plays': [play.to_dict() for play in recent_plays],
            'stats': self.stats.copy()
        }
    
    def get_recent_scoring_plays(self, limit: int = 20) -> List[MetsScoringPlay]:
        """Get recent Mets scoring plays"""
        # Sort by timestamp (newest first) and limit
        sorted_plays = sorted(self.scoring_plays, key=lambda x: x.timestamp, reverse=True)
        return sorted_plays[:limit]
    
    def cleanup_memory(self):
        """Clean up old plays to prevent memory bloat"""
        if len(self.scoring_plays) > 50:
            # Keep only the most recent plays
            self.scoring_plays = sorted(self.scoring_plays, key=lambda x: x.timestamp, reverse=True)[:50]
            logger.info(f"🧹 Cleaned up old scoring plays, kept {len(self.scoring_plays)} recent ones")

# Global tracker instance
_mets_scoring_tracker = None

def start_mets_scoring_tracker():
    """Start the Mets scoring plays background tracker"""
    global _mets_scoring_tracker
    if _mets_scoring_tracker is None:
        _mets_scoring_tracker = MetsScoringBackgroundTracker()
    
    if not _mets_scoring_tracker.monitoring:
        _mets_scoring_tracker.start_monitoring()
        logger.info("🎯 Mets scoring plays tracker started successfully")

def get_mets_scoring_tracker() -> Optional[MetsScoringBackgroundTracker]:
    """Get the global Mets scoring plays tracker instance"""
    return _mets_scoring_tracker

def stop_mets_scoring_tracker():
    """Stop the Mets scoring plays background tracker"""
    global _mets_scoring_tracker
    if _mets_scoring_tracker:
        _mets_scoring_tracker.stop_monitoring()
        logger.info("⏹️ Mets scoring plays tracker stopped")

if __name__ == "__main__":
    # Test mode
    logging.basicConfig(level=logging.INFO)
    start_mets_scoring_tracker()
    
    try:
        while True:
            time.sleep(60)
            if _mets_scoring_tracker:
                status = _mets_scoring_tracker.get_status()
                print(f"Status: {status}")
    except KeyboardInterrupt:
        stop_mets_scoring_tracker() 