import tkinter
import tkinter.filedialog
import tkinter.messagebox # Explicitly import messagebox
import customtkinter
import subprocess
import os
import glob
import json
import datetime
import sys
import platform
import threading
import time
import tempfile # For temporary thumbnail files
import uuid # For unique temporary filenames
from PIL import Image, ImageTk # Requires Pillow: pip install Pillow
# Handle potential date parsing issues across Python versions
from dateutil import parser as date_parser # Requires: pip install python-dateutil

# --- Configuration ---
# Set the directory to monitor for videos.
# IMPORTANT: Replace 'path/to/your/video/clips' with the actual path.
# Use forward slashes '/' even on Windows.
VIDEO_DIRECTORY = 'C:/obs/'
# Supported video file extensions
VIDEO_EXTENSIONS = ('*.mp4', '*.mov', '*.avi', '*.mkv', '*.wmv', '*.flv')
# Number of recent files to list
RECENT_FILES_COUNT = 5
# Thumbnail settings
THUMBNAIL_WIDTH = 240
THUMBNAIL_HEIGHT = 135 # Approximate 16:9 aspect ratio
THUMBNAIL_UPDATE_DELAY_MS = 300 # Delay thumbnail update after slider stops moving
# Output filename suffix for normal trim
TRIM_SUFFIX = "_trimmy"
# --- End Configuration ---

# --- Global Variables ---
# To store references to temporary thumbnail files for cleanup
temp_files_to_cleanup = [] # Renamed to be more general
# Placeholder image data (simple gray box)
placeholder_img = Image.new('RGB', (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), color = 'gray')

# --- Helper Functions ---

def format_time(seconds):
    """Converts seconds to HH:MM:SS.ms format."""
    if seconds is None or not isinstance(seconds, (int, float)) or seconds < 0:
        return "00:00:00.000"
    try:
        if seconds == float('inf') or seconds != seconds:
             return "00:00:00.000"
        delta = datetime.timedelta(seconds=seconds)
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds_part = divmod(remainder, 60)
        milliseconds = int(delta.microseconds / 1000)
        return f"{hours:02}:{minutes:02}:{seconds_part:02}.{milliseconds:03}"
    except OverflowError:
        print(f"Warning: Overflow formatting time for {seconds}")
        return "HH:MM:SS.ms (Overflow)"
    except Exception as e:
        print(f"Warning: Error formatting time {seconds}: {e}")
        return "00:00:00.000"

def format_size(size_bytes):
    """Converts bytes to a human-readable string (KB, MB, GB)."""
    if size_bytes is None or not isinstance(size_bytes, (int, float)) or size_bytes < 0:
        return "N/A"
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name)-1:
        size_bytes /= 1024.0
        i += 1
    p = 2 if i > 0 else 0
    return f"{size_bytes:.{p}f} {size_name[i]}"


