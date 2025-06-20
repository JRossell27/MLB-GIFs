#!/usr/bin/env python3
"""
Simplified Baseball Savant GIF Integration for Manual Dashboard
Optimized for 512MB RAM - creates, sends, and deletes GIFs immediately
"""

import os
import time
import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import json
import subprocess
import tempfile
from pathlib import Path
import csv
from io import StringIO
import re

logger = logging.getLogger(__name__)

class BaseballSavantGIFIntegration:
    def __init__(self):
        self.savant_base = "https://baseballsavant.mlb.com"
        self.temp_dir = Path(tempfile.gettempdir()) / "mlb_gifs"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Clean up any existing temp files on startup
        self._cleanup_temp_files()
    
    def _cleanup_temp_files(self):
        """Clean up all temporary files to free memory"""
        try:
            for file_path in self.temp_dir.glob("*"):
                try:
                    file_path.unlink()
                except:
                    pass
        except Exception as e:
            logger.warning(f"Error cleaning temp files: {e}")
    
    def get_gif_for_play(self, game_id: int, play_id: int, game_date: str, mlb_play_data: Dict = None) -> Optional[str]:
        """
        Get GIF for a specific play - optimized for immediate use and deletion
        Returns path to GIF file that should be used immediately and then deleted
        """
        try:
            # Get Statcast data for the play
            statcast_data = self.get_statcast_data_for_play(game_id, play_id, game_date, mlb_play_data)
            
            if not statcast_data:
                logger.warning(f"No Statcast data found for play {play_id} in game {game_id}")
                return None
            
            # Get the animation URL
            animation_url = self.get_play_animation_url(game_id, play_id, statcast_data, mlb_play_data)
            
            if not animation_url:
                logger.warning(f"No animation URL found for play {play_id} in game {game_id}")
                return None
            
            # Download and convert to GIF
            output_filename = f"play_{game_id}_{play_id}_{int(time.time())}.gif"
            output_path = self.temp_dir / output_filename
            
            success = self.download_and_convert_to_gif(animation_url, str(output_path))
            
            if success and output_path.exists():
                logger.info(f"Successfully created GIF: {output_path}")
                return str(output_path)
            else:
                logger.error(f"Failed to create GIF for play {play_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating GIF for play {play_id}: {e}")
            return None
    
    def get_statcast_data_for_play(self, game_id: int, play_id: int, game_date: str, mlb_play_data: Dict = None) -> Optional[Dict]:
        """Get Statcast data for a specific play"""
        try:
            params = {
                'all': 'true',
                'hfPT': '',
                'hfAB': '',
                'hfBBT': '',
                'hfPR': '',
                'hfZ': '',
                'stadium': '',
                'hfBBL': '',
                'hfNewZones': '',
                'hfGT': 'R|',
                'hfC': '',
                'hfSea': '2025|',
                'hfSit': '',
                'player_type': 'batter',
                'hfOuts': '',
                'opponent': '',
                'pitcher_throws': '',
                'batter_stands': '',
                'hfSA': '',
                'game_date_gt': game_date,
                'game_date_lt': game_date,
                'hfInfield': '',
                'team': '',
                'position': '',
                'hfOutfield': '',
                'hfRO': '',
                'home_road': '',
                'game_pk': game_id,
                'hfFlag': '',
                'hfPull': '',
                'metric_1': '',
                'hfInn': '',
                'min_pitches': '0',
                'min_results': '0',
                'group_by': 'name',
                'sort_col': 'pitches',
                'player_event_sort': 'h_launch_speed',
                'sort_order': 'desc',
                'min_pas': '0',
                'type': 'details',
            }
            
            url = f"{self.savant_base}/statcast_search/csv"
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # Parse CSV data
            csv_reader = csv.DictReader(StringIO(response.text))
            plays_with_events = [row for row in csv_reader if row.get('events')]
            
            if not plays_with_events:
                return None
            
            # If we have MLB play data, try to match it
            if mlb_play_data:
                target_event = mlb_play_data.get('result', {}).get('event', '').lower()
                target_inning = mlb_play_data.get('about', {}).get('inning')
                
                # Try to find exact match by event and inning
                for play in plays_with_events:
                    event = play.get('events', '').lower()
                    inning = play.get('inning')
                    
                    if (target_event in event or event in target_event) and str(inning) == str(target_inning):
                        return play
                
                # Fallback to event type match
                for play in plays_with_events:
                    event = play.get('events', '').lower()
                    if target_event in event or event in target_event:
                        return play
            
            # Return the most interesting play
            for play in plays_with_events:
                event = play.get('events', '').lower()
                if any(keyword in event for keyword in ['home_run', 'double', 'triple', 'single']):
                    return play
            
            return plays_with_events[0]
            
        except Exception as e:
            logger.error(f"Error fetching Statcast data: {e}")
            return None
    
    def get_play_animation_url(self, game_id: int, play_id: int, statcast_data: Dict, mlb_play_data: Dict = None) -> Optional[str]:
        """Get the animation URL for a specific play"""
        try:
            # Get game data from Baseball Savant
            gf_url = f"{self.savant_base}/gf?game_pk={game_id}&at_bat_number=1"
            response = requests.get(gf_url, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"Failed to get game data: {response.status_code}")
                return None
            
            data = response.json()
            
            # Get all plays
            all_plays = []
            all_plays.extend(data.get('team_home', []))
            all_plays.extend(data.get('team_away', []))
            
            if not mlb_play_data:
                # If no specific play data, try to find any video
                for play in all_plays:
                    play_uuid = play.get('play_id')
                    if play_uuid and play.get('pitch_call') == 'hit_into_play':
                        return f"{self.savant_base}/sporty-videos?playId={play_uuid}"
                return None
            
            # Match play using MLB data
            target_event = mlb_play_data.get('result', {}).get('event', '').lower()
            target_inning = mlb_play_data.get('about', {}).get('inning')
            target_batter = mlb_play_data.get('matchup', {}).get('batter', {}).get('fullName', '')
            
            best_matches = []
            for play in all_plays:
                play_inning = play.get('inning')
                play_batter = play.get('batter_name', '')
                play_uuid = play.get('play_id')
                
                if str(play_inning) == str(target_inning) and play_uuid:
                    # Check batter match
                    if target_batter.split()[-1].lower() in play_batter.lower():
                        score = 0
                        
                        # Prioritize contact pitches
                        if play.get('pitch_call') == 'hit_into_play':
                            score += 1000
                        
                        # Match event description
                        play_description = play.get('des', '').lower()
                        if target_event in play_description:
                            score += 100
                        
                        best_matches.append((score, play_uuid))
            
            if best_matches:
                # Sort by score and return the best match
                best_matches.sort(reverse=True)
                best_uuid = best_matches[0][1]
                return f"{self.savant_base}/sporty-videos?playId={best_uuid}"
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting animation URL: {e}")
            return None
    
    def download_and_convert_to_gif(self, video_url: str, output_path: str, max_duration: int = 8) -> bool:
        """Download video and convert to GIF - optimized for memory efficiency"""
        try:
            # Download video content
            response = requests.get(video_url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Save to temporary video file
            temp_video = self.temp_dir / f"temp_video_{int(time.time())}.mp4"
            
            with open(temp_video, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Convert to GIF using ffmpeg with optimization for file size and memory
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', str(temp_video),
                '-t', str(max_duration),  # Limit duration
                '-vf', 'scale=480:-1:flags=lanczos,fps=15',  # Reduce size and frame rate
                '-gifflags', '+transdiff',
                '-y',  # Overwrite output
                output_path
            ]
            
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Clean up temp video immediately
            try:
                temp_video.unlink()
            except:
                pass
            
            if result.returncode == 0 and os.path.exists(output_path):
                # Check file size (should be reasonable for Discord)
                file_size = os.path.getsize(output_path)
                if file_size > 8 * 1024 * 1024:  # 8MB Discord limit
                    logger.warning(f"GIF file too large: {file_size} bytes")
                    os.remove(output_path)
                    return False
                
                logger.info(f"Successfully created GIF: {output_path} ({file_size} bytes)")
                return True
            else:
                logger.error(f"ffmpeg failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg conversion timed out")
            return False
        except Exception as e:
            logger.error(f"Error converting to GIF: {e}")
            return False
        finally:
            # Always clean up temp files
            try:
                if 'temp_video' in locals() and temp_video.exists():
                    temp_video.unlink()
            except:
                pass 