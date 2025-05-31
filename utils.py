import os
import glob
import json
import datetime
import subprocess
import platform
import tkinter.messagebox # For error popups from ffprobe/ffmpeg
import tempfile
import uuid
from dateutil import parser as date_parser

from . import config_settings

temp_files_to_cleanup = []

def format_time(seconds):
    if seconds is None or not isinstance(seconds, (int, float)) or seconds < 0:
        return "00:00:00"
    try:
        if seconds == float('inf') or seconds != seconds: # handles NaN
            return "00:00:00"
        delta = datetime.timedelta(seconds=seconds)
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds_part = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds_part:02}"
    except Exception as e:
        print(f"Warning: Error formatting time {seconds}: {e}")
        return "00:00:00"

def format_size(size_bytes):
    if size_bytes is None or not isinstance(size_bytes, (int, float)) or size_bytes < 0: return "N/A"
    if size_bytes == 0: return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name)-1 and (isinstance(size_bytes, (int, float)) and size_bytes == size_bytes):
        size_bytes /= 1024.0
        i += 1
    p = 2 if i > 0 else 0
    return f"{size_bytes:.{p}f} {size_name[i]}"

def get_parent_directories(path):
    path = os.path.normpath(os.path.abspath(path))
    parents = []
    if not os.path.isdir(path): path = os.path.dirname(path)
    if path and os.path.isdir(path): parents.append(path)
    while True:
        parent = os.path.dirname(path)
        if parent == path or not parent: break
        if os.path.isdir(parent): parents.append(parent)
        else: break
        path = parent
    return parents

def load_last_directory():
    # Assuming config_settings.CONFIG_FILENAME is accessible
    # If running this file standalone, direct import of config_settings might be needed for CONFIG_FILENAME
    # For now, let's assume it's run as part of the larger application where imports are resolved.
    # To make this function truly standalone for testing, pass CONFIG_FILENAME or import it directly.
    config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), config_settings.CONFIG_FILENAME)
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                last_dir = config.get("last_input_directory")
                if last_dir and os.path.isdir(last_dir):
                    print(f"Loaded last directory from config: {last_dir}")
                    return last_dir
                else: print(f"Config found, but last directory is invalid or missing: {last_dir}")
    except (json.JSONDecodeError, IOError, Exception) as e: print(f"Error loading config file ({config_path}): {e}")
    print("No valid last directory found in config or config does not exist.")
    return None

def get_video_metadata(file_path):
    if not file_path or not os.path.exists(file_path):
        print(f"Error: File not found - {file_path}")
        return None, None, None, None
    try:
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffprobe', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: ffprobe not found.")
        tkinter.messagebox.showerror("Error", "ffprobe (part of FFmpeg) not found in system PATH.\nPlease install FFmpeg and ensure it's added to PATH.")
        return None, None, None, None

    command = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
    try:
        startupinfo_run = None # New variable for this specific run
        if platform.system() == 'Windows':
            startupinfo_run = subprocess.STARTUPINFO()
            startupinfo_run.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo_run.wShowWindow = subprocess.SW_HIDE
        process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo_run)
        metadata = json.loads(process.stdout)
        duration = 0.0
        creation_time_str_formatted = "N/A"
        file_size_str = "N/A"
        file_size_bytes = None
        creation_time_tag = None

        if 'format' in metadata:
            if 'duration' in metadata['format']:
                try:
                    duration = float(metadata['format']['duration'])
                except (ValueError, TypeError):
                    duration = 0.0
            if 'tags' in metadata['format'] and 'creation_time' in metadata['format']['tags']:
                 creation_time_tag = metadata['format']['tags']['creation_time']
                 try:
                     dt_object = date_parser.isoparse(creation_time_tag)
                     dt_object = dt_object.astimezone(None) if dt_object.tzinfo else dt_object
                     creation_time_str_formatted = dt_object.strftime('%m/%d/%y %H:%M')
                 except ValueError as e:
                     print(f"Warning: Could not parse creation_time tag '{creation_time_tag}': {e}.")
                     creation_time_tag = None # Fallback to file mtime
            if 'size' in metadata['format']:
                try:
                    file_size_bytes = int(metadata['format']['size'])
                except (ValueError, TypeError):
                    pass # file_size_bytes remains None

        if creation_time_tag is None: # If not found in tags or parsing failed
             try:
                 mtime = os.path.getmtime(file_path)
                 dt_object = datetime.datetime.fromtimestamp(mtime)
                 creation_time_str_formatted = dt_object.strftime('%m/%d/%y %H:%M')
             except Exception as e:
                 print(f"Warning: Could not get file modification time: {e}")
                 creation_time_str_formatted = "N/A"

        if file_size_bytes is None: # If not found in format metadata
            try:
                file_size_bytes = os.path.getsize(file_path)
            except OSError as e:
                print(f"Warning: Could not get file size from OS: {e}")
                file_size_bytes = None

        if file_size_bytes is not None:
            file_size_str = utils.format_size(file_size_bytes)

        return duration, creation_time_str_formatted, file_size_str, file_size_bytes
    except subprocess.CalledProcessError as e:
        print(f"ffprobe execution error: {e}\nstderr: {e.stderr}")
        return None, None, None, None
    except json.JSONDecodeError as e:
        print(f"Error decoding ffprobe JSON output: {e}\nOutput: {process.stdout if 'process' in locals() else 'N/A'}")
        return None, None, None, None
    except Exception as e:
        print(f"An unexpected error occurred in get_video_metadata: {e}")
        return None, None, None, None