def get_video_metadata(file_path):
    """Gets video duration, creation time (MM/DD/YY HH:MM), size str, and size bytes using ffprobe."""
    if not file_path or not os.path.exists(file_path):
        print(f"Error: File not found - {file_path}")
        return None, None, None, None

    # Check ffprobe
    try:
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffprobe', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: ffprobe not found. Make sure FFmpeg is installed and in PATH.")
        return None, None, None, None

    command = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
    try:
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
        metadata = json.loads(process.stdout)

        duration = 0.0
        creation_time_str_formatted = "N/A" # The final formatted string
        file_size_str = "N/A"
        file_size_bytes = None
        creation_time_tag = None

        # --- Duration ---
        if 'format' in metadata and 'duration' in metadata['format']:
            try:
                duration = float(metadata['format']['duration'])
            except (ValueError, TypeError):
                duration = 0.0

        # --- Creation Time ---
        # Try getting from metadata tags first
        if 'format' in metadata and 'tags' in metadata['format'] and 'creation_time' in metadata['format']['tags']:
             creation_time_tag = metadata['format']['tags']['creation_time']
             try:
                 # Use dateutil.parser for robust ISO 8601 parsing (handles Z etc.)
                 dt_object = date_parser.isoparse(creation_time_tag)
                 # Convert to local timezone if it's timezone-aware
                 if dt_object.tzinfo:
                      dt_object = dt_object.astimezone(None)
                 creation_time_str_formatted = dt_object.strftime('%m/%d/%y %H:%M')
             except ValueError as e:
                 print(f"Warning: Could not parse creation_time tag '{creation_time_tag}': {e}. Falling back to file time.")
                 creation_time_tag = None # Ensure fallback happens

        # Fallback to file system modification time if tag missing or failed parsing
        if creation_time_tag is None:
             try:
                 mtime = os.path.getmtime(file_path)
                 dt_object = datetime.datetime.fromtimestamp(mtime)
                 creation_time_str_formatted = dt_object.strftime('%m/%d/%y %H:%M')
             except Exception as e:
                  print(f"Warning: Could not get file modification time: {e}")
                  creation_time_str_formatted = "N/A" # Keep N/A if error

        # --- File Size ---
        if 'format' in metadata and 'size' in metadata['format']:
             try:
                  file_size_bytes = int(metadata['format']['size'])
             except (ValueError, TypeError):
                  pass # Fallback below
        # Fallback/Primary method for file size if not in format metadata
        if file_size_bytes is None:
            try:
                file_size_bytes = os.path.getsize(file_path)
            except OSError as e:
                print(f"Warning: Could not get file size for {file_path}: {e}")
                file_size_bytes = None
        # Format size string
        if file_size_bytes is not None:
             file_size_str = format_size(file_size_bytes)

        return duration, creation_time_str_formatted, file_size_str, file_size_bytes

    except subprocess.CalledProcessError as e:
        print(f"Error running ffprobe: {e}\nStderr: {e.stderr}")
        return None, None, None, None
    except json.JSONDecodeError as e:
        print(f"Error parsing ffprobe JSON output: {e}\nOutput was: {process.stdout}")
        return None, None, None, None
    except Exception as e:
        print(f"An unexpected error occurred getting metadata: {e}")
        return None, None, None, None


def find_recent_videos(directory, count):
    """Finds the most recently modified video files in the specified directory."""
    if not os.path.isdir(directory):
        print(f"Error: Directory not found - {directory}")
        return []
    all_videos = []
    for ext in VIDEO_EXTENSIONS:
        all_videos.extend(glob.glob(os.path.join(directory, ext)))
    if not all_videos:
        print(f"No video files found in {directory}")
        return []
    try:
        all_videos.sort(key=os.path.getmtime, reverse=True)
        return all_videos[:count]
    except Exception as e:
        print(f"Error sorting or finding recent files: {e}")
        return []

def extract_thumbnail(video_path, time_seconds, output_path):
    """Extracts a single frame from the video at the specified time using ffmpeg."""
    global temp_files_to_cleanup
    if not video_path or not os.path.exists(video_path):
        print(f"Thumbnail Error: Input video not found - {video_path}")
        return False
    try:
        # --- Linter Fix: Split startupinfo setup ---
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: ffmpeg not found."); return False

    valid_time_seconds = max(0, time_seconds) if isinstance(time_seconds, (int, float)) else 0
    time_str = format_time(valid_time_seconds)
    command = ['ffmpeg', '-ss', time_str, '-i', video_path, '-frames:v', '1', '-q:v', '3', '-vf', f'scale={THUMBNAIL_WIDTH}:-1:force_original_aspect_ratio=decrease', '-y', output_path]
    try:
        # --- Linter Fix: Split startupinfo setup ---
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        print(f"Extracting thumbnail: {' '.join(command)}")
        process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
        print(f"Thumbnail extracted successfully to {output_path}")
        temp_files_to_cleanup.append(output_path)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error extracting thumbnail: {e}\nStderr: {e.stderr}")
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except OSError: pass
        return False
    except Exception as e:
        print(f"An unexpected error during thumbnail extraction: {e}")
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except OSError: pass
        return False

