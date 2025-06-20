#!/usr/bin/env python3
"""
Baseball Savant GIF Integration for Manual Dashboard
Creates ONLY real video GIFs - no fallback static images
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
        Get REAL VIDEO GIF for a specific play - optimized for immediate use and deletion
        Returns path to GIF file that should be used immediately and then deleted
        Returns None if no real video is available (NO FALLBACK STATIC IMAGES)
        """
        try:
            logger.info(f"Creating VIDEO GIF for game {game_id}, play {play_id}")
            
            # Get Statcast data for the play
            statcast_data = self.get_statcast_data_for_play(game_id, play_id, game_date, mlb_play_data)
            
            if not statcast_data:
                logger.warning(f"No Statcast data found for play {play_id} in game {game_id}")
                return None
            
            # Get the animation URL
            animation_url = self.get_play_animation_url(game_id, play_id, statcast_data, mlb_play_data)
            
            if not animation_url:
                logger.warning(f"No video animation URL found for play {play_id} in game {game_id}")
                return None
            
            # Download and convert to GIF
            output_filename = f"play_{game_id}_{play_id}_{int(time.time())}.gif"
            output_path = self.temp_dir / output_filename
            
            success = self.download_and_convert_to_gif(animation_url, str(output_path))
            
            if success and output_path.exists():
                logger.info(f"Successfully created VIDEO GIF: {output_path}")
                return str(output_path)
            else:
                logger.error(f"Failed to create VIDEO GIF for play {play_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating VIDEO GIF for play {play_id}: {e}")
            return None
    
    def get_statcast_data_for_play(self, game_id: int, play_id: int, game_date: str, mlb_play_data: Dict = None) -> Optional[Dict]:
        """Get Statcast data for a specific play - using exact same method as working Impact Players system"""
        try:
            # Extract year from game_date for the season parameter
            year = game_date.split('-')[0]
            logger.info(f"Fetching Statcast data for game {game_id} on {game_date} (season {year})")
            
            # Use EXACT same parameters as the working Impact Players system
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
                'hfGT': 'R|',  # Regular season
                'hfC': '',
                'hfSea': f'{year}|',  # Current season
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
                'game_pk': game_id,  # CRUCIAL: This filters to the specific game
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
            
            # Use the CSV export endpoint for easier parsing
            url = f"{self.savant_base}/statcast_search/csv"
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # Parse CSV data
            csv_reader = csv.DictReader(StringIO(response.text))
            
            # Get all plays with events (not just pitches)
            plays_with_events = []
            for row in csv_reader:
                if row.get('events'):  # Only rows with actual events
                    plays_with_events.append(row)
            
            logger.info(f"Found {len(plays_with_events)} Statcast plays with events for game {game_id}")
            
            # If we have MLB play data to match against, try to find the exact play
            if mlb_play_data:
                target_event = mlb_play_data.get('result', {}).get('event', '').lower()
                target_inning = mlb_play_data.get('about', {}).get('inning')
                target_batter = mlb_play_data.get('matchup', {}).get('batter', {}).get('id')
                target_batter_name = mlb_play_data.get('matchup', {}).get('batter', {}).get('fullName', '')
                
                logger.info(f"Looking for play: {target_event} in inning {target_inning} by {target_batter_name}")
                
                # Try to find exact match by event type and inning
                for play in plays_with_events:
                    event = play.get('events', '').lower()
                    inning = play.get('inning')
                    batter_id = play.get('batter')
                    
                    # Match by event type and inning
                    if (target_event in event or event in target_event) and str(inning) == str(target_inning):
                        logger.info(f"Found matching Statcast play: {event} in inning {inning}")
                        return play
                
                # If no exact match, try just by event type
                for play in plays_with_events:
                    event = play.get('events', '').lower()
                    if target_event in event or event in target_event:
                        logger.info(f"Found Statcast play by event type: {event}")
                        return play
            
            # Fallback: prioritize visually interesting plays
            for play in plays_with_events:
                event = play.get('events', '').lower()
                # Prioritize visually interesting plays
                if any(keyword in event for keyword in ['home_run', 'double', 'triple', 'single']):
                    logger.info(f"Found interesting Statcast play: {event}")
                    return play
            
            # If no interesting plays, return the first play with events
            if plays_with_events:
                logger.info(f"Returning first available Statcast play: {plays_with_events[0].get('events')}")
                return plays_with_events[0]
            
            logger.warning(f"No Statcast plays with events found for game {game_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching Statcast data: {e}")
            return None
    
    def get_play_animation_url(self, game_id: int, play_id: int, statcast_data: Dict, mlb_play_data: Dict = None) -> Optional[str]:
        """Get the animation URL for a specific play from Baseball Savant - using exact same method as working system"""
        try:
            # We need to get the play UUID from the Baseball Savant /gf endpoint
            # since the Statcast CSV doesn't include it
            
            logger.info(f"Getting play UUID for game {game_id}, play {play_id}")
            
            # Get game data from Baseball Savant /gf endpoint
            gf_url = f"{self.savant_base}/gf?game_pk={game_id}&at_bat_number=1"
            gf_response = requests.get(gf_url, timeout=15)
            
            if gf_response.status_code != 200:
                logger.warning(f"Failed to get game data from /gf endpoint: {gf_response.status_code}")
                return None
            
            gf_data = gf_response.json()
            
            # Look in both home and away team plays
            all_plays = []
            all_plays.extend(gf_data.get('team_home', []))
            all_plays.extend(gf_data.get('team_away', []))
            
            logger.info(f"Found {len(all_plays)} total plays in Baseball Savant game data")
            
            # DEBUG: Log sample of available plays
            contact_plays = [p for p in all_plays if p.get('pitch_call') == 'hit_into_play' and p.get('play_id')]
            logger.info(f"Found {len(contact_plays)} contact plays with UUIDs")
            
            # Find the matching play using MLB API data if available
            target_play_uuid = None
            
            if mlb_play_data:
                target_event = mlb_play_data.get('result', {}).get('event', '').lower()
                target_inning = mlb_play_data.get('about', {}).get('inning')
                target_batter = mlb_play_data.get('matchup', {}).get('batter', {}).get('fullName', '')
                
                logger.info(f"Looking for {target_batter} {target_event} in inning {target_inning}")
                
                # Try to find exact match - prioritize plays that have the actual event in their description
                best_matches = []
                for play in all_plays:
                    play_event = play.get('events', '').lower()
                    play_description = play.get('des', '').lower()
                    play_inning = play.get('inning')
                    play_batter = play.get('batter_name', '')
                    play_uuid = play.get('play_id')
                    
                    # Must match inning and have a play UUID
                    if str(play_inning) == str(target_inning) and play_uuid:
                        # Check if batter matches - more flexible matching
                        batter_last_name = target_batter.split()[-1].lower() if target_batter else ""
                        play_batter_lower = play_batter.lower()
                        batter_match = (batter_last_name in play_batter_lower or 
                                      any(name.lower() in play_batter_lower for name in target_batter.split()))
                        
                        if batter_match:
                            # Score this match based on how well it matches the event
                            score = 0
                            
                            # HIGHEST PRIORITY: This is the actual contact pitch (not just a pitch in the at-bat)
                            pitch_call = play.get('pitch_call', '')
                            call = play.get('call', '')
                            if pitch_call == 'hit_into_play' or call == 'X':
                                score += 1000  # Heavily prioritize the contact pitch
                            
                            # High priority: event description contains the target event
                            if target_event in play_description or target_event.replace(' ', '') in play_description.replace(' ', ''):
                                score += 100
                            
                            # Medium priority: events field contains the target event  
                            if target_event in play_event or target_event.replace(' ', '') in play_event.replace(' ', ''):
                                score += 50
                            
                            # For home runs, look for specific indicators
                            if 'home' in target_event and 'run' in target_event:
                                if 'homer' in play_description or 'home run' in play_description:
                                    score += 100
                                if 'homer' in play_event or 'home run' in play_event:
                                    score += 50
                                
                                # Additional bonus for hit data which confirms this was the contact pitch
                                if play.get('hit_speed') or play.get('hit_distance'):
                                    score += 500
                            
                            # Bonus for exact event match
                            if play_event.strip() == target_event.strip():
                                score += 200
                            
                            best_matches.append((score, play, play_uuid))
                            logger.info(f"Found potential match (score {score}): {play_batter} - {play_event} - pitch_call: {pitch_call}")
                
                # Sort by score and take the best match
                if best_matches:
                    best_matches.sort(key=lambda x: x[0], reverse=True)
                    best_score, best_play, target_play_uuid = best_matches[0]
                    
                    logger.info(f"Selected best match (score {best_score}): {best_play.get('batter_name')} - {best_play.get('events')}")
                    logger.info(f"Play UUID: {target_play_uuid}")
                else:
                    logger.warning(f"No exact matches found for {target_batter} {target_event} in inning {target_inning}")
            
            # Fallback: look for interesting plays if no exact match
            if not target_play_uuid:
                logger.info("No exact match found, looking for interesting plays...")
                for play in all_plays:
                    play_event = play.get('events', '').lower()
                    play_uuid = play.get('play_id')
                    pitch_call = play.get('pitch_call', '')
                    
                    # Only consider plays that are actual contact pitches with interesting events
                    if (play_uuid and pitch_call == 'hit_into_play' and 
                        any(keyword in play_event for keyword in ['home_run', 'double', 'triple'])):
                        logger.info(f"Found interesting contact play: {play_event}")
                        target_play_uuid = play_uuid
                        break
            
            # Even broader fallback: try ANY contact play
            if not target_play_uuid:
                logger.info("Still no match, trying ANY contact play...")
                for play in all_plays:
                    play_uuid = play.get('play_id')
                    pitch_call = play.get('pitch_call', '')
                    
                    if play_uuid and pitch_call == 'hit_into_play':
                        logger.info(f"Using ANY contact play: {play.get('batter_name')} - {play.get('events')}")
                        target_play_uuid = play_uuid
                        break
            
            if not target_play_uuid:
                logger.error("No suitable play with UUID found!")
                # DEBUG: Log what we actually have
                all_uuids = [p.get('play_id') for p in all_plays if p.get('play_id')]
                logger.info(f"Available UUIDs in game: {len(all_uuids)} total")
                return None
            
            # Now get the video URL using the UUID
            logger.info(f"Getting video URL for play UUID: {target_play_uuid}")
            
            sporty_url = f"{self.savant_base}/sporty-videos?playId={target_play_uuid}"
            response = requests.get(sporty_url, timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                logger.info(f"Got video page ({len(html_content)} chars)")
                
                # DEBUG: Log if we see any video-related content
                if 'sporty-clips.mlb.com' in html_content:
                    logger.info("✅ Found sporty-clips URLs in HTML")
                else:
                    logger.warning("❌ No sporty-clips URLs found in HTML")
                
                # Extract the actual video URL from the HTML using multiple patterns
                video_url_patterns = [
                    r'https://sporty-clips\.mlb\.com/[^"\s]*\.mp4',
                    r'"src":\s*"(https://sporty-clips\.mlb\.com/[^"]*\.mp4)"',
                    r'data-src="(https://sporty-clips\.mlb\.com/[^"]*\.mp4)"',
                    r'source src="(https://sporty-clips\.mlb\.com/[^"]*\.mp4)"',
                    r'video.*?src="(https://sporty-clips\.mlb\.com/[^"]*\.mp4)"',
                    r'"url":\s*"(https://sporty-clips\.mlb\.com/[^"]*\.mp4)"',
                    r'href="(https://sporty-clips\.mlb\.com/[^"]*\.mp4)"',
                ]
                
                found_any_urls = False
                for pattern_idx, pattern in enumerate(video_url_patterns):
                    matches = re.findall(pattern, html_content, re.IGNORECASE)
                    if matches:
                        found_any_urls = True
                        logger.info(f"Pattern {pattern_idx+1} found {len(matches)} potential URLs")
                    
                    for match in matches:
                        video_url = match[0] if isinstance(match, tuple) else match
                        logger.info(f"Found potential video URL: {video_url}")
                        
                        # Test if this URL actually works
                        try:
                            test_response = requests.head(video_url, timeout=10)
                            if test_response.status_code == 200:
                                content_type = test_response.headers.get('content-type', '')
                                if 'video' in content_type:
                                    logger.info(f"✅ Confirmed working video URL: {video_url}")
                                    return video_url
                                else:
                                    logger.warning(f"URL exists but not video: {content_type}")
                            else:
                                logger.warning(f"URL test failed with status: {test_response.status_code}")
                        except Exception as e:
                            logger.warning(f"Video URL test failed: {e}")
                            continue
                
                if not found_any_urls:
                    logger.error(f"No video URLs found with any pattern. Sample HTML: {html_content[:500]}...")
                else:
                    logger.warning(f"Found URLs but none were working videos")
                
                return None
            else:
                logger.warning(f"Failed to fetch video page: {response.status_code}")
                return None
            
        except Exception as e:
            logger.error(f"Error getting animation URL: {e}")
            return None
    
    def download_and_convert_to_gif(self, video_url: str, output_path: str, max_duration: int = 8) -> bool:
        """Download video and convert to GIF using ffmpeg - optimized for memory efficiency"""
        try:
            logger.info(f"Downloading video from: {video_url}")
            
            # Download video content
            response = requests.get(video_url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Save to temporary video file
            temp_video = self.temp_dir / f"temp_video_{int(time.time())}.mp4"
            
            with open(temp_video, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded video ({temp_video.stat().st_size} bytes), converting to GIF...")
            
            # Convert to GIF using ffmpeg with 2-pass approach for better quality
            # Step 1: Generate palette
            palette_path = self.temp_dir / f'palette_{int(time.time())}.png'
            palette_cmd = [
                'ffmpeg',
                '-i', str(temp_video),
                '-t', str(max_duration),
                '-vf', 'fps=15,scale=480:-1:flags=lanczos,palettegen=stats_mode=diff',
                '-y',
                str(palette_path)
            ]
            
            result = subprocess.run(palette_cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                logger.error(f"Palette generation failed: {result.stderr}")
                return False
            
            # Step 2: Create GIF with palette
            gif_cmd = [
                'ffmpeg',
                '-i', str(temp_video),
                '-i', str(palette_path),
                '-t', str(max_duration),
                '-lavfi', 'fps=15,scale=480:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5',
                '-y',
                output_path
            ]
            
            result = subprocess.run(gif_cmd, capture_output=True, text=True, timeout=60)
            
            # Clean up temp files immediately
            try:
                temp_video.unlink()
                palette_path.unlink(missing_ok=True)
            except:
                pass
            
            if result.returncode == 0 and os.path.exists(output_path):
                # Check file size (should be reasonable for Discord)
                file_size = os.path.getsize(output_path)
                if file_size > 8 * 1024 * 1024:  # 8MB Discord limit
                    logger.warning(f"GIF file too large: {file_size} bytes")
                    os.remove(output_path)
                    return False
                
                logger.info(f"Successfully created VIDEO GIF: {output_path} ({file_size} bytes)")
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
                if 'palette_path' in locals() and palette_path.exists():
                    palette_path.unlink()
            except:
                pass 