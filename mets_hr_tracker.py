#!/usr/bin/env python3
"""
Mets Home Run Background Tracker
Integrated with MLB GIF Dashboard - automatically detects and sends Mets HRs to Telegram
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
from dataclasses import dataclass, field
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
        logging.FileHandler('mets_hr_tracker.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class MetsHomeRun:
    """Data structure for a Mets home run"""
    game_pk: int
    play_id: str
    player_name: str
    inning: int
    half_inning: str
    description: str
    exit_velocity: Optional[float] = None
    launch_angle: Optional[float] = None
    hit_distance: Optional[float] = None
    gif_path: Optional[str] = None
    telegram_sent: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    attempts: int = 0
    away_team: str = ""
    home_team: str = ""
    away_score: int = 0
    home_score: int = 0

    def to_dict(self):
        data = {
            'game_pk': self.game_pk,
            'play_id': self.play_id,
            'player_name': self.player_name,
            'inning': self.inning,
            'half_inning': self.half_inning,
            'description': self.description,
            'exit_velocity': self.exit_velocity,
            'launch_angle': self.launch_angle,
            'hit_distance': self.hit_distance,
            'telegram_sent': self.telegram_sent,
            'timestamp': self.timestamp.isoformat(),
            'attempts': self.attempts,
            'away_team': self.away_team,
            'home_team': self.home_team,
            'away_score': self.away_score,
            'home_score': self.home_score
        }
        return data

class MetsHRBackgroundTracker:
    """Background tracker for Mets home runs integrated with the main dashboard"""
    
    def __init__(self):
        self.mets_team_id = 121  # New York Mets team ID
        self.monitoring_active = False
        self.processed_plays: Set[str] = set()
        self.home_run_queue = queue.Queue()
        self.start_time = datetime.now()
        self.keep_alive_url = "https://mlb-gifs.onrender.com/api/ping"
        
        # Statistics
        self.stats = {
            'homeruns_detected_today': 0,
            'gifs_created_today': 0,
            'homeruns_sent_today': 0,
            'last_check': None,
            'processed_plays': 0,
            'api_calls_today': 0,
            'errors_today': 0
        }
        
        # Store recent home runs for the dashboard
        self.recent_home_runs: List[MetsHomeRun] = []
        
        # Initialize GIF generator (using our existing integration)
        try:
            self.gif_integration = BaseballSavantGIFIntegration()
            logger.info("🎬 GIF integration initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize GIF generator: {e}")
            self.gif_integration = None
        
        # Load processed plays from file
        self.load_processed_plays()
        
        logger.info("🏠⚾ Mets HR Background Tracker initialized")
        logger.info(f"📊 Loaded {len(self.processed_plays)} previously processed plays")
    
    def load_processed_plays(self):
        """Load processed plays from pickle file"""
        try:
            if os.path.exists('processed_mets_hrs.pkl'):
                with open('processed_mets_hrs.pkl', 'rb') as f:
                    data = pickle.load(f)
                    if isinstance(data, set):
                        self.processed_plays = data
                    else:
                        # Handle legacy format
                        self.processed_plays = set(data.get('processed_plays', []))
                        self.recent_home_runs = data.get('recent_hrs', [])
                logger.info(f"📂 Loaded {len(self.processed_plays)} processed plays from file")
            else:
                logger.info("📂 No processed plays file found, starting fresh")
        except Exception as e:
            logger.error(f"❌ Error loading processed plays: {e}")
            self.processed_plays = set()
            self.recent_home_runs = []
    
    def save_processed_plays(self):
        """Save processed plays and recent HRs to pickle file"""
        try:
            # Keep only recent plays (last 30 days) to manage memory
            cutoff_date = datetime.now() - timedelta(days=30)
            recent_plays = set()
            
            for play_id in self.processed_plays:
                recent_plays.add(play_id)
            
            # Limit to last 200 plays to avoid memory issues
            if len(recent_plays) > 200:
                recent_plays = set(list(recent_plays)[-200:])
            
            self.processed_plays = recent_plays
            
            # Keep only recent home runs (last 7 days)
            recent_hrs = []
            for hr in self.recent_home_runs:
                if hr.timestamp > cutoff_date:
                    recent_hrs.append(hr)
            
            # Limit to last 50 home runs
            if len(recent_hrs) > 50:
                recent_hrs = recent_hrs[-50:]
            
            self.recent_home_runs = recent_hrs
            
            # Save both processed plays and recent HRs
            data = {
                'processed_plays': list(self.processed_plays),
                'recent_hrs': self.recent_home_runs
            }
            
            with open('processed_mets_hrs.pkl', 'wb') as f:
                pickle.dump(data, f)
            
        except Exception as e:
            logger.error(f"❌ Error saving processed plays: {e}")
    
    def get_live_mets_games(self) -> List[Dict]:
        """Get live/recent Mets games from MLB API"""
        try:
            eastern = pytz.timezone('US/Eastern')
            now_et = datetime.now(eastern)
            
            # Check today and yesterday for games
            today = now_et.strftime('%Y-%m-%d')
            yesterday = (now_et - timedelta(days=1)).strftime('%Y-%m-%d')
            
            all_games = []
            dates_to_check = [today, yesterday]
            
            for date_str in dates_to_check:
                try:
                    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&teamId={self.mets_team_id}"
                    self.stats['api_calls_today'] += 1
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    
                    for date_data in data.get('dates', []):
                        for game in date_data.get('games', []):
                            game['_query_date'] = date_str
                            all_games.append(game)
                            
                except Exception as e:
                    logger.warning(f"⚠️ Error checking games for {date_str}: {e}")
                    continue
            
            if not all_games:
                return []
            
            # Prioritize live games
            live_games = []
            recent_games = []
            
            for game in all_games:
                status_code = game.get('status', {}).get('statusCode', '')
                status_desc = game.get('status', {}).get('detailedState', 'Unknown')
                
                if status_code == 'I':  # Live/In Progress
                    live_games.append(game)
                    logger.info(f"🔴 LIVE METS GAME: {status_desc}")
                elif status_code in ['F', 'FT', 'FR']:  # Recently completed
                    recent_games.append(game)
                    logger.info(f"🟢 COMPLETED METS GAME: {status_desc}")
                elif status_code == 'P':  # Warmup
                    recent_games.append(game)
                    logger.info(f"🟡 WARMUP METS GAME: {status_desc}")
            
            # Return live games first, then recent games
            return live_games + recent_games
            
        except Exception as e:
            logger.error(f"❌ Error fetching Mets games: {e}")
            return []
    
    def get_game_plays(self, game_pk: int) -> List[Dict]:
        """Get all plays for a specific game"""
        try:
            endpoints_to_try = [
                f"https://statsapi.mlb.com/api/v1/game/{game_pk}/playByPlay",
                f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/playByPlay",
                f"https://statsapi.mlb.com/api/v1/game/{game_pk}/feed/live"
            ]
            
            for endpoint in endpoints_to_try:
                try:
                    response = requests.get(endpoint, timeout=15)
                    self.stats['api_calls_today'] += 1
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Try to extract plays from different structures
                        plays = []
                        if 'allPlays' in data:
                            plays = data.get('allPlays', [])
                        elif 'liveData' in data and 'plays' in data['liveData']:
                            plays = data['liveData']['plays'].get('allPlays', [])
                        elif 'plays' in data:
                            plays = data['plays'].get('allPlays', [])
                        
                        if plays:
                            return plays
                            
                except requests.exceptions.RequestException:
                    continue
            
            return []
            
        except Exception as e:
            logger.error(f"❌ Error getting game plays for {game_pk}: {e}")
            return []
    
    def get_player_info(self, player_id: int) -> Dict:
        """Get player information"""
        try:
            url = f"https://statsapi.mlb.com/api/v1/people/{player_id}"
            self.stats['api_calls_today'] += 1
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if 'people' in data and len(data['people']) > 0:
                return data['people'][0]
            
            return {}
            
        except Exception as e:
            logger.error(f"❌ Error getting player info for {player_id}: {e}")
            return {}
    
    def get_enhanced_statcast_data(self, play: Dict, game_pk: int) -> Dict[str, Any]:
        """Get enhanced Statcast data for a play"""
        try:
            # Try to get from play data first
            hit_data = play.get('hitData', {})
            if hit_data:
                return {
                    'exit_velocity': hit_data.get('launchSpeed'),
                    'launch_angle': hit_data.get('launchAngle'),
                    'distance': hit_data.get('totalDistance')
                }
            
            # Fallback to basic data
            return {
                'exit_velocity': None,
                'launch_angle': None,
                'distance': None
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting Statcast data: {e}")
            return {'exit_velocity': None, 'launch_angle': None, 'distance': None}
    
    def is_mets_home_run(self, play: Dict, game_pk: int, game_data: Dict) -> Optional[MetsHomeRun]:
        """Check if a play is a Mets home run"""
        try:
            # Check if it's a home run
            result = play.get('result', {})
            if result.get('event') != 'Home Run':
                return None
            
            # Get batter info
            matchup = play.get('matchup', {})
            batter_id = matchup.get('batter', {}).get('id')
            
            if not batter_id:
                return None
            
            # Check if batter is on the Mets
            player_info = self.get_player_info(batter_id)
            current_team = player_info.get('currentTeam', {})
            
            if current_team.get('id') != self.mets_team_id:
                return None
            
            # Create unique play ID
            about = play.get('about', {})
            inning = about.get('inning', 0)
            half_inning = about.get('halfInning', 'unknown')
            at_bat_index = about.get('atBatIndex', 0)
            play_index = about.get('playIndex', 0)
            play_id = f"mets_hr_{game_pk}_{inning}_{half_inning}_{at_bat_index}_{play_index}"
            
            # Check if already processed
            if play_id in self.processed_plays:
                return None
            
            # Get enhanced Statcast data
            stats = self.get_enhanced_statcast_data(play, game_pk)
            
            # Get game info
            away_team = game_data.get('teams', {}).get('away', {}).get('team', {}).get('abbreviation', 'UNK')
            home_team = game_data.get('teams', {}).get('home', {}).get('team', {}).get('abbreviation', 'UNK')
            away_score = about.get('awayScore', 0)
            home_score = about.get('homeScore', 0)
            
            # Create MetsHomeRun object
            home_run = MetsHomeRun(
                game_pk=game_pk,
                play_id=play_id,
                player_name=player_info.get('fullName', 'Unknown Player'),
                inning=inning,
                half_inning=half_inning,
                description=result.get('description', 'Home run'),
                exit_velocity=stats.get('exit_velocity'),
                launch_angle=stats.get('launch_angle'),
                hit_distance=stats.get('distance'),
                away_team=away_team,
                home_team=home_team,
                away_score=away_score,
                home_score=home_score
            )
            
            logger.info(f"🏠⚾ NEW METS HOME RUN DETECTED!")
            logger.info(f"🎯 Player: {home_run.player_name}")
            logger.info(f"📍 Inning: {inning} ({half_inning})")
            logger.info(f"🏟️ Game: {away_team} @ {home_team} ({away_score}-{home_score})")
            logger.info(f"🚀 Exit Velocity: {stats.get('exit_velocity', 'N/A')} mph")
            logger.info(f"📐 Launch Angle: {stats.get('launch_angle', 'N/A')}°")
            logger.info(f"📏 Distance: {stats.get('distance', 'N/A')} ft")
            
            return home_run
            
        except Exception as e:
            logger.error(f"❌ Error checking if play is Mets home run: {e}")
            return None
    
    def process_home_run_queue(self):
        """Process the home run queue in background"""
        logger.info("🎬 Starting Mets HR processing thread")
        
        while self.monitoring_active:
            try:
                if not self.home_run_queue.empty():
                    home_run = self.home_run_queue.get_nowait()
                    
                    if home_run.attempts >= 3:
                        logger.warning(f"⚠️ Max attempts reached for {home_run.player_name} HR - skipping")
                        continue
                    
                    # Increment attempts
                    home_run.attempts += 1
                    logger.info(f"🔄 Processing {home_run.player_name} HR (attempt {home_run.attempts}/3)")
                    
                    # Try to create GIF
                    gif_path = None
                    if self.gif_integration:
                        try:
                            logger.info(f"🎬 Creating GIF for {home_run.player_name} HR...")
                            
                            # Use our existing integration to create GIF
                            gif_path = self.gif_integration.create_gif_for_play(
                                game_id=home_run.game_pk,
                                play_id=0,  # We'll use 0 as a placeholder
                                game_date=home_run.timestamp.strftime('%Y-%m-%d'),
                                mlb_play_data={
                                    'result': {'event': 'Home Run'},
                                    'about': {'inning': home_run.inning},
                                    'matchup': {'batter': {'fullName': home_run.player_name}}
                                }
                            )
                            
                            if gif_path and os.path.exists(gif_path):
                                home_run.gif_path = gif_path
                                self.stats['gifs_created_today'] += 1
                                logger.info(f"✅ GIF created successfully: {gif_path}")
                            else:
                                logger.warning(f"⚠️ No GIF created for {home_run.player_name} HR")
                                
                        except Exception as e:
                            logger.error(f"❌ Error creating GIF: {e}")
                    
                    # Send to Telegram
                    logger.info(f"📱 Sending {home_run.player_name} HR to Telegram...")
                    
                    # Prepare Telegram data
                    telegram_data = {
                        'event': f'🏠 METS HOME RUN! 🏠',
                        'description': f'{home_run.player_name} - {home_run.description}',
                        'away_team': home_run.away_team,
                        'home_team': home_run.home_team,
                        'impact_score': 1.0,  # Home runs are always high impact
                        'inning': home_run.inning,
                        'half_inning': home_run.half_inning,
                        'batter': home_run.player_name,
                        'pitcher': 'N/A',
                        'away_score': home_run.away_score,
                        'home_score': home_run.home_score,
                        'timestamp': home_run.timestamp.isoformat(),
                        'mets_hr_stats': {
                            'exit_velocity': home_run.exit_velocity,
                            'launch_angle': home_run.launch_angle,
                            'distance': home_run.hit_distance
                        }
                    }
                    
                    success = telegram_client.send_gif_notification(telegram_data, gif_path)
                    
                    if success:
                        home_run.telegram_sent = True
                        self.stats['homeruns_sent_today'] += 1
                        logger.info(f"✅ Successfully sent {home_run.player_name} HR to Telegram!")
                        logger.info(f"🎉 LET'S GO METS! 🧡💙")
                        
                        # Add to recent home runs for dashboard
                        self.recent_home_runs.append(home_run)
                        
                        # Clean up GIF file
                        if gif_path and os.path.exists(gif_path):
                            try:
                                os.remove(gif_path)
                                logger.info(f"🗑️ Cleaned up GIF file: {gif_path}")
                            except Exception as e:
                                logger.error(f"❌ Error removing GIF file: {e}")
                    else:
                        # Requeue with delay if failed
                        if home_run.attempts < 3:
                            logger.warning(f"⚠️ Failed to send {home_run.player_name} HR, requeueing (attempt {home_run.attempts})")
                            time.sleep(30)  # Wait before retry
                            self.home_run_queue.put(home_run)
                        else:
                            logger.error(f"💥 Failed to send {home_run.player_name} HR after 3 attempts")
                
                time.sleep(10)  # Check queue every 10 seconds
                
            except queue.Empty:
                time.sleep(10)
            except Exception as e:
                logger.error(f"❌ Error processing HR queue: {e}")
                time.sleep(30)
    
    def monitor_mets_home_runs(self):
        """Main monitoring loop for Mets home runs"""
        logger.info("🏠⚾ Starting Mets HR Background Tracker - LET'S GO METS!")
        logger.info(f"🔗 Keep-alive URL: {self.keep_alive_url}")
        self.monitoring_active = True
        
        # Start home run processing thread
        hr_thread = threading.Thread(target=self.process_home_run_queue, daemon=True)
        hr_thread.start()
        logger.info("🎬 Started HR processing thread")
        
        cycle_count = 0
        
        try:
            while self.monitoring_active:
                try:
                    cycle_count += 1
                    logger.info(f"🔄 Mets HR monitoring cycle #{cycle_count}")
                    
                    # Get live/recent Mets games
                    games = self.get_live_mets_games()
                    
                    if not games:
                        logger.info("📅 No Mets games found - standing by...")
                    else:
                        logger.info(f"🎯 Found {len(games)} Mets game(s) to monitor for HRs")
                        
                        for game in games:
                            game_pk = game['gamePk']
                            plays = self.get_game_plays(game_pk)
                            
                            if not plays:
                                continue
                            
                            # Check each play for Mets home runs
                            new_hrs_found = 0
                            for play in plays:
                                home_run = self.is_mets_home_run(play, game_pk, game)
                                if home_run:
                                    # Add to processed set
                                    self.processed_plays.add(home_run.play_id)
                                    
                                    # Add to queue for processing
                                    self.home_run_queue.put(home_run)
                                    self.stats['homeruns_detected_today'] += 1
                                    new_hrs_found += 1
                                    
                                    logger.info(f"🎬 Queued {home_run.player_name} HR for processing!")
                            
                            if new_hrs_found == 0:
                                logger.info(f"🔍 Scanned {len(plays)} plays in game {game_pk} - no new Mets HRs")
                    
                    # Update statistics
                    self.stats['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.stats['processed_plays'] = len(self.processed_plays)
                    
                    # Save processed plays
                    self.save_processed_plays()
                    
                    # Log status
                    uptime = str(datetime.now() - self.start_time).split('.')[0]
                    logger.info(f"📊 Mets HR Tracker Status - Uptime: {uptime}")
                    logger.info(f"📊 Today's Stats - HRs Detected: {self.stats['homeruns_detected_today']}, HRs Sent: {self.stats['homeruns_sent_today']}, GIFs: {self.stats['gifs_created_today']}")
                    
                    # Keep-alive ping
                    try:
                        response = requests.get(self.keep_alive_url, timeout=5)
                        if response.status_code == 200:
                            logger.info("💓 Keep-alive ping successful")
                        else:
                            logger.warning(f"⚠️ Keep-alive ping returned status {response.status_code}")
                    except Exception as e:
                        logger.warning(f"⚠️ Keep-alive ping failed: {e}")
                    
                    # Wait 2 minutes before next check
                    logger.info("⏰ Waiting 2 minutes before next Mets HR check...")
                    time.sleep(120)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"💥 Error in Mets HR monitoring loop: {e}")
                    self.stats['errors_today'] += 1
                    time.sleep(60)  # Wait before retry
                    
        except KeyboardInterrupt:
            logger.info("👋 Mets HR monitoring stopped by user")
        finally:
            self.monitoring_active = False
            logger.info("🛑 Mets HR Background Tracker stopped")
    
    def stop_monitoring(self):
        """Stop the monitoring process"""
        self.monitoring_active = False
        logger.info("🛑 Stopping Mets HR Background Tracker...")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current system status"""
        uptime = str(datetime.now() - self.start_time).split('.')[0] if self.monitoring_active else None
        
        return {
            'monitoring': self.monitoring_active,
            'uptime': uptime,
            'last_check': self.stats.get('last_check'),
            'queue_size': self.home_run_queue.qsize(),
            'processed_plays': len(self.processed_plays),
            'recent_home_runs': [hr.to_dict() for hr in self.recent_home_runs[-10:]],  # Last 10 HRs
            'stats': self.stats
        }
    
    def get_recent_home_runs(self, limit: int = 20) -> List[Dict]:
        """Get recent Mets home runs for the dashboard"""
        return [hr.to_dict() for hr in sorted(self.recent_home_runs, key=lambda x: x.timestamp, reverse=True)[:limit]]

# Global tracker instance
mets_hr_tracker = None

def start_mets_hr_tracker():
    """Start the Mets HR background tracker"""
    global mets_hr_tracker
    if mets_hr_tracker is None:
        mets_hr_tracker = MetsHRBackgroundTracker()
        # Start in background thread
        tracker_thread = threading.Thread(target=mets_hr_tracker.monitor_mets_home_runs, daemon=True)
        tracker_thread.start()
        logger.info("🏠 Mets HR Background Tracker started")
    return mets_hr_tracker

def stop_mets_hr_tracker():
    """Stop the Mets HR background tracker"""
    global mets_hr_tracker
    if mets_hr_tracker:
        mets_hr_tracker.stop_monitoring()
        mets_hr_tracker = None
        logger.info("🛑 Mets HR Background Tracker stopped")

def get_mets_hr_tracker():
    """Get the current Mets HR tracker instance"""
    global mets_hr_tracker
    return mets_hr_tracker 