def open_file_explorer(path):
    """Opens the file explorer to the specified path, selecting the file."""
    try:
        norm_path = os.path.normpath(path)
        if not os.path.exists(norm_path):
             print(f"Cannot open explorer: Path does not exist - {norm_path}")
             dir_path = os.path.dirname(norm_path)
             if os.path.isdir(dir_path):
                  if platform.system() == "Windows": os.startfile(dir_path)
                  elif platform.system() == "Darwin": subprocess.run(['open', dir_path], check=True)
                  else: subprocess.run(['xdg-open', dir_path], check=True)
             return
        if platform.system() == "Windows": subprocess.run(['explorer', '/select,', norm_path], check=True)
        elif platform.system() == "Darwin": subprocess.run(['open', '-R', norm_path], check=True)
        else:
             dir_path = os.path.dirname(norm_path) if os.path.isfile(norm_path) else norm_path
             subprocess.run(['xdg-open', dir_path], check=True)
    except FileNotFoundError: print(f"Error: Could not open file explorer (command not found).")
    except subprocess.CalledProcessError as e: print(f"Error opening file explorer: {e}")
    except Exception as e: print(f"An unexpected error occurred opening file explorer: {e}")


def cleanup_temp_files():
    """Deletes temporary files."""
    global temp_files_to_cleanup
    print("Cleaning up temporary files...")
    cleaned_count = 0; errors = 0
    for f in list(temp_files_to_cleanup):
        try:
            if f and os.path.exists(f):
                os.remove(f); print(f"Removed: {f}"); cleaned_count += 1
        except OSError as e: print(f"Error removing temp file {f}: {e}"); errors += 1
        except Exception as e: print(f"Unexpected error removing temp file {f}: {e}"); errors += 1
        finally:
             if f in temp_files_to_cleanup: temp_files_to_cleanup.remove(f)
    print(f"Cleanup finished. Removed {cleaned_count} files, {errors} errors.")
    temp_files_to_cleanup = []


# --- Main Application Class ---

