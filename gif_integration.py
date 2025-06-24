#!/usr/bin/env python3
"""
MLB Highlight GIF Integration for Manual Dashboard
Creates ONLY real video GIFs using Baseball Savant individual play videos (primary) 
and MLB-StatsAPI highlight videos (fallback)
Optimized for 512MB RAM - creates, sends, and deletes GIFs immediately
"""

import os
import sys
import time
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import pytz
from dataclasses import dataclass, asdict
import requests

# Import statsapi
try:
    import statsapi
except ImportError:
    try:
        # Try adding common paths
        import sys
        sys.path.append('/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages')
        import statsapi
    except ImportError:
        print("Error: MLB-StatsAPI package not found. Please install it with: pip install MLB-StatsAPI")
        sys.exit(1)

logger = logging.getLogger(__name__)

class MLBHighlightGIFIntegration:
    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "mlb_gifs"
        self.temp_dir.mkdir(exist_ok=True)
        self.savant_base = "https://baseballsavant.mlb.com"
    
    def get_baseball_savant_play_video(self, game_id: int, play_id: int, mlb_play_data: Dict = None, broadcast_preference: str = 'auto') -> Optional[str]:
        """Get video URL for a specific play from Baseball Savant using the correct fastball-clips pattern"""
        try:
            # Get all plays from Baseball Savant
            url = f"https://baseballsavant.mlb.com/gf?game_pk={game_id}"
            
            # Use proper headers for MLB access
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.mlb.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                logger.warning(f"Baseball Savant API failed: {response.status_code}")
                return None
            
            data = response.json()
            
            # Extract all plays from both teams
            all_plays = []
            if 'team_home' in data and isinstance(data['team_home'], list):
                all_plays.extend([(play, 'home') for play in data['team_home']])
            if 'team_away' in data and isinstance(data['team_away'], list):
                all_plays.extend([(play, 'away') for play in data['team_away']])
            
            logger.info(f"Found {len(all_plays)} plays from Baseball Savant")
            
            # Determine broadcast preference based on teams
            selected_broadcast = self._determine_broadcast_preference(
                data, broadcast_preference, mlb_play_data
            )
            
            # Find the specific play and apply broadcast preference
            target_play = None
            target_source = None
            
            if mlb_play_data:
                # Try to match by event and inning
                event = mlb_play_data.get('result', {}).get('event', '')
                inning = mlb_play_data.get('about', {}).get('inning', 0)
                batter = mlb_play_data.get('matchup', {}).get('batter', {}).get('fullName', '')
                
                logger.info(f"Looking for play: {event} - {batter} (Inning {inning})")
                
                # First try to find exact match with preferred broadcast
                for play, source in all_plays:
                    if (selected_broadcast == 'auto' or 
                        (selected_broadcast == 'home' and source == 'home') or
                        (selected_broadcast == 'away' and source == 'away')):
                        
                        if (play.get('play_id') == play_id or 
                            (event.lower() in str(play.get('events', '')).lower() and
                             play.get('inning') == inning)):
                            target_play = play
                            target_source = source
                            logger.info(f"Found matching play with {source} broadcast preference")
                            break
                
                # Fallback to any available broadcast if preferred not found
                if not target_play:
                    for play, source in all_plays:
                        if (play.get('play_id') == play_id or 
                            (event.lower() in str(play.get('events', '')).lower() and
                             play.get('inning') == inning)):
                            target_play = play
                            target_source = source
                            logger.info(f"Using fallback {source} broadcast")
                            break
            
            # Ultimate fallback - use first available play
            if not target_play and all_plays:
                target_play, target_source = all_plays[0]
                logger.info("Using first available play as fallback")
            
            if not target_play:
                logger.warning("No plays found in Baseball Savant data")
                return None
            
            # Extract video URL from the selected play
            video_url = target_play.get('video_url')
            if not video_url:
                # Try to construct URL from play UUID if direct URL not available
                play_uuid = target_play.get('play_id')
                if play_uuid:
                    # Construct the correct video URL using fastball-clips pattern
                    video_urls = [
                        f"https://fastball-clips.mlb.com/{game_id}/{target_source}/{play_uuid}.m3u8",
                        f"https://fastball-clips.mlb.com/{game_id}/{target_source}/{play_uuid}.mp4"
                    ]
                    
                    for test_url in video_urls:
                        logger.info(f"Testing video URL: {test_url}")
                        try:
                            test_response = requests.head(test_url, headers=headers, timeout=10)
                            if test_response.status_code == 200:
                                video_url = test_url
                                logger.info(f"✅ Found working Baseball Savant video: {video_url}")
                                break
                        except Exception as e:
                            logger.info(f"Video URL test failed: {e}")
                            continue
            else:
                logger.info(f"Testing video URL: {video_url}")
                # Test if URL is accessible
                test_response = requests.head(video_url, headers=headers, timeout=10)
                if test_response.status_code == 200:
                    logger.info(f"✅ Found working Baseball Savant video: {video_url}")
                else:
                    logger.warning(f"Video URL not accessible: {test_response.status_code}")
                    video_url = None
            
            if not video_url:
                logger.warning("No valid video URL found in Baseball Savant data")
                return None
            
            return video_url
            
        except Exception as e:
            logger.error(f"Error getting Baseball Savant play video: {e}")
            return None
    
    def _determine_broadcast_preference(self, game_data: Dict, preference: str, mlb_play_data: Dict = None) -> str:
        """Determine which broadcast to prefer based on preference and game context"""
        if preference in ['home', 'away']:
            return preference
        
        # Auto selection logic
        if preference == 'mets':
            # Always prefer Mets broadcast if available
            home_team = game_data.get('home_team_name', '').upper()
            away_team = game_data.get('away_team_name', '').upper()
            
            if 'NYM' in home_team or 'METS' in home_team:
                logger.info("Mets are home team - using home broadcast")
                return 'home'
            elif 'NYM' in away_team or 'METS' in away_team:
                logger.info("Mets are away team - using away broadcast")  
                return 'away'
        
        if preference == 'auto':
            # Smart selection: prefer Mets if they're playing, otherwise home team
            home_team = game_data.get('home_team_name', '').upper()
            away_team = game_data.get('away_team_name', '').upper()
            
            # Check if Mets are involved
            if 'NYM' in home_team or 'METS' in home_team:
                logger.info("Auto-selecting Mets home broadcast")
                return 'home'
            elif 'NYM' in away_team or 'METS' in away_team:
                logger.info("Auto-selecting Mets away broadcast")
                return 'away'
            else:
                # Default to home team broadcast for other games
                logger.info("Auto-selecting home team broadcast")
                return 'home'
        
        # Default fallback
        return 'home'

    def get_game_highlights(self, game_id: int) -> List[Dict]:
        """Get all highlight videos for a game using MLB-StatsAPI (fallback method)"""
        try:
            logger.info(f"Getting highlight videos for game {game_id}")
            highlights = statsapi.game_highlight_data(game_id)
            logger.info(f"Found {len(highlights)} highlights for game {game_id}")
            
            # Log highlight titles for debugging
            for i, highlight in enumerate(highlights[:5]):
                title = highlight.get('title', 'No title')
                logger.debug(f"Highlight {i+1}: {title}")
            
            return highlights
            
        except Exception as e:
            logger.error(f"Error fetching highlights for game {game_id}: {e}")
            return []
    
    def find_matching_highlight(self, highlights: List[Dict], mlb_play_data: Dict = None) -> Optional[Dict]:
        """Find the best matching highlight for a specific play (fallback method)"""
        if not highlights:
            return None
            
        if not mlb_play_data:
            # If no play data provided, return the first highlight
            return highlights[0]
        
        try:
            # Extract play information for matching
            play_event = mlb_play_data.get('result', {}).get('event', '').lower()
            play_description = mlb_play_data.get('result', {}).get('description', '').lower()
            batter_name = mlb_play_data.get('matchup', {}).get('batter', {}).get('fullName', '').lower()
            pitcher_name = mlb_play_data.get('matchup', {}).get('pitcher', {}).get('fullName', '').lower()
            inning = mlb_play_data.get('about', {}).get('inning')
            
            logger.info(f"Looking for highlight matching: {batter_name} {play_event} in inning {inning}")
            
            # Score each highlight based on how well it matches
            best_matches = []
            for highlight in highlights:
                title = highlight.get('title', '').lower()
                description = highlight.get('description', '').lower()
                
                score = 0
                
                # Exact batter name match (highest priority)
                if batter_name and any(name in title for name in batter_name.split()):
                    score += 100
                
                # Event type match
                event_keywords = {
                    'home_run': ['homer', 'home run', 'hr'],
                    'double': ['double'],
                    'triple': ['triple'],
                    'single': ['single'],
                    'hit_by_pitch': ['hit by pitch', 'hbp'],
                    'walk': ['walk', 'bb'],
                    'strikeout': ['strikeout', 'strikes out', 'k'],
                    'flyout': ['flyout', 'flies out'],
                    'groundout': ['groundout', 'grounds out'],
                    'lineout': ['lineout', 'lines out'],
                    'double_play': ['double play', 'dp']
                }
                
                if play_event in event_keywords:
                    for keyword in event_keywords[play_event]:
                        if keyword in title or keyword in description:
                            score += 50
                            break
                
                # Pitcher name match
                if pitcher_name and any(name in title for name in pitcher_name.split()):
                    score += 25
                
                # General keywords from description
                if play_description:
                    desc_words = play_description.split()
                    for word in desc_words:
                        if len(word) > 3 and word in title:
                            score += 10
                
                if score > 0:
                    best_matches.append((score, highlight))
                    logger.debug(f"Highlight match score {score}: {title}")
            
            # Return the best match
            if best_matches:
                best_matches.sort(key=lambda x: x[0], reverse=True)
                best_highlight = best_matches[0][1]
                logger.info(f"Selected best matching highlight (score {best_matches[0][0]}): {best_highlight.get('title')}")
                return best_highlight
            
            # If no good matches, return the first highlight
            logger.info(f"No strong matches found, using first highlight: {highlights[0].get('title')}")
            return highlights[0]
            
        except Exception as e:
            logger.error(f"Error matching highlight: {e}")
            return highlights[0] if highlights else None
    
    def get_best_video_url(self, highlight: Dict) -> Optional[str]:
        """Get the best quality video URL from a highlight (fallback method)"""
        try:
            playbacks = highlight.get('playbacks', [])
            if not playbacks:
                logger.warning("No playback URLs found in highlight")
                return None
            
            # Prefer MP4 format for better compatibility
            mp4_urls = [pb for pb in playbacks if 'mp4' in pb.get('name', '').lower()]
            if mp4_urls:
                # Sort by resolution (prefer higher quality but not too high for GIF conversion)
                # Handle width/height as strings or integers
                def get_resolution(pb):
                    try:
                        width = int(pb.get('width', 0))
                        height = int(pb.get('height', 0))
                        return width * height
                    except (ValueError, TypeError):
                        return 0
                
                mp4_urls.sort(key=get_resolution, reverse=True)
                
                # Use medium quality (around 720p) for good balance
                for pb in mp4_urls:
                    try:
                        width = int(pb.get('width', 0))
                        if 500 <= width <= 1000:  # Good size for GIF conversion
                            logger.info(f"Selected video: {pb.get('name')} ({width}x{pb.get('height')})")
                            return pb.get('url')
                    except (ValueError, TypeError):
                        continue
                
                # Fallback to any MP4
                best_mp4 = mp4_urls[0]
                logger.info(f"Using fallback MP4: {best_mp4.get('name')} ({best_mp4.get('width')}x{best_mp4.get('height')})")
                return best_mp4.get('url')
            
            # If no MP4, use any available format
            best_url = playbacks[0].get('url')
            logger.info(f"Using fallback format: {playbacks[0].get('name')}")
            return best_url
            
        except Exception as e:
            logger.error(f"Error extracting video URL: {e}")
            return None
    
    def download_and_convert_to_gif(self, video_url: str, output_path: str, highlight_duration: Optional[str] = None) -> bool:
        """Download video and convert to GIF using ffmpeg"""
        temp_video = None
        palette_file = None
        
        try:
            logger.info(f"Downloading video from: {video_url}")
            
            # Determine if this is an HLS stream or direct video
            is_hls = video_url.endswith('.m3u8')
            
            if is_hls:
                # For HLS streams, use ffmpeg to download and convert directly
                logger.info("Processing HLS stream directly with ffmpeg...")
                
                # Quick test to see if HLS stream is accessible
                try:
                    test_response = requests.head(video_url, headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Referer': 'https://www.mlb.com/',
                        'Accept': 'video/mp4,video/*;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Connection': 'keep-alive',
                    }, timeout=10)
                    logger.info(f"HLS stream test: {test_response.status_code}")
                except Exception as e:
                    logger.warning(f"HLS stream test failed: {e}")
                
                # Parse highlight duration if provided
                duration_seconds = None
                if highlight_duration:
                    try:
                        # Convert duration like "00:00:15" to seconds
                        if ':' in highlight_duration:
                            parts = highlight_duration.split(':')
                            if len(parts) == 3:  # HH:MM:SS
                                duration_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                            elif len(parts) == 2:  # MM:SS
                                duration_seconds = int(parts[0]) * 60 + int(parts[1])
                        else:
                            # Already in seconds
                            duration_seconds = int(float(highlight_duration))
                        
                        logger.info(f"Using highlight duration: {duration_seconds} seconds")
                    except (ValueError, IndexError):
                        logger.warning(f"Could not parse duration '{highlight_duration}', using full video")
                        duration_seconds = None
                
                # Build ffmpeg command for HLS input - SIMPLIFIED HIGH QUALITY APPROACH
                gif_cmd = [
                    'ffmpeg',
                    '-user_agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    '-referer', 'https://www.mlb.com/',
                    '-headers', 'Accept: video/mp4,video/*;q=0.9,*/*;q=0.8\\r\\nAccept-Language: en-US,en;q=0.5\\r\\nConnection: keep-alive\\r\\n',
                    '-i', video_url,
                    '-t', '10',  # Keep duration short for speed
                    '-vf', 'fps=24,scale=1080:-1:flags=lanczos',  # Simple high-quality scaling, no heavy processing
                    '-loop', '0',
                    '-y',
                    output_path
                ]
                
                # Override duration if specified and reasonable
                if duration_seconds and duration_seconds <= 15:
                    gif_cmd[5] = str(duration_seconds)  # Replace the '-t' value
                    logger.info(f"Limiting GIF to {duration_seconds} seconds")
                else:
                    logger.info("Using 10 second limit for fast processing")
                
                # Run ffmpeg with HLS input - simple fast conversion
                result = subprocess.run(
                    gif_cmd, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=180  # 3 minute timeout for safety
                )
                
                logger.info("Simplified high-quality GIF conversion completed successfully")
                
            else:
                # For direct video files, download first then convert
                temp_video = self.temp_dir / f"temp_video_{int(time.time())}.mp4"
                
                # Use proper headers for download
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Referer': 'https://www.mlb.com/',
                    'Accept': 'video/mp4,video/*;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                }
                
                response = requests.get(video_url, stream=True, timeout=30, headers=headers)
                response.raise_for_status()
                
                with open(temp_video, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"Downloaded video to: {temp_video}")
                
                # Check video file size and validate
                video_size = temp_video.stat().st_size / 1024 / 1024
                logger.info(f"Video file size: {video_size:.1f}MB")
                
                if video_size < 0.1:  # Less than 100KB is suspicious
                    logger.error(f"Video file too small ({video_size:.1f}MB), likely corrupted")
                    return False
                
                # Validate video file with ffprobe
                try:
                    probe_cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', str(temp_video)]
                    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
                    if probe_result.returncode != 0:
                        logger.error("Video file validation failed - file appears corrupted")
                        return False
                    logger.info("Video file validation passed")
                except Exception as e:
                    logger.warning(f"Could not validate video file: {e}")
                
                # Parse highlight duration if provided
                duration_seconds = None
                if highlight_duration:
                    try:
                        # Convert duration like "00:00:15" to seconds
                        if ':' in highlight_duration:
                            parts = highlight_duration.split(':')
                            if len(parts) == 3:  # HH:MM:SS
                                duration_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                            elif len(parts) == 2:  # MM:SS
                                duration_seconds = int(parts[0]) * 60 + int(parts[1])
                        else:
                            # Already in seconds
                            duration_seconds = int(float(highlight_duration))
                        
                        logger.info(f"Using highlight duration: {duration_seconds} seconds")
                    except (ValueError, IndexError):
                        logger.warning(f"Could not parse duration '{highlight_duration}', using full video")
                        duration_seconds = None
                
                # Convert to GIF using simplified quality approach
                logger.info("Converting to GIF with simplified high quality...")
                
                # Simplified single-pass GIF conversion
                gif_cmd = [
                    'ffmpeg',
                    '-i', str(temp_video),
                    '-t', '10',  # Keep duration short for speed
                    '-vf', 'fps=24,scale=1080:-1:flags=lanczos',  # Simple high-quality scaling, no heavy processing
                    '-loop', '0',
                    '-y',
                    output_path
                ]
                
                # Override duration if specified and reasonable
                if duration_seconds and duration_seconds <= 15:
                    gif_cmd[3] = str(duration_seconds)  # Replace the '-t' value
                    logger.info(f"Limiting GIF to {duration_seconds} seconds")
                else:
                    logger.info("Using 10 second limit for fast processing")
                
                # Run with timeout and capture output
                result = subprocess.run(
                    gif_cmd, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=180  # 3 minute timeout for safety
                )
                
                logger.info("Simplified high-quality GIF conversion completed successfully")
            
            # Check if output file was created
            if not Path(output_path).exists():
                logger.error("Output GIF file was not created")
                return False
            
            # Check file size (Telegram bot limit is ~50MB for GIFs)
            file_size = Path(output_path).stat().st_size
            file_size_mb = file_size / 1024 / 1024
            
            if file_size > 50 * 1024 * 1024:
                logger.warning(f"GIF too large: {file_size_mb:.1f}MB, trying with smaller settings...")
                
                # Try again with smaller, faster settings
                input_source = video_url if is_hls else str(temp_video)
                
                # Enhanced fallback approach for smaller file
                if is_hls:
                    smaller_cmd = [
                        'ffmpeg',
                        '-user_agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        '-referer', 'https://www.mlb.com/',
                        '-headers', 'Accept: video/mp4,video/*;q=0.9,*/*;q=0.8\\r\\nAccept-Language: en-US,en;q=0.5\\r\\nConnection: keep-alive\\r\\n',
                        '-i', input_source,
                        '-t', '8',  # Shorter duration
                        '-vf', 'fps=20,scale=720:-1:flags=lanczos',  # Simple scaling fallback
                        '-loop', '0',
                        '-y',
                        output_path
                    ]
                else:
                    smaller_cmd = [
                        'ffmpeg',
                        '-i', input_source,
                        '-t', '8',  # Shorter duration
                        '-vf', 'fps=20,scale=720:-1:flags=lanczos',  # Simple scaling fallback
                        '-loop', '0',
                        '-y',
                        output_path
                    ]
                
                result = subprocess.run(
                    smaller_cmd, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=120  # 2 minute timeout for fallback
                )
                
                file_size = Path(output_path).stat().st_size
                file_size_mb = file_size / 1024 / 1024
            
            logger.info(f"✅ Successfully created GIF: {output_path} ({file_size_mb:.1f}MB)")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg conversion timed out")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e}")
            logger.error(f"FFmpeg stderr: {e.stderr}")
            logger.error(f"FFmpeg stdout: {e.stdout}")
            return False
        except Exception as e:
            logger.error(f"Error creating GIF: {e}")
            return False
        finally:
            # Clean up temporary files
            try:
                if temp_video and temp_video.exists():
                    temp_video.unlink()
                    logger.debug(f"Cleaned up temp video: {temp_video}")
                if palette_file and palette_file.exists():
                    palette_file.unlink()
                    logger.debug(f"Cleaned up palette file: {palette_file}")
            except Exception as cleanup_error:
                logger.warning(f"Error cleaning up temp files: {cleanup_error}")
    
    def download_and_convert_to_video(self, video_url: str, output_path: str, max_duration: int = 30) -> bool:
        """Download video and convert to MP4 format (with sound) using ffmpeg"""
        try:
            logger.info(f"Downloading video from: {video_url}")
            
            # Determine if this is an HLS stream or direct video
            is_hls = video_url.endswith('.m3u8')
            
            if is_hls:
                # For HLS streams, use ffmpeg to download and convert directly
                logger.info("Processing HLS stream directly with ffmpeg...")
                
                # Quick test to see if HLS stream is accessible
                try:
                    test_response = requests.head(video_url, headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Referer': 'https://www.mlb.com/',
                        'Accept': 'video/mp4,video/*;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Connection': 'keep-alive',
                    }, timeout=10)
                    logger.info(f"HLS stream test: {test_response.status_code}")
                except Exception as e:
                    logger.warning(f"HLS stream test failed: {e}")
                
                # Build ffmpeg command for HLS input - HIGH QUALITY VIDEO WITH AUDIO
                video_cmd = [
                    'ffmpeg',
                    '-user_agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    '-referer', 'https://www.mlb.com/',
                    '-headers', 'Accept: video/mp4,video/*;q=0.9,*/*;q=0.8\\r\\nAccept-Language: en-US,en;q=0.5\\r\\nConnection: keep-alive\\r\\n',
                    '-i', video_url,
                    '-t', str(max_duration),  # Limit duration
                    '-c:v', 'libx264',  # High quality video codec
                    '-c:a', 'aac',      # High quality audio codec
                    '-preset', 'fast',  # Fast encoding
                    '-crf', '18',       # High quality (lower is better, 18 is visually lossless)
                    '-movflags', '+faststart',  # Optimize for streaming
                    '-y',
                    output_path
                ]
                
                logger.info(f"Creating high-quality MP4 with audio (max {max_duration}s)")
                
                # Run ffmpeg with HLS input
                result = subprocess.run(
                    video_cmd, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                logger.info("High-quality MP4 conversion completed successfully")
                
            else:
                # For direct video files, download first then convert if needed
                temp_video = self.temp_dir / f"temp_video_{int(time.time())}.mp4"
                
                # Use proper headers for download
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Referer': 'https://www.mlb.com/',
                    'Accept': 'video/mp4,video/*;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                }
                
                response = requests.get(video_url, stream=True, timeout=30, headers=headers)
                response.raise_for_status()
                
                with open(temp_video, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"Downloaded video to: {temp_video}")
                
                # Check if conversion is needed or if we can use directly
                if temp_video.suffix.lower() == '.mp4' and max_duration >= 60:
                    # If it's already MP4 and we don't need to trim, just copy
                    import shutil
                    shutil.copy2(temp_video, output_path)
                    logger.info("Using downloaded MP4 directly (no conversion needed)")
                    temp_video.unlink()  # Clean up temp file
                else:
                    # Convert to ensure quality and duration limits
                    video_cmd = [
                        'ffmpeg',
                        '-i', str(temp_video),
                        '-t', str(max_duration),
                        '-c:v', 'libx264',
                        '-c:a', 'aac',
                        '-preset', 'fast',
                        '-crf', '18',
                        '-movflags', '+faststart',
                        '-y',
                        output_path
                    ]
                    
                    result = subprocess.run(
                        video_cmd, 
                        check=True, 
                        capture_output=True, 
                        text=True,
                        timeout=180
                    )
                    
                    logger.info("MP4 conversion completed successfully")
                    temp_video.unlink()  # Clean up temp file
            
            # Check if output file was created
            if not Path(output_path).exists():
                logger.error("Output MP4 file was not created")
                return False
            
            # Check file size
            file_size = Path(output_path).stat().st_size
            file_size_mb = file_size / 1024 / 1024
            
            logger.info(f"✅ Successfully created MP4: {output_path} ({file_size_mb:.1f}MB)")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg video conversion timed out")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg video error: {e}")
            logger.error(f"FFmpeg stderr: {e.stderr}")
            logger.error(f"FFmpeg stdout: {e.stdout}")
            return False
        except Exception as e:
            logger.error(f"Error creating MP4: {e}")
            return False
    
    def create_gif_for_play(self, game_id: int, play_id: int, game_date: str, mlb_play_data: Dict = None, 
                           broadcast_preference: str = 'auto', output_format: str = 'gif') -> Optional[str]:
        """Create a GIF/video for a specific play using Baseball Savant individual play videos ONLY
        
        Args:
            broadcast_preference: 'auto' (smart selection), 'home', 'away', or 'mets'
            output_format: 'gif' or 'mp4' for video output
        """
        try:
            logger.info(f"Creating {output_format.upper()} for play - game {game_id}, play {play_id}")
            
            # ONLY METHOD: Try Baseball Savant individual play video
            logger.info("🎯 Trying Baseball Savant individual play video...")
            savant_video_url = self.get_baseball_savant_play_video(
                game_id, play_id, mlb_play_data, broadcast_preference
            )
            
            if not savant_video_url:
                # No fallback - fail cleanly with specific error message
                logger.warning(f"❌ No Baseball Savant video available for play {play_id} in game {game_id}")
                return None
                
            logger.info(f"✅ Found Baseball Savant play video, creating {output_format.upper()}...")
            
            event_type = 'play'
            if mlb_play_data:
                event_type = mlb_play_data.get('result', {}).get('event', 'play').lower().replace(' ', '_')
            
            # Choose file extension based on output format
            file_ext = 'mp4' if output_format.lower() == 'mp4' else 'gif'
            output_filename = f"mlb_savant_{event_type}_{game_id}_{play_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_ext}"
            output_path = self.temp_dir / output_filename
            
            if output_format.lower() == 'mp4':
                success = self.download_and_convert_to_video(savant_video_url, str(output_path))
            else:
                success = self.download_and_convert_to_gif(savant_video_url, str(output_path))
            
            if success and output_path.exists():
                logger.info(f"✅ Successfully created Baseball Savant {output_format.upper()}: {output_path}")
                return str(output_path)
            else:
                logger.error(f"❌ Failed to create {output_format.upper()} from Baseball Savant video for play {play_id}")
                return None
            
        except Exception as e:
            logger.error(f"Error creating {output_format.upper()} for play {play_id} in game {game_id}: {e}")
            return None
    
    def cleanup_temp_files(self):
        """Clean up all temporary files"""
        try:
            for file_path in self.temp_dir.glob("*"):
                if file_path.is_file():
                    file_path.unlink()
                    logger.debug(f"Cleaned up temp file: {file_path}")
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")

    def get_detailed_game_data(self, game_id: int) -> Dict:
        """Get comprehensive pitch-by-pitch data organized by half-inning and at-bat"""
        try:
            logger.info(f"Getting detailed pitch data for game {game_id}")
            
            # Get Baseball Savant data
            url = f"https://baseballsavant.mlb.com/gf?game_pk={game_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.mlb.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                logger.error(f"Failed to get Baseball Savant data: {response.status_code}")
                return {}
            
            data = response.json()
            
            # Organize data by half-inning and at-bat
            organized_data = {
                'game_id': game_id,
                'game_info': {
                    'home_team': data.get('home_team_data', {}).get('abbreviation', 'HOME'),
                    'away_team': data.get('away_team_data', {}).get('abbreviation', 'AWAY'),
                    'game_date': data.get('game_date', ''),
                    'venue': data.get('venue_name', '')
                },
                'half_innings': {}
            }
            
            # Process both home and away team data
            # IMPORTANT: Baseball Savant data structure is inverted!
            # - team_home data contains pitches when AWAY team is batting (top half-inning)
            # - team_away data contains pitches when HOME team is batting (bottom half-inning)
            teams_data = [
                (data.get('team_home', []), 'home', 'top'),    # home data source = away team batting = top half
                (data.get('team_away', []), 'away', 'bottom')  # away data source = home team batting = bottom half
            ]
            
            for team_plays, team_type, inning_half in teams_data:
                if not isinstance(team_plays, list):
                    continue
                    
                # Group pitches by at-bat first to organize properly
                at_bat_groups = {}
                
                for play in team_plays:
                    inning = play.get('inning', 1)
                    batter_name = play.get('batter_name', 'Unknown Batter')
                    
                    # Create a more robust at-bat key using inning + batter + sequence
                    # This ensures we don't mix up different at-bats by the same batter
                    at_bat_key = f"{inning}_{batter_name}_{play.get('at_bat_number', 0)}"
                    
                    if at_bat_key not in at_bat_groups:
                        at_bat_groups[at_bat_key] = {
                            'inning': inning,
                            'batter_name': batter_name,
                            'pitches': [],
                            'at_bat_result': None
                        }
                    
                    # Add each pitch as an individual entry
                    pitch_data = {
                        'play_id': play.get('play_id'),
                        'pitch_number': play.get('pitch_number', 1),
                        'pitch_type': play.get('pitch_name', 'Unknown'),
                        'velocity': play.get('start_speed', 0) or play.get('release_speed', 0),  # Use start_speed first, fallback to release_speed
                        'result': play.get('description', ''),
                        'pitcher_name': play.get('pitcher_name', 'Unknown Pitcher'),
                        'count': f"{play.get('balls', 0)}-{play.get('strikes', 0)}",
                        'team_batting': team_type,
                        'video_available': bool(play.get('play_id')),
                        'batter_name': batter_name  # Add batter name to each pitch
                    }
                    
                    at_bat_groups[at_bat_key]['pitches'].append(pitch_data)
                    
                    # Track the final result of the at-bat
                    if play.get('events'):
                        at_bat_groups[at_bat_key]['at_bat_result'] = play.get('events')
                
                # Now organize by half-inning
                for at_bat_key, at_bat_data in at_bat_groups.items():
                    inning = at_bat_data['inning']
                    half_inning_key = f"{inning_half}_{inning}"
                    
                    if half_inning_key not in organized_data['half_innings']:
                        # Fix team assignment: top = away team batting, bottom = home team batting
                        batting_team = organized_data['game_info']['away_team'] if inning_half == 'top' else organized_data['game_info']['home_team']
                        organized_data['half_innings'][half_inning_key] = {
                            'inning': inning,
                            'half': inning_half,
                            'display_name': f"{batting_team} Batting - Inning {inning} ({inning_half.title()})",
                            'at_bats': {}
                        }
                    
                    # Sort pitches by pitch number
                    at_bat_data['pitches'].sort(key=lambda p: p.get('pitch_number', 0))
                    
                    # Store the complete at-bat with all individual pitches
                    organized_data['half_innings'][half_inning_key]['at_bats'][at_bat_key] = {
                        'batter_name': at_bat_data['batter_name'],
                        'result': at_bat_data['at_bat_result'] or 'In Progress',
                        'pitches': at_bat_data['pitches'],  # Each pitch is individually accessible
                        'pitch_count': len(at_bat_data['pitches'])
                    }
            
            total_pitches = sum(
                len(at_bat['pitches']) 
                for half_inning in organized_data['half_innings'].values() 
                for at_bat in half_inning['at_bats'].values()
            )
            
            logger.info(f"✅ Organized {total_pitches} individual pitches across {len(organized_data['half_innings'])} half-innings")
            return organized_data
            
        except Exception as e:
            logger.error(f"Error getting detailed game data: {e}")
            return {}

    def get_pitch_video_url(self, game_id: int, play_id: str, team_batting: str) -> Optional[str]:
        """Get video URL for a specific pitch using the play_id (UUID)"""
        try:
            if not play_id:
                return None
                
            # The team_batting parameter represents the data source (home/away)
            # Video URL path should match the data source
            team_path = team_batting  # 'home' or 'away' - matches data source
            
            # Use proper headers for MLB access
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.mlb.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
            }
            
            # Try HLS first (more reliable), then MP4
            video_urls = [
                f"https://fastball-clips.mlb.com/{game_id}/{team_path}/{play_id}.m3u8",
                f"https://fastball-clips.mlb.com/{game_id}/{team_path}/{play_id}.mp4"
            ]
            
            for video_url in video_urls:
                try:
                    # Test if video URL is accessible
                    video_response = requests.head(video_url, headers=headers, timeout=10)
                    if video_response.status_code == 200:
                        logger.info(f"✅ Found pitch video: {video_url}")
                        return video_url
                except Exception:
                    continue
            
            logger.warning(f"No video found for pitch {play_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting pitch video URL: {e}")
            return None

    def create_gif_for_pitch(self, game_id: int, play_id: str, team_batting: str, pitch_info: Dict = None) -> Optional[str]:
        """Create a GIF for a specific pitch"""
        try:
            logger.info(f"Creating GIF for pitch - game {game_id}, play {play_id}")
            
            # Get the pitch video URL
            video_url = self.get_pitch_video_url(game_id, play_id, team_batting)
            
            if not video_url:
                logger.warning(f"❌ No video available for pitch {play_id}")
                return None
                
            logger.info("✅ Found pitch video, creating GIF...")
            
            # Create descriptive filename
            if pitch_info:
                batter = pitch_info.get('batter_name', 'unknown').replace(' ', '_')
                pitch_type = pitch_info.get('pitch_type', 'pitch').replace(' ', '_')
                velocity = pitch_info.get('velocity', 0)
                gif_filename = f"pitch_{batter}_{pitch_type}_{velocity}mph_{game_id}_{play_id[:8]}.gif"
            else:
                gif_filename = f"pitch_{game_id}_{play_id[:8]}_{datetime.now().strftime('%H%M%S')}.gif"
            
            gif_path = self.temp_dir / gif_filename
            
            success = self.download_and_convert_to_gif(video_url, str(gif_path))
            
            if success and gif_path.exists():
                logger.info(f"✅ Successfully created pitch GIF: {gif_path}")
                return str(gif_path)
            else:
                logger.error(f"❌ Failed to create GIF for pitch {play_id}")
                return None
            
        except Exception as e:
            logger.error(f"Error creating GIF for pitch {play_id}: {e}")
            return None

# Maintain compatibility with existing code
class BaseballSavantGIFIntegration(MLBHighlightGIFIntegration):
    """Compatibility wrapper for existing code"""
    pass

if __name__ == "__main__":
    # Test the integration
    gif_integration = MLBHighlightGIFIntegration()
    print("MLB Hybrid GIF integration module loaded successfully!")
    print("Now using Baseball Savant individual play videos (primary) + MLB highlights (fallback)") 