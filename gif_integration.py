#!/usr/bin/env python3
"""
MLB Highlight GIF Integration for Manual Dashboard
Creates ONLY real video GIFs using MLB-StatsAPI highlight videos
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
        
    def get_game_highlights(self, game_id: int) -> List[Dict]:
        """Get all highlight videos for a game using MLB-StatsAPI"""
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
        """Find the best matching highlight for a specific play"""
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
        """Get the best quality video URL from a highlight"""
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
            
            # Download the video
            temp_video = self.temp_dir / f"temp_video_{int(time.time())}.mp4"
            
            response = requests.get(video_url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(temp_video, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded video to: {temp_video}")
            
            # Check video file size
            video_size = temp_video.stat().st_size / 1024 / 1024
            logger.info(f"Video file size: {video_size:.1f}MB")
            
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
            
            # Use simpler, faster conversion for memory-constrained environment
            logger.info("Converting to GIF (using full highlight duration)...")
            
            gif_cmd = [
                'ffmpeg',
                '-i', str(temp_video),
                '-vf', 'fps=15,scale=480:-1:flags=lanczos',  # Better quality: higher resolution and fps
                '-loop', '0',  # Loop forever
                '-y',  # Overwrite output
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
                timeout=90  # Increased timeout for longer videos
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
                smaller_cmd = [
                    'ffmpeg',
                    '-i', str(temp_video),
                    '-t', '10',  # 10 second fallback
                    '-vf', 'fps=12,scale=400:-1:flags=lanczos',  # Smaller fallback
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
        """Create a GIF for a specific play using MLB highlight videos"""
        try:
            logger.info(f"Creating GIF for play - game {game_id}, play {play_id}")
            
            # Step 1: Get all highlights for the game
            highlights = self.get_game_highlights(game_id)
            if not highlights:
                logger.warning(f"No highlights found for game {game_id}")
                return None
            
            # Step 2: Find the best matching highlight
            best_highlight = self.find_matching_highlight(highlights, mlb_play_data)
            if not best_highlight:
                logger.warning(f"No suitable highlight found for play {play_id}")
                return None
            
            # Step 3: Get the best video URL
            video_url = self.get_best_video_url(best_highlight)
            if not video_url:
                logger.warning(f"No video URL found in highlight")
                return None
            
            # Step 4: Create the GIF
            event_type = 'play'
            if mlb_play_data:
                event_type = mlb_play_data.get('result', {}).get('event', 'play').lower().replace(' ', '_')
            
            gif_filename = f"mlb_{event_type}_{game_id}_{play_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gif"
            gif_path = self.temp_dir / gif_filename
            
            success = self.download_and_convert_to_gif(video_url, str(gif_path))
            
            if success and gif_path.exists():
                logger.info(f"✅ Successfully created GIF: {gif_path}")
                return str(gif_path)
            else:
                logger.error(f"❌ Failed to create GIF for play {play_id} in game {game_id}")
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
    print("MLB Highlight GIF integration module loaded successfully!")
    print("Now using reliable MLB-StatsAPI highlight videos instead of Baseball Savant URLs") 