class VideoTrimmerApp(customtkinter.CTk):
    def __init__(self, recent_video_paths):
        super().__init__()

        if not recent_video_paths:
            self.show_error_and_quit("No recent video files found.")
            return

        self.recent_videos = recent_video_paths
        self.video_path = self.recent_videos[0]
        self.video_filenames = [os.path.basename(p) for p in self.recent_videos]

        # Store static info for reuse in info display
        self.current_filename = ""
        self.current_creation_time = ""
        self.current_duration_str = ""
        self.current_size_str = ""

        self.duration = 0.0
        self.start_time = 0.0
        self.end_time = 0.0
        self.original_size_bytes = None
        self.is_processing = False
        self.start_thumb_job = None
        self.end_thumb_job = None

        # --- Configure Window ---
        self.title("Video Trimmer V5 (Linter Fixes)") # Updated title
        # Increased height slightly more to ensure buttons are fully visible
        self.geometry("650x750")
        self.resizable(False, False)
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        size = tuple(int(_) for _ in self.geometry().split('+')[0].split('x'))
        x = screen_width/2 - size[0]/2
        y = screen_height/2 - size[1]/2 - 50
        self.geometry("+%d+%d" % (x, y))

        # --- Create UI Elements ---
        self.grid_columnconfigure(0, weight=1) # Single main column

        # Video Selection
        self.video_select_label = customtkinter.CTkLabel(self, text="Select Video:")
        self.video_select_label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")
        self.video_combobox = customtkinter.CTkComboBox(self, values=self.video_filenames, command=self.on_video_selected)
        self.video_combobox.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="ew")
        self.video_combobox.set(self.video_filenames[0])

        # File Info Display (Single Label)
        self.info_frame = customtkinter.CTkFrame(self)
        self.info_frame.grid(row=2, column=0, padx=20, pady=(0, 15), sticky="ew")
        self.info_frame.grid_columnconfigure(0, weight=1)

        # Use a single label for the info block
        self.file_info_display = customtkinter.CTkLabel(
            self.info_frame,
            text="Loading...",
            justify=tkinter.LEFT, # Left justify text block
            anchor="nw"           # Anchor text to top-left
        )
        self.file_info_display.grid(row=0, column=0, padx=10, pady=5, sticky="ew")


        # Sliders (Rows 3-6)
        self.start_time_label = customtkinter.CTkLabel(self, text=f"Start Time: {format_time(self.start_time)}")
        self.start_time_label.grid(row=3, column=0, padx=20, pady=(10, 0), sticky="w")
        self.start_slider = customtkinter.CTkSlider(self, from_=0, to=1.0, command=self.update_start_time)
        self.start_slider.grid(row=4, column=0, padx=20, pady=(5, 10), sticky="ew")

        self.end_time_label = customtkinter.CTkLabel(self, text=f"End Time: {format_time(self.end_time)}")
        self.end_time_label.grid(row=5, column=0, padx=20, pady=(10, 0), sticky="w")
        self.end_slider = customtkinter.CTkSlider(self, from_=0, to=1.0, command=self.update_end_time)
        self.end_slider.grid(row=6, column=0, padx=20, pady=(5, 20), sticky="ew")

        # Thumbnails (Row 7)
        self.thumb_frame = customtkinter.CTkFrame(self)
        self.thumb_frame.grid(row=7, column=0, padx=20, pady=10, sticky="ew")
        self.thumb_frame.grid_columnconfigure(0, weight=1)
        self.thumb_frame.grid_columnconfigure(1, weight=1)
        self.start_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="Start Frame")
        self.start_thumb_label_text.grid(row=0, column=0, pady=(5,2))
        self.start_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=None)
        self.start_thumb_label.grid(row=1, column=0, padx=10, pady=(0,10))
        self.end_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="End Frame")
        self.end_thumb_label_text.grid(row=0, column=1, pady=(5,2))
        self.end_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=None)
        self.end_thumb_label.grid(row=1, column=1, padx=10, pady=(0,10))

        # Status Label (Row 8)
        self.status_label = customtkinter.CTkLabel(self, text="", text_color="gray")
        self.status_label.grid(row=8, column=0, padx=20, pady=5, sticky="ew")

        # Button Frame (Row 9)
        self.button_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.button_frame.grid(row=9, column=0, padx=20, pady=(10, 20), sticky="ew")
        self.button_frame.grid_columnconfigure(0, weight=1); self.button_frame.grid_columnconfigure(1, weight=0)
        self.button_frame.grid_columnconfigure(2, weight=1); self.button_frame.grid_columnconfigure(3, weight=0)

        self.trim_button = customtkinter.CTkButton(self.button_frame, text="Trim", command=lambda: self.start_trim_thread(delete_original=False))
        self.trim_button.grid(row=0, column=1, padx=10, pady=5)
        self.trim_delete_button = customtkinter.CTkButton(self.button_frame, text="Trim & Delete", command=lambda: self.start_trim_thread(delete_original=True), fg_color="#D32F2F", hover_color="#B71C1C")
        self.trim_delete_button.grid(row=0, column=3, padx=10, pady=5)

        # --- Initial Load ---
        self.load_video_data(self.video_path)
        self.display_placeholder_thumbnails()

        # --- Protocol Handler ---
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def display_placeholder_thumbnails(self):
        """Displays gray boxes in the thumbnail labels."""
        try:
            ctk_placeholder = customtkinter.CTkImage(light_image=placeholder_img, dark_image=placeholder_img, size=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
            self.start_thumb_label.configure(image=ctk_placeholder, text=""); self.start_thumb_label.image = ctk_placeholder
            self.end_thumb_label.configure(image=ctk_placeholder, text=""); self.end_thumb_label.image = ctk_placeholder
        except Exception as e: print(f"Error displaying placeholder thumbnails: {e}")


    def load_video_data(self, video_path):
        """Loads metadata and updates UI for the given video path."""
        self.video_path = video_path
        self.update_status(f"Loading metadata for {os.path.basename(video_path)}...", "gray")
        self.display_placeholder_thumbnails()

        duration_new, creation_time_fmt, file_size_str, file_size_bytes = get_video_metadata(self.video_path)

        if duration_new is None:
             self.show_error_and_quit(f"Could not get metadata for:\n{os.path.basename(self.video_path)}\n\nIs FFmpeg/ffprobe installed?")
             return

        # Store static info
        self.current_filename = os.path.basename(self.video_path)
        self.current_creation_time = creation_time_fmt if creation_time_fmt else "N/A"
        self.current_duration_str = format_time(duration_new)
        self.current_size_str = file_size_str if file_size_str else "N/A"

        # Update dynamic info
        self.duration = duration_new
        self.original_size_bytes = file_size_bytes
        self.start_time = 0.0
        self.end_time = self.duration if self.duration > 0 else 1.0

        # Update sliders
        slider_max = max(self.duration, 0.1)
        self.start_slider.configure(to=slider_max); self.start_slider.set(0)
        self.end_slider.configure(to=slider_max); self.end_slider.set(slider_max)

        # Update time labels
        self.start_time_label.configure(text=f"Start Time: {format_time(self.start_time)}")
        self.end_time_label.configure(text=f"End Time: {format_time(self.end_time)}")

        # Update the single info display label
        self.update_info_display()
        self.update_status("") # Clear loading message

        # Load initial thumbnails
        self.schedule_thumbnail_update('start', self.start_time, immediate=True)
        self.schedule_thumbnail_update('end', self.end_time, immediate=True)

    def update_info_display(self):
        """Calculates estimates and updates the single file info display label."""
        est_duration_str = "N/A"
        est_size_str = "N/A"

        if self.duration > 0 and self.original_size_bytes is not None:
             estimated_duration_sec = max(0, self.end_time - self.start_time)
             # Prevent division by zero if duration is extremely small but > 0
             if self.duration > 1e-9:
                 duration_ratio = estimated_duration_sec / self.duration
             else:
                 duration_ratio = 0
             estimated_size = int(self.original_size_bytes * duration_ratio)
             est_duration_str = format_time(estimated_duration_sec)
             est_size_str = f"{format_size(estimated_size)} (approx.)"

        # Build the text block according to the requested format
        info_text = (
            f"File: {self.current_filename}\n"
            f"Created: {self.current_creation_time}\n"
            f"\n" # Explicit blank line requested
            f"Duration: {self.current_duration_str}\n"
            f"Estimated Duration: {est_duration_str}\n"
            f"Size: {self.current_size_str}\n"
            f"Estimated size: {est_size_str}"
        )
        self.file_info_display.configure(text=info_text)


    def on_video_selected(self, selected_filename):
        """Callback when a video is chosen from the dropdown."""
        print(f"Video selected: {selected_filename}")
        try:
            selected_index = self.video_filenames.index(selected_filename)
            new_video_path = self.recent_videos[selected_index]
            if new_video_path != self.video_path:
                 self.load_video_data(new_video_path)
            else:
                 print("Selected video is the same as current.")
        except ValueError:
            print(f"Error: Could not find path for {selected_filename}")
            self.update_status("Error selecting video.", "red")


    def update_start_time(self, value):
        """Callback when the start slider is moved."""
        self.start_time = float(value)
        if self.start_time > self.end_time:
            self.start_time = self.end_time
            self.start_slider.set(self.start_time)
        self.start_time_label.configure(text=f"Start Time: {format_time(self.start_time)}")
        self.schedule_thumbnail_update('start', self.start_time)
        self.update_info_display() # Update estimates in info block

    def update_end_time(self, value):
        """Callback when the end slider is moved."""
        self.end_time = float(value)
        if self.end_time < self.start_time:
            self.end_time = self.start_time
            self.end_slider.set(self.end_time)
        self.end_time_label.configure(text=f"End Time: {format_time(self.end_time)}")
        self.schedule_thumbnail_update('end', self.end_time)
        self.update_info_display() # Update estimates in info block


    def schedule_thumbnail_update(self, thumb_type, time_sec, immediate=False):
        """Schedules or cancels thumbnail extraction using self.after for debouncing."""
        job_attr = f"{thumb_type}_thumb_job"
        existing_job = getattr(self, job_attr, None)
        if existing_job: self.after_cancel(existing_job)
        if immediate: self.generate_and_display_thumbnail(thumb_type, time_sec)
        else:
            new_job = self.after(THUMBNAIL_UPDATE_DELAY_MS, lambda t=thumb_type, s=time_sec: self.generate_and_display_thumbnail(t, s))
            setattr(self, job_attr, new_job)


    def generate_and_display_thumbnail(self, thumb_type, time_seconds):
        """Creates temp file and starts thread for thumbnail extraction."""
        if not self.video_path: return
        try:
            fd, temp_thumb_path = tempfile.mkstemp(suffix=".jpg", prefix=f"thumb_{thumb_type}_")
            os.close(fd)
            print(f"Created temp file for thumbnail: {temp_thumb_path}")
        except Exception as e:
            print(f"Error creating temporary file for thumbnail: {e}"); self.update_status(f"Error creating temp file for {thumb_type} thumb.", "red"); return
        thread = threading.Thread(target=self._run_thumbnail_extraction, args=(thumb_type, time_seconds, temp_thumb_path)); thread.daemon = True; thread.start()

    def _run_thumbnail_extraction(self, thumb_type, time_seconds, temp_thumb_path):
        """Worker function for thumbnail extraction thread."""
        success = extract_thumbnail(self.video_path, time_seconds, temp_thumb_path)
        self.after(0, self._update_thumbnail_label, thumb_type, temp_thumb_path, success)

    def _update_thumbnail_label(self, thumb_type, image_path, success):
        """Updates the CTkLabel with the new thumbnail image (runs in main thread)."""
        target_label = self.start_thumb_label if thumb_type == 'start' else self.end_thumb_label
        if success and os.path.exists(image_path) and os.path.getsize(image_path) > 0:
            try:
                pil_image = Image.open(image_path); pil_image.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)
                ctk_image = customtkinter.CTkImage(light_image=pil_image, dark_image=pil_image, size=(pil_image.width, pil_image.height))
                target_label.configure(image=ctk_image, text=""); target_label.image = ctk_image
                print(f"Updated {thumb_type} thumbnail display.")
            except Exception as e:
                print(f"Error loading/displaying thumbnail {image_path}: {e}"); self.display_placeholder_thumbnails(); self.update_status(f"Error loading {thumb_type} thumbnail.", "red")
                if image_path in temp_files_to_cleanup: temp_files_to_cleanup.remove(image_path)
                if os.path.exists(image_path):
                    try: os.remove(image_path)
                    except OSError: pass
        else:
            print(f"Thumbnail extraction failed or file invalid for {thumb_type}. Path: {image_path}"); self.display_placeholder_thumbnails()
            if os.path.exists(image_path):
                try: os.remove(image_path);
                except OSError: pass


    def start_trim_thread(self, delete_original=False):
        """Starts the trimming process after optional confirmation."""
        global temp_files_to_cleanup
        if self.is_processing: print("Already processing."); return
        if abs(self.end_time - self.start_time) < 0.1: self.update_status("Error: Start and End times are too close.", "red"); return

        if delete_original:
            confirm = tkinter.messagebox.askyesno("Confirm Delete", f"Permanently delete the original file?\n\n{os.path.basename(self.video_path)}\n\nThis cannot be undone.", icon='warning')
            if not confirm: self.update_status("Trim & Delete cancelled.", "orange"); return

        self.is_processing = True
        self.trim_button.configure(state="disabled"); self.trim_delete_button.configure(state="disabled")
        self.start_slider.configure(state="disabled"); self.end_slider.configure(state="disabled")
        self.video_combobox.configure(state="disabled"); self.update_status("Starting trim...", "blue")

        temp_output_path = None
        if delete_original:
            try:
                 output_dir = os.path.dirname(self.video_path); base, ext = os.path.splitext(os.path.basename(self.video_path))
                 temp_output_path = os.path.join(output_dir, f"{base}_temp_trim_{uuid.uuid4().hex}{ext}")
                 temp_files_to_cleanup.append(temp_output_path)
                 print(f"Generated temporary output path for delete operation: {temp_output_path}")
            except Exception as e:
                 print(f"Error generating temporary filename: {e}"); self.update_status("Error preparing temporary file.", "red"); self.reset_ui_after_processing(); return

        thread = threading.Thread(target=self.run_ffmpeg_trim, args=(delete_original, temp_output_path)); thread.daemon = True; thread.start()

    def run_ffmpeg_trim(self, delete_original, temp_output_path_for_delete):
        """Executes the ffmpeg command and handles optional deletion/renaming."""
        global temp_files_to_cleanup
        final_output_path = None

        try:
            input_filename = self.video_path; output_dir = os.path.dirname(input_filename); base, ext = os.path.splitext(os.path.basename(input_filename))
            if delete_original:
                output_filename = temp_output_path_for_delete
                if not output_filename: raise ValueError("Temporary output path missing.")
                final_output_path = input_filename
            else:
                output_filename_base = os.path.join(output_dir, f"{base}{TRIM_SUFFIX}{ext}"); output_filename = output_filename_base; counter = 1
                while os.path.exists(output_filename): output_filename = os.path.join(output_dir, f"{base}{TRIM_SUFFIX}_{counter}{ext}"); counter += 1
                final_output_path = output_filename

            start_str = format_time(self.start_time); trim_duration = max(0.1, self.end_time - self.start_time)
            command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', input_filename, '-ss', start_str, '-t', str(trim_duration), '-c', 'copy', '-map', '0', '-avoid_negative_ts', 'make_zero', '-y', output_filename]
            self.update_status("Processing with FFmpeg...", "blue"); print(f"Running FFmpeg command: {' '.join(command)}")

            # --- Linter Fix: Split startupinfo setup ---
            startupinfo = None
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                print(f"FFmpeg finished successfully. Output: {output_filename}")
                if delete_original:
                    self.update_status("FFmpeg success. Deleting original...", "blue"); time.sleep(0.5)
                    try:
                        print(f"Attempting delete: {input_filename}"); os.remove(input_filename); print(f"Delete OK: {input_filename}")
                        self.update_status("Original deleted. Renaming...", "blue"); time.sleep(0.5)
                        try:
                            print(f"Attempting rename: {output_filename} -> {final_output_path}"); os.rename(output_filename, final_output_path); print(f"Rename OK -> {final_output_path}")
                            if output_filename in temp_files_to_cleanup: temp_files_to_cleanup.remove(output_filename)
                            self.update_status("Trim & Delete successful!", "green"); self.after(100, lambda: self.post_trim_success(final_output_path))
                        except OSError as rename_err:
                            error_message = f"RENAME FAILED: {rename_err}\nTrimmed video saved as:\n{os.path.basename(output_filename)}"; print(error_message); self.update_status(error_message, "red"); self.after(100, self.reset_ui_after_processing)
                    except OSError as delete_err:
                        error_message = f"DELETE FAILED: {delete_err}\nOriginal NOT deleted.\nTrimmed video saved as:\n{os.path.basename(output_filename)}"; print(error_message); self.update_status(error_message, "red"); self.after(100, self.reset_ui_after_processing)
                else:
                    self.update_status("Trim successful!", "green"); self.after(100, lambda: self.post_trim_success(final_output_path))
            else:
                error_message = f"FFmpeg failed (code {process.returncode}):\n{stderr[-500:]}"; print(error_message); self.update_status(error_message, "red")
                if delete_original and output_filename and os.path.exists(output_filename):
                     print(f"FFmpeg failed, cleaning up temp: {output_filename}")
                     try: os.remove(output_filename)
                     except OSError as e: print(f"Error cleaning failed temp: {e}")
                     if output_filename in temp_files_to_cleanup: temp_files_to_cleanup.remove(output_filename)
                self.after(100, self.reset_ui_after_processing)
        except Exception as e:
            error_message = f"Unexpected error during trim process: {e}"; print(error_message); self.update_status(error_message, "red")
            if delete_original and temp_output_path_for_delete and os.path.exists(temp_output_path_for_delete):
                 try: os.remove(temp_output_path_for_delete)
                 except OSError as e: print(f"Error cleaning temp after unexpected error: {e}")
                 if temp_output_path_for_delete in temp_files_to_cleanup: temp_files_to_cleanup.remove(temp_output_path_for_delete)
            self.after(100, self.reset_ui_after_processing)


    def post_trim_success(self, output_filepath):
        """Actions after successful trim (and potential rename/delete)."""
        print(f"Trim process successful. Final file: {output_filepath}")
        open_file_explorer(output_filepath)
        self.update_status("Done! Closing...", "green")
        self.after(1500, self.on_closing)


    def reset_ui_after_processing(self):
        """Resets UI elements after processing."""
        self.is_processing = False
        self.trim_button.configure(state="normal"); self.trim_delete_button.configure(state="normal")
        self.start_slider.configure(state="normal"); self.end_slider.configure(state="normal")
        self.video_combobox.configure(state="normal")


    def update_status(self, message, color="gray"):
        """Updates the status label text and color."""
        def _update(): self.status_label.configure(text=message, text_color=color)
        self.after(0, _update)


    def show_error_and_quit(self, message):
        """Displays an error message box and quits."""
        print(f"FATAL ERROR: {message}")
        if not hasattr(self, 'title') or not self.winfo_exists():
            root = tkinter.Tk(); root.withdraw(); tkinter.messagebox.showerror("Error", message); root.destroy()
        else:
            if self.winfo_exists(): tkinter.messagebox.showerror("Error", message); self.destroy()
        cleanup_temp_files(); sys.exit(1)


    def on_closing(self):
        """Handles the window closing event."""
        print("Closing application.")
        if self.start_thumb_job: self.after_cancel(self.start_thumb_job)
        if self.end_thumb_job: self.after_cancel(self.end_thumb_job)
        cleanup_temp_files()
        if self.winfo_exists(): self.destroy()


