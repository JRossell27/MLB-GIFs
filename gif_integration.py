#!/usr/bin/env python3
"""
MLB Highlight GIF Integration for Manual Dashboard
Creates ONLY real video GIFs using Baseball Savant individual play videos (primary) 
and MLB-StatsAPI highlight videos (fallback)
Optimized for 512MB RAM - creates, sends, and deletes GIFs immediately
"""

import os
import time
import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import subprocess
import tempfile
from pathlib import Path
import sys
import re
import json

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
    
    def get_baseball_savant_play_video(self, game_id: int, play_id: int, mlb_play_data: Dict = None) -> Optional[str]:
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
            
            if not all_plays:
                logger.warning("No plays found in Baseball Savant data")
                return None
            
            # Find matching play using sophisticated matching
            target_play = None
            target_team_path = None
            
            if mlb_play_data:
                # Try to match using MLB play data
                target_batter = mlb_play_data.get('batter_name', '').strip()
                target_event = mlb_play_data.get('event', '').strip()
                target_inning = mlb_play_data.get('inning')
                
                logger.info(f"Looking for play: {target_batter} - {target_event} (Inning {target_inning})")
                
                for play, team_path in all_plays:
                    play_batter = play.get('batter_name', '').strip()
                    play_event = play.get('events', '').strip()
                    play_inning = play.get('inning')
                    
                    # Match by batter name and inning
                    if (play_batter == target_batter and 
                        play_inning == target_inning and
                        (not target_event or play_event == target_event)):
                        target_play = play
                        target_team_path = team_path
                        logger.info(f"✅ Found matching play: {play_batter} - {play_event}")
                        break
            
            # If no MLB data match, try to find by play_id or use first play
            if not target_play and all_plays:
                target_play, target_team_path = all_plays[0]  # Use first play as fallback
                logger.info(f"Using first available play as fallback")
            
            if not target_play:
                logger.warning("No suitable play found for video")
                return None
            
            # Extract play UUID
            play_uuid = target_play.get('play_id')
            if not play_uuid:
                logger.warning("No play UUID found")
                return None
            
            # Construct the correct video URL using fastball-clips pattern
            # Try HLS first (more reliable), then MP4
            video_urls = [
                f"https://fastball-clips.mlb.com/{game_id}/{target_team_path}/{play_uuid}.m3u8",
                f"https://fastball-clips.mlb.com/{game_id}/{target_team_path}/{play_uuid}.mp4"
            ]
            
            for video_url in video_urls:
                logger.info(f"Testing video URL: {video_url}")
                try:
                    # Test if video URL is accessible
                    video_response = requests.head(video_url, headers=headers, timeout=10)
                    if video_response.status_code == 200:
                        logger.info(f"✅ Found working Baseball Savant video: {video_url}")
                        return video_url
                    else:
                        logger.info(f"Video URL returned {video_response.status_code}")
                except Exception as e:
                    logger.info(f"Video URL test failed: {e}")
                    continue
            
            logger.warning(f"No working video URLs found for play UUID {play_uuid}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting Baseball Savant video: {e}")
            return None

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
                
                # Build ffmpeg command for HLS input
                gif_cmd = [
                    'ffmpeg',
                    '-user_agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    '-referer', 'https://www.mlb.com/',
                    '-headers', 'Accept: video/mp4,video/*;q=0.9,*/*;q=0.8\r\nAccept-Language: en-US,en;q=0.5\r\nConnection: keep-alive\r\n',
                    '-i', video_url,
                    '-vf', 'fps=15,scale=480:-1:flags=lanczos',
                    '-loop', '0',
                    '-y',
                    output_path
                ]
                
                # Add duration limit if specified
                if duration_seconds and duration_seconds <= 20:
                    gif_cmd.insert(3, '-t')
                    gif_cmd.insert(4, str(duration_seconds))
                    logger.info(f"Limiting GIF to {duration_seconds} seconds")
                else:
                    logger.info("Using full video duration (no time limit)")
                
                # Run ffmpeg with HLS input
                result = subprocess.run(
                    gif_cmd, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=90
                )
                
                logger.info("HLS to GIF conversion completed successfully")
                
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
                
                # Convert to GIF
                logger.info("Converting to GIF (using full highlight duration)...")
                
                gif_cmd = [
                    'ffmpeg',
                    '-i', str(temp_video),
                    '-vf', 'fps=15,scale=480:-1:flags=lanczos',
                    '-loop', '0',
                    '-y',
                    output_path
                ]
                
                # Add duration limit only if we have one and it's reasonable (under 20 seconds)
                if duration_seconds and duration_seconds <= 20:
                    gif_cmd.insert(3, '-t')
                    gif_cmd.insert(4, str(duration_seconds))
                    logger.info(f"Limiting GIF to {duration_seconds} seconds")
                else:
                    logger.info("Using full video duration (no time limit)")
                
                # Run with timeout and capture output
                result = subprocess.run(
                    gif_cmd, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=90
                )
                
                logger.info("GIF conversion completed successfully")
            
            # Check if output file was created
            if not Path(output_path).exists():
                logger.error("Output GIF file was not created")
                return False
            
            # Check file size (Discord limit is ~8MB for GIFs)
            file_size = Path(output_path).stat().st_size
            file_size_mb = file_size / 1024 / 1024
            
            if file_size > 8 * 1024 * 1024:
                logger.warning(f"GIF too large: {file_size_mb:.1f}MB, trying with shorter duration...")
                
                # Try again with 10 second limit
                input_source = video_url if is_hls else str(temp_video)
                smaller_cmd = [
                    'ffmpeg',
                    '-i', input_source,
                    '-t', '10',  # 10 second fallback
                    '-vf', 'fps=12,scale=400:-1:flags=lanczos',  # Smaller fallback
                    '-loop', '0',
                    '-y',
                    output_path
                ]
                
                # Add headers for HLS streams in fallback too
                if is_hls:
                    smaller_cmd = [
                        'ffmpeg',
                        '-user_agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        '-referer', 'https://www.mlb.com/',
                        '-headers', 'Accept: video/mp4,video/*;q=0.9,*/*;q=0.8\r\nAccept-Language: en-US,en;q=0.5\r\nConnection: keep-alive\r\n',
                        '-i', input_source,
                        '-t', '10',
                        '-vf', 'fps=12,scale=400:-1:flags=lanczos',
                        '-loop', '0',
                        '-y',
                        output_path
                    ]
                
                result = subprocess.run(
                    smaller_cmd, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=60
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
    
    def create_gif_for_play(self, game_id: int, play_id: int, game_date: str, mlb_play_data: Dict = None) -> Optional[str]:
        """Create a GIF for a specific play using Baseball Savant individual play videos ONLY"""
        try:
            logger.info(f"Creating GIF for play - game {game_id}, play {play_id}")
            
            # ONLY METHOD: Try Baseball Savant individual play video
            logger.info("🎯 Trying Baseball Savant individual play video...")
            savant_video_url = self.get_baseball_savant_play_video(game_id, play_id, mlb_play_data)
            
            if not savant_video_url:
                # No fallback - fail cleanly with specific error message
                logger.warning(f"❌ No Baseball Savant video available for play {play_id} in game {game_id}")
                return None
                
            logger.info("✅ Found Baseball Savant play video, creating GIF...")
            
            event_type = 'play'
            if mlb_play_data:
                event_type = mlb_play_data.get('result', {}).get('event', 'play').lower().replace(' ', '_')
            
            gif_filename = f"mlb_savant_{event_type}_{game_id}_{play_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gif"
            gif_path = self.temp_dir / gif_filename
            
            success = self.download_and_convert_to_gif(savant_video_url, str(gif_path))
            
            if success and gif_path.exists():
                logger.info(f"✅ Successfully created Baseball Savant GIF: {gif_path}")
                return str(gif_path)
            else:
                logger.error(f"❌ Failed to create GIF from Baseball Savant video for play {play_id}")
                return None
            
        except Exception as e:
            logger.error(f"Error creating GIF for play {play_id} in game {game_id}: {e}")
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

# Maintain compatibility with existing code
class BaseballSavantGIFIntegration(MLBHighlightGIFIntegration):
    """Compatibility wrapper for existing code"""
    pass

if __name__ == "__main__":
    # Test the integration
    gif_integration = MLBHighlightGIFIntegration()
    print("MLB Hybrid GIF integration module loaded successfully!")
    print("Now using Baseball Savant individual play videos (primary) + MLB highlights (fallback)") 