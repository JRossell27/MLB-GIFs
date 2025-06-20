#!/usr/bin/env python3
"""
Manual MLB GIF Dashboard
A comprehensive dashboard for manually selecting plays to convert to GIFs
Updates every 2 minutes with new plays, keeps games for 24 hours, optimized for 512MB RAM
"""

import os
import sys
import time
import json
import logging
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import threading
import signal
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import pytz
from dataclasses import dataclass, asdict
import requests
from pathlib import Path
import tempfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gif_dashboard.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import our local components
from gif_integration import BaseballSavantGIFIntegration
from discord_webhook import discord_client

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

@dataclass
class GamePlay:
    """Represents a single play in a game"""
    play_id: str
    game_id: int
    game_date: str
    game_time: str
    home_team: str
    away_team: str
    inning: int
    half_inning: str
    outs: int
    description: str
    event: str
    batter: str
    pitcher: str
    home_score: int
    away_score: int
    leverage_index: float
    wpa: float
    impact_score: float
    timestamp: datetime
    selected: bool = False
    gif_created: bool = False
    gif_processing: bool = False
    
    def to_dict(self):
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

@dataclass 
class GameInfo:
    """Represents a game with its plays"""
    game_id: int
    game_date: str
    game_time: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    inning: int
    inning_state: str
    game_state: str
    venue: str
    plays: List[GamePlay]
    last_updated: datetime
    
    def to_dict(self):
        data = asdict(self)
        data['plays'] = [play.to_dict() for play in self.plays]
        data['last_updated'] = self.last_updated.isoformat()
        return data