# --- Script Entry Point ---
if __name__ == "__main__":
    # Check Pillow and dateutil Installation
    try: from PIL import Image, ImageTk
    except ImportError:
        # --- Linter Fix: Split print and sys.exit ---
        print("ERROR: Pillow library not found. Please install it: pip install Pillow")
        sys.exit("Dependency Error: Pillow not found.")
    try: from dateutil import parser as date_parser
    except ImportError:
        # --- Linter Fix: Split print and sys.exit ---
        print("ERROR: python-dateutil library not found. Please install it: pip install python-dateutil")
        sys.exit("Dependency Error: python-dateutil not found.")


    customtkinter.set_appearance_mode("System"); customtkinter.set_default_color_theme("blue")

    if VIDEO_DIRECTORY == 'path/to/your/video/clips':
         # --- Linter Fix: Split chained statements ---
         root = tkinter.Tk()
         root.withdraw()
         tkinter.messagebox.showerror("Config Needed", "Edit script: Set 'VIDEO_DIRECTORY'")
         root.destroy()
         sys.exit("Config Error: VIDEO_DIRECTORY not set.")
    if not os.path.isdir(VIDEO_DIRECTORY):
         # --- Linter Fix: Split chained statements ---
         root = tkinter.Tk()
         root.withdraw()
         tkinter.messagebox.showerror("Error", f"VIDEO_DIRECTORY not found:\n{VIDEO_DIRECTORY}")
         root.destroy()
         sys.exit(f"Directory not found: {VIDEO_DIRECTORY}")

    recent_videos = find_recent_videos(VIDEO_DIRECTORY, RECENT_FILES_COUNT)
    if recent_videos:
        print(f"Found {len(recent_videos)} recent videos.")
        app = VideoTrimmerApp(recent_videos)
        if app and app.winfo_exists(): app.mainloop()
        else:
            # --- Linter Fix: Split print and sys.exit ---
            print("Application failed to initialize properly.")
            cleanup_temp_files() # Attempt cleanup anyway
            sys.exit(1) # Exit with error status
    else:
        # --- Linter Fix: Split chained statements ---
        root = tkinter.Tk()
        root.withdraw()
        tkinter.messagebox.showinfo("No Videos", f"No videos found in:\n{VIDEO_DIRECTORY}")
        root.destroy()
        sys.exit(f"No videos found in {VIDEO_DIRECTORY}")
