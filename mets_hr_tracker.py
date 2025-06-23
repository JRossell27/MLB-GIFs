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
        self.api_base = "https://statsapi.mlb.com/api/v1"
        self.gif_integration = BaseballSavantGIFIntegration()
        
        # Tracking state
        self.monitoring = False
        self.start_time = None
        self.last_check = None
        self.processed_plays: Set[str] = set()
        self.scoring_plays: List[MetsScoringPlay] = []
        self.processing_queue = queue.Queue()
        
        # Stats
        self.stats = {
            'plays_detected': 0,
            'gifs_created': 0,
            'notifications_sent': 0,
            'errors': 0
        }
        
        # Keep only recent plays in memory (last 100)
        self.max_plays_memory = 100
        
        # Keep-alive settings
        self.keep_alive_url = "https://mlb-gifs.onrender.com/"
        self.monitor_interval = 120  # 2 minutes
        
        logger.info("✅ Mets Scoring Plays tracker initialized")
    
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
                self._check_for_mets_scoring_plays()
                self._send_keep_alive_ping()
                self.last_check = datetime.now()
                logger.info("⏰ Waiting 2 minutes before next Mets scoring check...")
                time.sleep(self.monitor_interval)
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
    
    def _check_for_mets_scoring_plays(self):
        """Check for new Mets scoring plays"""
        try:
            mets_games = self._get_mets_games_today()
            
            if not mets_games:
                logger.info("📅 No Mets games found for today")
                return
            
            logger.info(f"🔍 Checking {len(mets_games)} Mets games for scoring plays...")
            
            for game in mets_games:
                self._scan_game_for_scoring_plays(game)
                
        except Exception as e:
            logger.error(f"Error checking for Mets scoring plays: {e}")
            self.stats['errors'] += 1
    
    def _get_mets_games_today(self) -> List[Dict]:
        """Get today's Mets games"""
        try:
            eastern = pytz.timezone('US/Eastern')
            today = datetime.now(eastern).strftime('%Y-%m-%d')
            
            # Check if we should use a test date
            test_date = os.environ.get('TEST_DATE')
            if test_date:
                today = test_date
            
            url = f"{self.api_base}/schedule"
            params = {
                'sportId': 1,
                'date': today,
                'teamId': 121,  # Mets team ID
                'hydrate': 'game(content(editorial(recap))),linescore,team'
            }
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            games = []
            
            for date_entry in data.get('dates', []):
                for game in date_entry.get('games', []):
                    # Only include games that are live or completed
                    status_code = game.get('status', {}).get('statusCode')
                    if status_code in ['I', 'F', 'O']:  # In Progress, Final, Official
                        games.append(game)
            
            return games
            
        except Exception as e:
            logger.error(f"Error fetching Mets games: {e}")
            return []
    
    def _scan_game_for_scoring_plays(self, game_data: Dict):
        """Scan a specific game for new Mets scoring plays"""
        try:
            game_id = game_data['gamePk']
            plays_data = self._get_game_plays(game_id)
            
            if not plays_data:
                return
            
            new_plays_count = 0
            
            for play_data in plays_data:
                play_id = f"{game_id}_{play_data.get('atBatIndex', 0)}"
                
                # Skip if already processed
                if play_id in self.processed_plays:
                    continue
                
                # Check if this is a Mets scoring play
                scoring_play = self._check_if_mets_scoring_play(play_data, game_data)
                if scoring_play:
                    logger.info(f"🎯 NEW METS SCORING PLAY: {scoring_play.event} by {scoring_play.batter} ({scoring_play.runs_scored} runs)")
                    
                    # Add to queue for processing
                    self.processing_queue.put(scoring_play)
                    self.scoring_plays.append(scoring_play)
                    self.stats['plays_detected'] += 1
                    new_plays_count += 1
                
                # Mark as processed regardless
                self.processed_plays.add(play_id)
            
            if new_plays_count > 0:
                logger.info(f"🔍 Scanned game {game_id} - found {new_plays_count} new Mets scoring plays")
            else:
                logger.info(f"🔍 Scanned {len(plays_data)} plays in game {game_id} - no new Mets scoring plays")
                
        except Exception as e:
            logger.error(f"Error scanning game for Mets scoring plays: {e}")
            self.stats['errors'] += 1
    
    def _get_game_plays(self, game_id: int) -> List[Dict]:
        """Get all plays for a specific game"""
        try:
            endpoints_to_try = [
                f"https://statsapi.mlb.com/api/v1/game/{game_id}/playByPlay",
                f"https://statsapi.mlb.com/api/v1.1/game/{game_id}/playByPlay",
            ]
            
            for endpoint in endpoints_to_try:
                try:
                    response = requests.get(endpoint, timeout=15)
                    if response.status_code == 200:
                        data = response.json()
                        plays = data.get('allPlays', [])
                        if plays:
                            return plays
                except:
                    continue
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting plays for game {game_id}: {e}")
            return []
    
    def _check_if_mets_scoring_play(self, play_data: Dict, game_data: Dict) -> Optional[MetsScoringPlay]:
        """Check if a play is a Mets scoring play and return MetsScoringPlay object"""
        try:
            result = play_data.get('result', {})
            about = play_data.get('about', {})
            matchup = play_data.get('matchup', {})
            
            # Check if Mets are batting (need to determine based on game data)
            mets_team_id = 121
            home_team_id = game_data.get('teams', {}).get('home', {}).get('team', {}).get('id')
            away_team_id = game_data.get('teams', {}).get('away', {}).get('team', {}).get('id')
            
            # Determine if Mets are batting this half-inning
            mets_batting = False
            half_inning = about.get('halfInning', '')
            
            if mets_team_id == home_team_id and half_inning == 'bottom':
                mets_batting = True
            elif mets_team_id == away_team_id and half_inning == 'top':
                mets_batting = True
            
            if not mets_batting:
                return None
            
            # Check if runs were scored on this play
            runs_scored = result.get('homeScore', 0) - about.get('homeScore', 0) if mets_team_id == home_team_id else result.get('awayScore', 0) - about.get('awayScore', 0)
            
            # If no runs scored, not a scoring play
            if runs_scored <= 0:
                return None
            
            # Get RBI count
            rbi_count = result.get('rbi', 0)
            
            # Create MetsScoringPlay object
            scoring_play = MetsScoringPlay(
                play_id=f"{game_data['gamePk']}_{about.get('atBatIndex', 0)}",
                game_id=game_data['gamePk'],
                game_date=game_data['gameDate'][:10],
                inning=about.get('inning', 0),
                half_inning=half_inning,
                batter=matchup.get('batter', {}).get('fullName', ''),
                pitcher=matchup.get('pitcher', {}).get('fullName', ''),
                description=result.get('description', ''),
                event=result.get('event', ''),
                runs_scored=runs_scored,
                rbi_count=rbi_count,
                home_score=about.get('homeScore', 0),
                away_score=about.get('awayScore', 0),
                leverage_index=play_data.get('leverageIndex', 1.0),
                wpa=play_data.get('winProbabilityAdded', 0.0),
                timestamp=datetime.now()
            )
            
            return scoring_play
            
        except Exception as e:
            logger.error(f"Error checking if Mets scoring play: {e}")
            return None
    
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
        if len(self.scoring_plays) > self.max_plays_memory:
            # Keep only the most recent plays
            self.scoring_plays = sorted(self.scoring_plays, key=lambda x: x.timestamp, reverse=True)[:self.max_plays_memory]
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