def find_recent_videos(directory, count):
    if not directory or not os.path.isdir(directory):
        print(f"Video search directory is invalid: {directory}")
        return []
    all_videos = []
    for ext_pattern in config_settings.VIDEO_EXTENSIONS:
        all_videos.extend(glob.glob(os.path.join(directory, ext_pattern)))
    if not all_videos:
        print(f"No videos found in {directory} with extensions {config_settings.VIDEO_EXTENSIONS}")
        return []
    try:
        all_videos.sort(key=os.path.getmtime, reverse=True)
        return all_videos[:count]
    except Exception as e:
        print(f"Error sorting videos: {e}")
        return []

def extract_thumbnail(video_path, time_seconds, output_path):
    # Uses global temp_files_to_cleanup from this module
    if not video_path or not os.path.exists(video_path):
        print(f"Thumbnail Error: Input video file not found - {video_path}")
        return False
    try:
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: ffmpeg not found for thumbnail extraction.")
        tkinter.messagebox.showerror("Error", "ffmpeg (part of FFmpeg) not found in system PATH.\nPlease install FFmpeg and ensure it's added to PATH.")
        return False

    valid_time_seconds = max(0, time_seconds) if isinstance(time_seconds, (int, float)) else 0
    time_str = format_time(valid_time_seconds).split('.')[0] # HH:MM:SS format

    command = [
        'ffmpeg', '-ss', time_str, '-i', video_path,
        '-frames:v', '1', '-q:v', '3', # Quality for JPG, good enough
        '-vf', f'scale={config_settings.THUMBNAIL_WIDTH}:-1:force_original_aspect_ratio=decrease,crop={config_settings.THUMBNAIL_WIDTH}:{config_settings.THUMBNAIL_HEIGHT}',
        '-y', output_path
    ]
    try:
        startupinfo_run = None # New variable for this specific run
        if platform.system() == 'Windows':
            startupinfo_run = subprocess.STARTUPINFO()
            startupinfo_run.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo_run.wShowWindow = subprocess.SW_HIDE
        process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo_run)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            if output_path not in temp_files_to_cleanup: # Avoid duplicates
                temp_files_to_cleanup.append(output_path)
            return True
        else:
            print(f"Error extracting thumbnail: Output file not created or is empty. Command: {' '.join(command)}")
            if process.stderr: print(f"FFmpeg stderr: {process.stderr}")
            if os.path.exists(output_path): # Cleanup empty file
                try: os.remove(output_path)
                except OSError: pass
            return False
    except subprocess.CalledProcessError as e:
        print(f"Error during thumbnail extraction (ffmpeg process error): {e}\nStderr: {e.stderr}\nCommand: {' '.join(command)}")
        if os.path.exists(output_path): # Cleanup partial file
            try: os.remove(output_path)
            except OSError: pass
        return False
    except Exception as e:
        print(f"An unexpected error occurred during thumbnail extraction: {e}\nCommand: {' '.join(command)}")
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except OSError: pass
        return False

def cleanup_temp_files_on_exit(): # Renamed to avoid conflict if imported directly
    # Uses global temp_files_to_cleanup from this module
    print("Cleaning up temporary files on exit...")
    cleaned_count = 0
    errors = 0
    # Iterate over a copy if modifying the list during iteration (though remove should handle it)
    for f_path in list(temp_files_to_cleanup): 
        try:
            if f_path and os.path.exists(f_path):
                os.remove(f_path)
                cleaned_count += 1
        except OSError as e:
            print(f"Error removing temporary file {f_path}: {e}")
            errors += 1
        except Exception as e: # Catch any other unexpected error
            print(f"Unexpected error removing temporary file {f_path}: {e}")
            errors += 1
        finally:
            # Ensure file is removed from the list even if deletion failed, to prevent re-attempts
            if f_path in temp_files_to_cleanup:
                temp_files_to_cleanup.remove(f_path)
    
    print(f"Cleanup finished. Removed {cleaned_count} files, encountered {errors} errors.")
    # Clear the list after attempting cleanup
    temp_files_to_cleanup.clear()