class ManualGIFDashboard:
    def __init__(self):
        self.api_base = "https://statsapi.mlb.com/api/v1.1"
        self.schedule_api_base = "https://statsapi.mlb.com/api/v1"
        self.gif_integration = BaseballSavantGIFIntegration()
        
        # Memory-optimized storage (for 512MB RAM)
        self.games: Dict[int, GameInfo] = {}
        self.processed_plays: Set[str] = set()
        self.max_games = 20  # Limit number of games kept in memory
        self.max_plays_per_game = 50  # Limit plays per game
        
        # Monitoring state
        self.monitoring = False
        self.last_update = None
        self.update_interval = 120  # 2 minutes
        
        # Team info for display
        self.team_names = {
            'LAA': 'Angels', 'HOU': 'Astros', 'OAK': 'Athletics', 'TOR': 'Blue Jays',
            'ATL': 'Braves', 'MIL': 'Brewers', 'STL': 'Cardinals', 'CHC': 'Cubs',
            'ARI': 'Diamondbacks', 'LAD': 'Dodgers', 'SF': 'Giants', 'CLE': 'Guardians',
            'SEA': 'Mariners', 'MIA': 'Marlins', 'NYM': 'Mets', 'WSH': 'Nationals',
            'BAL': 'Orioles', 'SD': 'Padres', 'PHI': 'Phillies', 'PIT': 'Pirates',
            'TEX': 'Rangers', 'TB': 'Rays', 'BOS': 'Red Sox', 'CIN': 'Reds',
            'COL': 'Rockies', 'KC': 'Royals', 'DET': 'Tigers', 'MIN': 'Twins',
            'CWS': 'White Sox', 'NYY': 'Yankees'
        }
        
        # Start monitoring thread
        self.start_monitoring()
    
    def start_monitoring(self):
        """Start the background monitoring thread"""
        if not self.monitoring:
            self.monitoring = True
            threading.Thread(target=self._monitoring_loop, daemon=True).start()
            logger.info("✅ Started game monitoring")
    
    def stop_monitoring(self):
        """Stop the background monitoring"""
        self.monitoring = False
        logger.info("⏹️ Stopped game monitoring")
    
    def _monitoring_loop(self):
        """Main monitoring loop that updates every 2 minutes"""
        while self.monitoring:
            try:
                self.update_games()
                self.cleanup_old_games()
                self.last_update = datetime.now(pytz.timezone('US/Eastern'))
                time.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(30)  # Wait 30 seconds before retrying
    
    def get_today_games(self) -> List[Dict]:
        """Get all games for today (Eastern time)"""
        eastern = pytz.timezone('US/Eastern')
        today = datetime.now(eastern).strftime('%Y-%m-%d')
        
        try:
            url = f"{self.schedule_api_base}/schedule"
            params = {
                'sportId': 1,
                'date': today,
                'hydrate': 'game(content(editorial(recap))),linescore,team,probablePitcher'
            }
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            games = []
            
            for date_entry in data.get('dates', []):
                for game in date_entry.get('games', []):
                    games.append(game)
            
            logger.info(f"Found {len(games)} games for {today}")
            return games
            
        except Exception as e:
            logger.error(f"Error fetching today's games: {e}")
            return []
    
    def get_game_plays(self, game_id: int) -> List[Dict]:
        """Get all plays for a specific game"""
        try:
            url = f"{self.api_base}/game/{game_id}/playByPlay"
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            plays = []
            
            for inning in data.get('allPlays', []):
                plays.append(inning)
            
            return plays
            
        except Exception as e:
            logger.error(f"Error fetching plays for game {game_id}: {e}")
            return []
    
    def calculate_impact_score(self, play: Dict) -> float:
        """Calculate impact score for a play"""
        try:
            # Get WPA if available
            wpa = 0.0
            if 'winProbabilityRemoved' in play:
                wpa = abs(play['winProbabilityRemoved'])
            elif 'winProbabilityAdded' in play:
                wpa = abs(play['winProbabilityAdded'])
            
            # Base score on event type
            event = play.get('result', {}).get('event', '').lower()
            base_score = 0.1
            
            # High impact events
            if 'home run' in event:
                base_score = 0.3
            elif any(hit in event for hit in ['triple', 'double']):
                base_score = 0.25
            elif 'single' in event:
                base_score = 0.15
            elif any(outcome in event for outcome in ['walk', 'hit by pitch']):
                base_score = 0.1
            elif 'strikeout' in event:
                base_score = 0.12
            
            # Leverage multiplier
            leverage = play.get('leverageIndex', 1.0)
            if leverage > 2.0:
                base_score *= 1.5
            elif leverage > 1.5:
                base_score *= 1.2
            
            return min(base_score + wpa, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating impact score: {e}")
            return 0.1
    
    def update_games(self):
        """Update all games with new plays"""
        games_data = self.get_today_games()
        
        for game_data in games_data:
            try:
                game_id = game_data['gamePk']
                
                # Skip if game hasn't started
                if game_data.get('status', {}).get('statusCode') == 'S':
                    continue
                
                # Get plays for this game
                plays_data = self.get_game_plays(game_id)
                
                # Process plays
                plays = []
                for play_data in plays_data:
                    play_id = f"{game_id}_{play_data.get('atBatIndex', 0)}"
                    
                    # Skip if already processed
                    if play_id in self.processed_plays:
                        continue
                    
                    # Create GamePlay object
                    play = self._create_game_play(play_data, game_data)
                    if play:
                        plays.append(play)
                        self.processed_plays.add(play_id)
                
                # Update or create game info
                if game_id in self.games:
                    # Update existing game
                    game_info = self.games[game_id]
                    game_info.plays.extend(plays)
                    # Keep only recent plays to save memory
                    game_info.plays = game_info.plays[-self.max_plays_per_game:]
                    game_info.last_updated = datetime.now()
                else:
                    # Create new game
                    game_info = self._create_game_info(game_data, plays)
                    self.games[game_id] = game_info
                
                # Memory management - keep only max games
                if len(self.games) > self.max_games:
                    oldest_game_id = min(self.games.keys(), 
                                       key=lambda x: self.games[x].last_updated)
                    del self.games[oldest_game_id]
                
            except Exception as e:
                logger.error(f"Error updating game {game_data.get('gamePk')}: {e}")
    
    def _create_game_play(self, play_data: Dict, game_data: Dict) -> Optional[GamePlay]:
        """Create a GamePlay object from MLB API data"""
        try:
            result = play_data.get('result', {})
            about = play_data.get('about', {})
            matchup = play_data.get('matchup', {})
            
            # Skip if no event occurred
            if not result.get('event'):
                return None
            
            impact_score = self.calculate_impact_score(play_data)
            
            play = GamePlay(
                play_id=f"{game_data['gamePk']}_{about.get('atBatIndex', 0)}",
                game_id=game_data['gamePk'],
                game_date=game_data['gameDate'][:10],
                game_time=game_data.get('gameDate', ''),
                home_team=game_data['teams']['home']['team']['abbreviation'],
                away_team=game_data['teams']['away']['team']['abbreviation'],
                inning=about.get('inning', 0),
                half_inning=about.get('halfInning', ''),
                outs=about.get('outs', 0),
                description=result.get('description', ''),
                event=result.get('event', ''),
                batter=matchup.get('batter', {}).get('fullName', ''),
                pitcher=matchup.get('pitcher', {}).get('fullName', ''),
                home_score=about.get('homeScore', 0),
                away_score=about.get('awayScore', 0),
                leverage_index=play_data.get('leverageIndex', 1.0),
                wpa=play_data.get('winProbabilityAdded', 0.0),
                impact_score=impact_score,
                timestamp=datetime.now()
            )
            
            return play
            
        except Exception as e:
            logger.error(f"Error creating GamePlay: {e}")
            return None
    
    def _create_game_info(self, game_data: Dict, plays: List[GamePlay]) -> GameInfo:
        """Create a GameInfo object from MLB API data"""
        linescore = game_data.get('linescore', {})
        status = game_data.get('status', {})
        
        return GameInfo(
            game_id=game_data['gamePk'],
            game_date=game_data['gameDate'][:10],
            game_time=game_data.get('gameDate', ''),
            home_team=game_data['teams']['home']['team']['abbreviation'],
            away_team=game_data['teams']['away']['team']['abbreviation'],
            home_score=linescore.get('teams', {}).get('home', {}).get('runs', 0),
            away_score=linescore.get('teams', {}).get('away', {}).get('runs', 0),
            inning=linescore.get('currentInning', 0),
            inning_state=linescore.get('inningState', ''),
            game_state=status.get('detailedState', ''),
            venue=game_data.get('venue', {}).get('name', ''),
            plays=plays,
            last_updated=datetime.now()
        )
    
    def cleanup_old_games(self):
        """Remove games older than 24 hours"""
        cutoff = datetime.now() - timedelta(hours=24)
        games_to_remove = []
        
        for game_id, game_info in self.games.items():
            if game_info.last_updated < cutoff:
                games_to_remove.append(game_id)
        
        for game_id in games_to_remove:
            del self.games[game_id]
            logger.info(f"Removed old game {game_id}")
    
    def create_gif_for_play(self, play_id: str) -> Dict:
        """Create a GIF for the specified play and send to Discord"""
        try:
            # Find the play
            play = None
            game_info = None
            
            for game in self.games.values():
                for p in game.plays:
                    if p.play_id == play_id:
                        play = p
                        game_info = game
                        break
                if play:
                    break
            
            if not play:
                return {"success": False, "error": "Play not found"}
            
            # Mark as processing
            play.gif_processing = True
            
            # Create GIF using existing integration
            gif_path = self.gif_integration.get_gif_for_play(
                game_id=play.game_id,
                play_id=int(play.play_id.split('_')[1]),
                game_date=play.game_date,
                mlb_play_data={
                    'result': {'event': play.event},
                    'about': {'inning': play.inning},
                    'matchup': {'batter': {'fullName': play.batter}}
                }
            )
            
            if gif_path and os.path.exists(gif_path):
                # Send to Discord
                discord_data = {
                    'event': play.event,
                    'description': play.description,
                    'away_team': play.away_team,
                    'home_team': play.home_team,
                    'impact_score': play.impact_score,
                    'inning': play.inning,
                    'half_inning': play.half_inning,
                    'batter': play.batter,
                    'pitcher': play.pitcher,
                    'timestamp': play.timestamp.isoformat()
                }
                
                success = discord_client.send_gif_notification(discord_data, gif_path)
                
                # Clean up GIF file immediately
                try:
                    os.remove(gif_path)
                except:
                    pass
                
                if success:
                    play.gif_created = True
                    play.gif_processing = False
                    return {"success": True, "message": "GIF created and sent to Discord"}
                else:
                    play.gif_processing = False
                    return {"success": False, "error": "Failed to send to Discord"}
            else:
                play.gif_processing = False
                return {"success": False, "error": "Failed to create GIF"}
                
        except Exception as e:
            logger.error(f"Error creating GIF for play {play_id}: {e}")
            return {"success": False, "error": str(e)}

# Global dashboard instance
dashboard = ManualGIFDashboard()

# Flask routes
@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/games')
def api_games():
    """Get all games with their plays"""
    games_data = []
    for game in dashboard.games.values():
        game_dict = game.to_dict()
        # Sort plays by timestamp (newest first)
        game_dict['plays'].sort(key=lambda x: x['timestamp'], reverse=True)
        games_data.append(game_dict)
    
    # Sort games by last updated
    games_data.sort(key=lambda x: x['last_updated'], reverse=True)
    
    return jsonify({
        'games': games_data,
        'last_update': dashboard.last_update.isoformat() if dashboard.last_update else None,
        'monitoring': dashboard.monitoring
    })

@app.route('/api/create_gif', methods=['POST'])
def api_create_gif():
    """Create a GIF for a specific play"""
    data = request.get_json()
    play_id = data.get('play_id')
    
    if not play_id:
        return jsonify({"success": False, "error": "play_id required"}), 400
    
    result = dashboard.create_gif_for_play(play_id)
    
    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 500

@app.route('/api/status')
def api_status():
    """Get system status"""
    return jsonify({
        'monitoring': dashboard.monitoring,
        'last_update': dashboard.last_update.isoformat() if dashboard.last_update else None,
        'total_games': len(dashboard.games),
        'total_plays': sum(len(game.plays) for game in dashboard.games.values()),
        'discord_configured': discord_client.is_configured()
    })

@app.route('/api/ping')
def api_ping():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'monitoring': dashboard.monitoring
    })

@app.route('/start_monitoring')
def start_monitoring():
    """Start game monitoring"""
    dashboard.start_monitoring()
    flash('Game monitoring started', 'success')
    return redirect(url_for('index'))

@app.route('/stop_monitoring')
def stop_monitoring():
    """Stop game monitoring"""
    dashboard.stop_monitoring()
    flash('Game monitoring stopped', 'warning')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Shutting down dashboard...")
        dashboard.stop_monitoring()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the Flask app
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Manual GIF Dashboard on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug) 