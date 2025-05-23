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
# Set the *initial* directory to monitor for videos.
# IMPORTANT: Replace 'path/to/your/video/clips' with the actual path.
# Use forward slashes '/' even on Windows.
# User's path from uploaded file: 'C:/obs/test'
INITIAL_VIDEO_DIRECTORY = '' # Renamed from VIDEO_DIRECTORY
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
# Fine scrubbing increment in seconds
SCRUB_INCREMENT = 0.5
# --- End Configuration ---

# --- Global Variables ---
# To store references to temporary thumbnail files for cleanup
temp_files_to_cleanup = []
# Placeholder image data (simple gray box)
placeholder_img = Image.new('RGB', (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), color = 'gray')
# Store browse option text to identify it
BROWSE_OPTION = "Browse..."

# --- Helper Functions ---

def format_time(seconds):
    """Converts seconds to HH:MM:SS.ms format."""
    if seconds is None or not isinstance(seconds, (int, float)) or seconds < 0:
        return "00:00:00.000"
    try:
        if seconds == float('inf') or seconds != seconds: return "00:00:00.000"
        delta = datetime.timedelta(seconds=seconds)
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds_part = divmod(remainder, 60)
        milliseconds = int(delta.microseconds / 1000)
        return f"{hours:02}:{minutes:02}:{seconds_part:02}.{milliseconds:03}"
    except OverflowError: print(f"Warning: Overflow formatting time for {seconds}"); return "HH:MM:SS.ms (Overflow)"
    except Exception as e: print(f"Warning: Error formatting time {seconds}: {e}"); return "00:00:00.000"

def format_size(size_bytes):
    """Converts bytes to a human-readable string (KB, MB, GB)."""
    if size_bytes is None or not isinstance(size_bytes, (int, float)) or size_bytes < 0: return "N/A"
    if size_bytes == 0: return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name)-1: size_bytes /= 1024.0; i += 1
    p = 2 if i > 0 else 0
    return f"{size_bytes:.{p}f} {size_name[i]}"

def get_parent_directories(path):
    """Returns a list of parent directories up to the root, including the path itself."""
    # Normalize path and handle potential drive letter case issues on Windows
    path = os.path.normpath(os.path.abspath(path))
    parents = []
    if not os.path.isdir(path): # If path is a file, start from its directory
        path = os.path.dirname(path)

    # Add the starting directory if it exists
    if path and os.path.isdir(path):
        parents.append(path)

    # Add parent directories
    while True:
        parent = os.path.dirname(path)
        if parent == path or not parent: # Reached root or empty path
            break
        # Check if parent exists to handle potential issues with root/network paths
        if os.path.isdir(parent):
             parents.append(parent)
        else: # Stop if parent doesn't exist (e.g., reached base of network share)
            break
        path = parent
    return parents

CONFIG_FILENAME = "config.json" # Store in the same dir as the script for simplicity

def load_last_directory():
    """Loads the last used directory from the config file."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                last_dir = config.get("last_input_directory")
                if last_dir and os.path.isdir(last_dir):
                    print(f"Loaded last directory from config: {last_dir}")
                    return last_dir
                else:
                    print("Config found, but last directory is invalid or missing.")
    except (json.JSONDecodeError, IOError, Exception) as e:
        print(f"Error loading config file ({config_path}): {e}")
    print("No valid last directory found in config.")
    return None

def save_last_directory(directory_path):
    """Saves the specified directory to the config file."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
    config = {"last_input_directory": directory_path}
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"Saved last directory to config: {directory_path}")
        return True
    except (IOError, Exception) as e:
        print(f"Error saving config file ({config_path}): {e}")
        return False


def get_video_metadata(file_path):
    """Gets video duration, creation time (MM/DD/YY HH:MM), size str, and size bytes using ffprobe."""
    if not file_path or not os.path.exists(file_path): print(f"Error: File not found - {file_path}"); return None, None, None, None
    try: # Check ffprobe
        startupinfo = None
        if platform.system() == 'Windows': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffprobe', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    except (FileNotFoundError, subprocess.CalledProcessError): print("Error: ffprobe not found."); return None, None, None, None

    command = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
    try: # Run ffprobe
        startupinfo = None
        if platform.system() == 'Windows': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
        metadata = json.loads(process.stdout)

        duration = 0.0; creation_time_str_formatted = "N/A"; file_size_str = "N/A"; file_size_bytes = None; creation_time_tag = None
        if 'format' in metadata:
            if 'duration' in metadata['format']:
                try:
                    duration = float(metadata['format']['duration'])
                except (ValueError, TypeError): duration = 0.0
            if 'tags' in metadata['format'] and 'creation_time' in metadata['format']['tags']: # Creation Time Tag
                 creation_time_tag = metadata['format']['tags']['creation_time']
                 try: dt_object = date_parser.isoparse(creation_time_tag); dt_object = dt_object.astimezone(None) if dt_object.tzinfo else dt_object; creation_time_str_formatted = dt_object.strftime('%m/%d/%y %H:%M')
                 except ValueError as e: print(f"Warning: Could not parse tag '{creation_time_tag}': {e}."); creation_time_tag = None
            if 'size' in metadata['format']: 
                try: file_size_bytes = int(metadata['format']['size'])
                except (ValueError, TypeError): pass # File Size Tag
        if creation_time_tag is None: # Fallback Creation Time (File Mod Time)
             try: mtime = os.path.getmtime(file_path); dt_object = datetime.datetime.fromtimestamp(mtime); creation_time_str_formatted = dt_object.strftime('%m/%d/%y %H:%M')
             except Exception as e: print(f"Warning: Could not get file mod time: {e}"); creation_time_str_formatted = "N/A"
        if file_size_bytes is None: # Fallback File Size (OS)
            try: file_size_bytes = os.path.getsize(file_path)
            except OSError as e: print(f"Warning: Could not get file size: {e}"); file_size_bytes = None
        if file_size_bytes is not None: file_size_str = format_size(file_size_bytes) # Format Size String
        return duration, creation_time_str_formatted, file_size_str, file_size_bytes
    except subprocess.CalledProcessError as e: print(f"ffprobe error: {e}\n{e.stderr}"); return None, None, None, None
    except json.JSONDecodeError as e: print(f"ffprobe JSON error: {e}\n{process.stdout}"); return None, None, None, None
    except Exception as e: print(f"Metadata error: {e}"); return None, None, None, None


def find_recent_videos(directory, count):
    """Finds the most recently modified video files in the specified directory."""
    if not directory or not os.path.isdir(directory): print(f"Video search dir invalid: {directory}"); return []
    all_videos = []
    for ext in VIDEO_EXTENSIONS: all_videos.extend(glob.glob(os.path.join(directory, ext)))
    if not all_videos: print(f"No videos found in {directory}"); return []
    try: all_videos.sort(key=os.path.getmtime, reverse=True); return all_videos[:count]
    except Exception as e: print(f"Error sorting videos: {e}"); return []

def extract_thumbnail(video_path, time_seconds, output_path):
    """Extracts a single frame from the video at the specified time using ffmpeg."""
    global temp_files_to_cleanup
    if not video_path or not os.path.exists(video_path): print(f"Thumb Error: Input not found - {video_path}"); return False
    try: # Check ffmpeg
        startupinfo = None
        if platform.system() == 'Windows': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    except (FileNotFoundError, subprocess.CalledProcessError): print("Error: ffmpeg not found."); return False

    valid_time_seconds = max(0, time_seconds) if isinstance(time_seconds, (int, float)) else 0
    time_str = format_time(valid_time_seconds)
    command = ['ffmpeg', '-ss', time_str, '-i', video_path, '-frames:v', '1', '-q:v', '3', '-vf', f'scale={THUMBNAIL_WIDTH}:-1:force_original_aspect_ratio=decrease', '-y', output_path]
    try: # Run ffmpeg
        startupinfo = None
        if platform.system() == 'Windows': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
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
             print(f"Cannot open explorer: Path does not exist - {norm_path}"); dir_path = os.path.dirname(norm_path)
             if os.path.isdir(dir_path): # Try opening directory instead
                  if platform.system() == "Windows": os.startfile(dir_path)
                  elif platform.system() == "Darwin": subprocess.run(['open', dir_path], check=True)
                  else: subprocess.run(['xdg-open', dir_path], check=True)
             return
        if platform.system() == "Windows": subprocess.run(['explorer', '/select,', norm_path], check=True)
        elif platform.system() == "Darwin": subprocess.run(['open', '-R', norm_path], check=True)
        else: dir_path = os.path.dirname(norm_path) if os.path.isfile(norm_path) else norm_path; subprocess.run(['xdg-open', dir_path], check=True)
    except FileNotFoundError: print(f"Error: Could not open file explorer (command not found).")
    except subprocess.CalledProcessError as e: print(f"Error opening file explorer: {e}")
    except Exception as e: print(f"An unexpected error occurred opening file explorer: {e}")


def cleanup_temp_files():
    """Deletes temporary files."""
    global temp_files_to_cleanup
    print("Cleaning up temporary files..."); cleaned_count = 0; errors = 0
    for f in list(temp_files_to_cleanup):
        try:
            if f and os.path.exists(f): os.remove(f); print(f"Removed: {f}"); cleaned_count += 1
        except OSError as e: print(f"Error removing temp file {f}: {e}"); errors += 1
        except Exception as e: print(f"Unexpected error removing temp file {f}: {e}"); errors += 1
        finally:
             if f in temp_files_to_cleanup: temp_files_to_cleanup.remove(f)
    print(f"Cleanup finished. Removed {cleaned_count} files, {errors} errors."); temp_files_to_cleanup = []


# --- Main Application Class ---

class VideoTrimmerApp(customtkinter.CTk):
    # --- Initialization ---
    def __init__(self, initial_input_dir): # Changed parameter name
        super().__init__()

        # --- Input/Output Directories ---
        # Validate initial dir, fallback to CWD if invalid
        if not initial_input_dir or not os.path.isdir(initial_input_dir):
            print(f"Warning: Initial directory '{initial_input_dir}' not valid. Using current working directory.")
            initial_input_dir = os.getcwd()
        self.current_input_directory = os.path.normpath(initial_input_dir)
        self.output_directory = self.current_input_directory # Default output = input
        self.location_options = [] # Store full paths for location dropdown
        self.destination_options = [] # Store full paths for destination dropdown

        # --- Video Data ---
        # Initialize these before calling update methods
        self.recent_videos = [] # Full paths
        self.video_filenames = [] # Basenames for display
        self.video_path = None # Currently selected video full path

        # --- State Variables ---
        self.current_filename = ""; self.current_creation_time = ""; self.current_duration_str = ""; self.current_size_str = ""
        self.duration = 0.0; self.start_time = 0.0; self.end_time = 0.0; self.original_size_bytes = None
        self.is_processing = False; self.start_thumb_job = None; self.end_thumb_job = None

        # --- Configure Window ---
        self.title("Trimmy V6 (Dir Select & Scrub)") # Updated title
        self.geometry("700x850") # Increased width/height for new elements
        self.resizable(False, False)
        self.update_idletasks()
        screen_width = self.winfo_screenwidth(); screen_height = self.winfo_screenheight()
        size = tuple(int(_) for _ in self.geometry().split('+')[0].split('x'))
        x = screen_width/2 - size[0]/2; y = screen_height/2 - size[1]/2 - 50
        self.geometry("+%d+%d" % (x, y))

        # --- Create UI Elements ---
        # Main grid configuration
        self.grid_columnconfigure(0, weight=0) # Col 0 for labels / left buttons
        self.grid_columnconfigure(1, weight=1) # Col 1 for dropdowns / sliders
        self.grid_columnconfigure(2, weight=0) # Col 2 for right buttons

        # --- Location Selection (Row 0, 1) ---
        self.location_label = customtkinter.CTkLabel(self, text="Location:")
        self.location_label.grid(row=0, column=0, columnspan=3, padx=20, pady=(20, 5), sticky="w")
        self.location_combobox = customtkinter.CTkComboBox(self, values=[], command=self.on_location_selected)
        self.location_combobox.grid(row=1, column=0, columnspan=3, padx=20, pady=(0, 15), sticky="ew")

        # --- Video Selection (Row 2, 3) ---
        self.video_select_label = customtkinter.CTkLabel(self, text="Select Video:")
        self.video_select_label.grid(row=2, column=0, columnspan=3, padx=20, pady=(5, 5), sticky="w")
        self.video_combobox = customtkinter.CTkComboBox(self, values=[], command=self.on_video_selected)
        self.video_combobox.grid(row=3, column=0, columnspan=3, padx=20, pady=(0, 15), sticky="ew")

        # --- File Info Display (Row 4) ---
        self.info_frame = customtkinter.CTkFrame(self)
        self.info_frame.grid(row=4, column=0, columnspan=3, padx=20, pady=(0, 15), sticky="ew")
        self.info_frame.grid_columnconfigure(0, weight=1)
        self.file_info_display = customtkinter.CTkLabel(self.info_frame, text="Select a video", justify=tkinter.LEFT, anchor="nw")
        self.file_info_display.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        # --- Sliders & Scrub Buttons (Rows 5-8) ---
        # Start Time
        self.start_time_label = customtkinter.CTkLabel(self, text=f"Start Time: {format_time(self.start_time)}")
        self.start_time_label.grid(row=5, column=0, columnspan=3, padx=20, pady=(10, 0), sticky="w")
        self.start_scrub_left_button = customtkinter.CTkButton(self, text="<", width=40, command=self.scrub_start_left)
        self.start_scrub_left_button.grid(row=6, column=0, padx=(20, 5), pady=(5, 10), sticky="w")
        self.start_slider = customtkinter.CTkSlider(self, from_=0, to=1.0, command=self.update_start_time)
        self.start_slider.grid(row=6, column=1, padx=5, pady=(5, 10), sticky="ew")
        self.start_scrub_right_button = customtkinter.CTkButton(self, text=">", width=40, command=self.scrub_start_right)
        self.start_scrub_right_button.grid(row=6, column=2, padx=(5, 20), pady=(5, 10), sticky="e")

        # End Time
        self.end_time_label = customtkinter.CTkLabel(self, text=f"End Time: {format_time(self.end_time)}")
        self.end_time_label.grid(row=7, column=0, columnspan=3, padx=20, pady=(10, 0), sticky="w")
        self.end_scrub_left_button = customtkinter.CTkButton(self, text="<", width=40, command=self.scrub_end_left)
        self.end_scrub_left_button.grid(row=8, column=0, padx=(20, 5), pady=(5, 20), sticky="w")
        self.end_slider = customtkinter.CTkSlider(self, from_=0, to=1.0, command=self.update_end_time)
        self.end_slider.grid(row=8, column=1, padx=5, pady=(5, 20), sticky="ew")
        self.end_scrub_right_button = customtkinter.CTkButton(self, text=">", width=40, command=self.scrub_end_right)
        self.end_scrub_right_button.grid(row=8, column=2, padx=(5, 20), pady=(5, 20), sticky="e")

        # --- Thumbnails (Row 9) ---
        self.thumb_frame = customtkinter.CTkFrame(self)
        self.thumb_frame.grid(row=9, column=0, columnspan=3, padx=20, pady=10, sticky="ew")
        self.thumb_frame.grid_columnconfigure(0, weight=1); self.thumb_frame.grid_columnconfigure(1, weight=1)
        self.start_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="Start Frame"); self.start_thumb_label_text.grid(row=0, column=0, pady=(5,2))
        self.start_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=None); self.start_thumb_label.grid(row=1, column=0, padx=10, pady=(0,10))
        self.end_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="End Frame"); self.end_thumb_label_text.grid(row=0, column=1, pady=(5,2))
        self.end_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=None); self.end_thumb_label.grid(row=1, column=1, padx=10, pady=(0,10))

        # --- Destination Selection (Row 10, 11) ---
        self.destination_label = customtkinter.CTkLabel(self, text="Destination:")
        self.destination_label.grid(row=10, column=0, columnspan=3, padx=20, pady=(10, 5), sticky="w")
        self.destination_combobox = customtkinter.CTkComboBox(self, values=[], command=self.on_destination_selected)
        self.destination_combobox.grid(row=11, column=0, columnspan=3, padx=20, pady=(0, 15), sticky="ew")

        # --- Status Label (Row 12) ---
        self.status_label = customtkinter.CTkLabel(self, text="", text_color="gray")
        self.status_label.grid(row=12, column=0, columnspan=3, padx=20, pady=5, sticky="ew")

        # --- Button Frame (Row 13) ---
        self.button_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.button_frame.grid(row=13, column=0, columnspan=3, padx=20, pady=(10, 20), sticky="ew")
        self.button_frame.grid_columnconfigure(0, weight=1); self.button_frame.grid_columnconfigure(1, weight=0)
        self.button_frame.grid_columnconfigure(2, weight=1); self.button_frame.grid_columnconfigure(3, weight=0)
        self.trim_button = customtkinter.CTkButton(self.button_frame, text="Trim", command=lambda: self.start_trim_thread(delete_original=False))
        self.trim_button.grid(row=0, column=1, padx=10, pady=5)
        self.trim_delete_button = customtkinter.CTkButton(self.button_frame, text="Trim & Delete", command=lambda: self.start_trim_thread(delete_original=True), fg_color="#D32F2F", hover_color="#B71C1C")
        self.trim_delete_button.grid(row=0, column=3, padx=10, pady=5)

        # --- Initial Load ---
        self.populate_location_dropdown() # Populate location first
        self.update_video_selection_dropdown() # Find videos in initial location
        self.display_placeholder_thumbnails()
        self.disable_ui_components() # Disable most UI until a video is loaded

        # --- Protocol Handler ---
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    # --- UI Update Functions ---
    def disable_ui_components(self, disable=True):
        """Disables or enables main UI components (sliders, thumbs, buttons)."""
        state = "disabled" if disable else "normal"
        # Keep track of widgets that are usually toggled together
        other_widgets_to_toggle = [
            self.start_slider, self.end_slider,
            self.start_scrub_left_button, self.start_scrub_right_button,
            self.end_scrub_left_button, self.end_scrub_right_button,
            self.trim_button, self.trim_delete_button,
            self.destination_combobox # Destination enabled/disabled with other controls
        ]

        # Disable/Enable the main controls
        for widget in other_widgets_to_toggle:
            if widget:
                 widget.configure(state=state)

        # Handle video combobox separately based on whether videos exist
        if disable:
            # Always disable video combobox when disabling everything else
            if self.video_combobox:
                self.video_combobox.configure(state="disabled")
            # Clear/reset other UI elements when disabling
            self.display_placeholder_thumbnails()
            self.file_info_display.configure(text="Select a video from the list above.")
            self.start_time_label.configure(text="Start Time: --:--:--.---")
            self.end_time_label.configure(text="End Time: --:--:--.---")
        else:
            # When enabling, only enable video combobox if there are videos
            if self.video_combobox:
                video_combo_state = "normal" if self.video_filenames else "disabled"
                self.video_combobox.configure(state=video_combo_state)
            # Destination combobox state was already handled in the loop above

            # If enabling fails because no video is loaded (video_path is None),
            # ensure sliders etc. remain disabled by calling again with disable=True
            if not self.video_path:
                 # Call recursively, but prevent infinite loop
                 # This case is unlikely if called correctly, but acts as a safeguard
                 print("Warning: disable_ui_components(False) called but no video loaded. Re-disabling non-selector controls.")
                 # Re-disable only the 'other' widgets
                 for widget in other_widgets_to_toggle:
                      if widget: widget.configure(state="disabled")
                 # Keep video combobox state as determined above
                 video_combo_state = "normal" if self.video_filenames else "disabled"
                 if self.video_combobox: self.video_combobox.configure(state=video_combo_state)


    def display_placeholder_thumbnails(self):
        """Displays gray boxes in the thumbnail labels."""
        try:
            ctk_placeholder = customtkinter.CTkImage(light_image=placeholder_img, dark_image=placeholder_img, size=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
            self.start_thumb_label.configure(image=ctk_placeholder, text=""); self.start_thumb_label.image = ctk_placeholder
            self.end_thumb_label.configure(image=ctk_placeholder, text=""); self.end_thumb_label.image = ctk_placeholder
        except Exception as e: print(f"Error displaying placeholder thumbnails: {e}")

    # --- Directory Handling ---
    def populate_location_dropdown(self):
        """Populates the Location dropdown with parents and Browse."""
        try:
            self.location_options = get_parent_directories(self.current_input_directory)
            display_options = self.location_options + [BROWSE_OPTION]
            self.location_combobox.configure(values=display_options)
            # Set default selection in dropdown
            if self.current_input_directory in self.location_options:
                 self.location_combobox.set(self.current_input_directory)
            elif display_options:
                 self.location_combobox.set(display_options[0]) # Fallback
        except Exception as e:
            print(f"Error populating location dropdown: {e}")
            self.location_combobox.configure(values=[BROWSE_OPTION])
            self.location_combobox.set(BROWSE_OPTION)


    def on_location_selected(self, selected_location_str):
        """Callback when a location is chosen."""
        if selected_location_str == BROWSE_OPTION:
            new_dir = tkinter.filedialog.askdirectory(initialdir=self.current_input_directory, title="Select Input Directory")
            if new_dir:
                norm_new_dir = os.path.normpath(new_dir)
                self.current_input_directory = norm_new_dir
                # Add newly browsed dir to options if not already present
                if norm_new_dir not in self.location_options:
                    self.location_options.insert(0, norm_new_dir) # Add to top for visibility
                self.populate_location_dropdown() # Re-populate to include new dir and set value
                self.update_video_selection_dropdown()
            else: # User cancelled browse
                self.location_combobox.set(self.current_input_directory) # Reset to current value
        elif selected_location_str and selected_location_str != self.current_input_directory:
            norm_selected_dir = os.path.normpath(selected_location_str)
            self.current_input_directory = norm_selected_dir
            self.update_video_selection_dropdown()
        elif not selected_location_str: # Handle empty selection if possible
             self.location_combobox.set(self.current_input_directory)


    def update_video_selection_dropdown(self):
        """Finds videos in the current input directory and updates the video dropdown."""
        self.update_status(f"Searching for videos in {os.path.basename(self.current_input_directory)}...", "gray")
        self.disable_ui_components(disable=True) # Disable UI while searching/loading
        self.video_path = None # Reset current video path

        self.recent_videos = find_recent_videos(self.current_input_directory, RECENT_FILES_COUNT)
        self.video_filenames = [os.path.basename(p) for p in self.recent_videos]

        if self.video_filenames:
            self.video_combobox.configure(values=self.video_filenames, state="normal")
            self.video_combobox.set(self.video_filenames[0]) # Select first video
            # Important: Call on_video_selected AFTER setting the value
            # This ensures the UI doesn't try to load data for an empty selection briefly
            self.after(10, lambda: self.on_video_selected(self.video_filenames[0])) # Small delay might help UI update
            self.update_status("") # Clear searching message
        else:
            self.video_combobox.configure(values=[], state="disabled") # Disable if no videos
            self.video_combobox.set("No videos found")
            self.disable_ui_components(disable=True) # Keep UI disabled
            self.update_status(f"No videos found in {os.path.basename(self.current_input_directory)}", "orange")
            # Ensure destination is also cleared/reset
            self.destination_combobox.configure(values=[BROWSE_OPTION], state="disabled")
            self.destination_combobox.set(BROWSE_OPTION)
            self.output_directory = None


    def update_destination_dropdown(self):
        """Updates the Destination dropdown based on current video path."""
        if not self.video_path:
             self.destination_combobox.configure(values=[BROWSE_OPTION], state="disabled")
             self.destination_combobox.set(BROWSE_OPTION); self.output_directory = None; return

        try:
            current_video_dir = os.path.dirname(self.video_path)
            self.destination_options = get_parent_directories(current_video_dir)
            display_options = self.destination_options + [BROWSE_OPTION]
            self.destination_combobox.configure(values=display_options, state="normal") # Enable

            # Set default selection to the video's directory
            if current_video_dir in self.destination_options:
                 self.destination_combobox.set(current_video_dir)
                 self.output_directory = current_video_dir
            elif self.destination_options: # Fallback to first parent if video dir itself failed (unlikely)
                 self.destination_combobox.set(self.destination_options[0])
                 self.output_directory = self.destination_options[0]
            else: # Only Browse is possible
                 self.destination_combobox.set(BROWSE_OPTION)
                 self.output_directory = None # No default dir selected yet
        except Exception as e:
            print(f"Error updating destination dropdown: {e}")
            self.destination_combobox.configure(values=[BROWSE_OPTION], state="disabled")
            self.destination_combobox.set(BROWSE_OPTION); self.output_directory = None


    def on_destination_selected(self, selected_dest_str):
        """Callback when a destination is chosen."""
        if selected_dest_str == BROWSE_OPTION:
            initial_browse_dir = os.path.dirname(self.video_path) if self.video_path else self.current_input_directory
            new_dir = tkinter.filedialog.askdirectory(initialdir=initial_browse_dir, title="Select Output Directory")
            if new_dir:
                norm_new_dir = os.path.normpath(new_dir)
                self.output_directory = norm_new_dir
                if norm_new_dir not in self.destination_options:
                     self.destination_options.insert(0, norm_new_dir)
                     display_options = self.destination_options + [BROWSE_OPTION]
                     self.destination_combobox.configure(values=display_options)
                self.destination_combobox.set(self.output_directory)
            else: # User cancelled browse
                 if self.output_directory and self.output_directory in self.destination_options: self.destination_combobox.set(self.output_directory)
                 else: # Fallback
                     current_video_dir = os.path.dirname(self.video_path) if self.video_path else None
                     if current_video_dir and current_video_dir in self.destination_options: self.destination_combobox.set(current_video_dir); self.output_directory = current_video_dir
                     elif self.destination_options: self.destination_combobox.set(self.destination_options[0]); self.output_directory = self.destination_options[0]
                     else: self.destination_combobox.set(BROWSE_OPTION); self.output_directory = None
        elif selected_dest_str: # Selected an existing path
            self.output_directory = os.path.normpath(selected_dest_str)
        else: # Handle empty selection if possible
             self.output_directory = None # Or fallback to video dir? Let's set to None
             current_video_dir = os.path.dirname(self.video_path) if self.video_path else None
             if current_video_dir and current_video_dir in self.destination_options: self.destination_combobox.set(current_video_dir)
             elif self.destination_options: self.destination_combobox.set(self.destination_options[0])
             else: self.destination_combobox.set(BROWSE_OPTION)

        print(f"Output directory set to: {self.output_directory}")

    # --- Video Loading & Info Update ---
    def on_video_selected(self, selected_filename):
        """Callback when a video is chosen from the dropdown."""
        if not selected_filename or selected_filename == "No videos found":
             self.video_path = None; self.disable_ui_components(disable=True); return

        print(f"Video selected: {selected_filename}")
        try:
            selected_index = self.video_filenames.index(selected_filename)
            new_video_path = self.recent_videos[selected_index]
            # Check if path is valid before loading
            if not os.path.exists(new_video_path):
                 self.update_status(f"Error: Selected video file not found:\n{new_video_path}", "red")
                 self.video_path = None; self.disable_ui_components(disable=True); return

            if new_video_path != self.video_path:
                 self.load_video_data(new_video_path)
            else:
                 print("Selected video is the same as current.")
                 # Ensure UI is enabled if selecting the same video again after potential disable
                 self.disable_ui_components(disable=False)
        except ValueError:
            print(f"Error: Could not find path for {selected_filename}")
            self.update_status("Error selecting video.", "red")
            self.video_path = None; self.disable_ui_components(disable=True)


    def load_video_data(self, video_path):
        """Loads metadata and updates UI for the given video path."""
        self.video_path = video_path
        if not self.video_path: self.disable_ui_components(disable=True); return

        self.update_status(f"Loading metadata for {os.path.basename(video_path)}...", "gray")
        self.display_placeholder_thumbnails()
        self.disable_ui_components(disable=True) # Disable while loading

        duration_new, creation_time_fmt, file_size_str, file_size_bytes = get_video_metadata(self.video_path)

        if duration_new is None:
             # Show error popup, but don't quit, just disable UI
             tkinter.messagebox.showerror("Metadata Error", f"Could not get metadata for:\n{os.path.basename(self.video_path)}\n\nIs FFmpeg/ffprobe installed and working?")
             self.update_status("Error loading metadata.", "red")
             self.video_path = None; self.disable_ui_components(disable=True); return

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

        # Update Destination Dropdown based on loaded video's dir
        self.update_destination_dropdown()

        # Enable UI and load thumbnails
        self.disable_ui_components(disable=False) # Enable UI now that data is loaded

        # Schedule start thumbnail (at exact start time)
        start_thumb_time = self.start_time # Usually 0.0
        self.schedule_thumbnail_update('start', start_thumb_time, immediate=True)

        # Schedule end thumbnail (slightly before the actual end if duration > 0)
        # Use a small offset (e.g., 0.1 sec) back from the full duration for the initial end thumb
        # Ensure it doesn't go before the start time.
        end_thumb_time = self.end_time # This should be self.duration at this point
        if end_thumb_time > 0.1: # Only adjust if duration is significant
            end_thumb_time = max(start_thumb_time + 0.01, end_thumb_time - 0.1) # Go back 0.1s, but not before start+epsilon

        self.schedule_thumbnail_update('end', end_thumb_time, immediate=True)


    def update_info_display(self):
        """Calculates estimates and updates the single file info display label."""
        est_duration_str = "N/A"; est_size_str = "N/A"
        if self.duration > 0 and self.original_size_bytes is not None:
             estimated_duration_sec = max(0, self.end_time - self.start_time)
             duration_ratio = estimated_duration_sec / self.duration if self.duration > 1e-9 else 0
             estimated_size = int(self.original_size_bytes * duration_ratio)
             est_duration_str = format_time(estimated_duration_sec)
             est_size_str = f"{format_size(estimated_size)} (approx.)"
        info_text = (f"File: {self.current_filename}\n"
                     f"Created: {self.current_creation_time}\n\n"
                     f"Duration: {self.current_duration_str}\n"
                     f"Estimated Duration: {est_duration_str}\n"
                     f"Size: {self.current_size_str}\n"
                     f"Estimated size: {est_size_str}")
        self.file_info_display.configure(text=info_text)

    # --- Slider/Scrub Update Handlers ---
    def update_start_time(self, value, from_scrub=False):
        """Callback when the start slider is moved OR scrubbed."""
        # Prevent updates if UI is disabled (e.g., during load)
        if self.start_slider.cget("state") == "disabled" and not from_scrub: return

        self.start_time = float(value)
        if self.start_time > self.end_time: self.start_time = self.end_time; self.start_slider.set(self.start_time) # Adjust slider too
        self.start_time_label.configure(text=f"Start Time: {format_time(self.start_time)}")
        self.schedule_thumbnail_update('start', self.start_time, immediate=from_scrub) # Immediate update if scrubbed
        self.update_info_display()

    def update_end_time(self, value, from_scrub=False):
        """Callback when the end slider is moved OR scrubbed."""
         # Prevent updates if UI is disabled (e.g., during load)
        if self.end_slider.cget("state") == "disabled" and not from_scrub: return

        self.end_time = float(value)
        if self.end_time < self.start_time: self.end_time = self.start_time; self.end_slider.set(self.end_time) # Adjust slider too
        self.end_time_label.configure(text=f"End Time: {format_time(self.end_time)}")
        self.schedule_thumbnail_update('end', self.end_time, immediate=from_scrub) # Immediate update if scrubbed
        self.update_info_display()

    def scrub_start_left(self):
        if self.start_slider.cget("state") == "disabled": return
        new_start = max(0, self.start_time - SCRUB_INCREMENT)
        self.start_slider.set(new_start)
        self.update_start_time(new_start, from_scrub=True)

    def scrub_start_right(self):
        if self.start_slider.cget("state") == "disabled": return
        new_start = min(self.end_time, self.start_time + SCRUB_INCREMENT) # Cannot go past end time
        self.start_slider.set(new_start)
        self.update_start_time(new_start, from_scrub=True)

    def scrub_end_left(self):
        if self.end_slider.cget("state") == "disabled": return
        new_end = max(self.start_time, self.end_time - SCRUB_INCREMENT) # Cannot go past start time
        self.end_slider.set(new_end)
        self.update_end_time(new_end, from_scrub=True)

    def scrub_end_right(self):
        if self.end_slider.cget("state") == "disabled": return
        new_end = min(self.duration, self.end_time + SCRUB_INCREMENT) # Cannot go past total duration
        self.end_slider.set(new_end)
        self.update_end_time(new_end, from_scrub=True)

    # --- Thumbnail Handling ---
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
        try: fd, temp_thumb_path = tempfile.mkstemp(suffix=".jpg", prefix=f"thumb_{thumb_type}_"); os.close(fd); print(f"Created temp file for thumbnail: {temp_thumb_path}")
        except Exception as e: print(f"Error creating temp thumb file: {e}"); self.update_status(f"Error creating temp file for {thumb_type} thumb.", "red"); return
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
                target_label.configure(image=ctk_image, text=""); target_label.image = ctk_image; print(f"Updated {thumb_type} thumbnail display.")
            except Exception as e:
                print(f"Error loading/displaying thumbnail {image_path}: {e}"); self.display_placeholder_thumbnails(); self.update_status(f"Error loading {thumb_type} thumbnail.", "red")
                if image_path in temp_files_to_cleanup: temp_files_to_cleanup.remove(image_path)
                if os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except OSError: pass
        else:
            print(f"Thumbnail extraction failed or file invalid for {thumb_type}. Path: {image_path}"); self.display_placeholder_thumbnails()
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except OSError: pass

    # --- Trimming Logic ---
    def start_trim_thread(self, delete_original=False):
        """Starts the trimming process after optional confirmation."""
        global temp_files_to_cleanup
        if self.is_processing: print("Already processing."); return
        if not self.video_path: self.update_status("No video selected.", "red"); return
        if not self.output_directory or not os.path.isdir(self.output_directory): self.update_status("Invalid output directory selected.", "red"); return
        if abs(self.end_time - self.start_time) < 0.1: self.update_status("Error: Start/End times too close.", "red"); return

        if delete_original:
            confirm = tkinter.messagebox.askyesno("Confirm Delete", f"Permanently delete the original file?\n\n{os.path.basename(self.video_path)}\n\nThis cannot be undone.", icon='warning')
            if not confirm: self.update_status("Trim & Delete cancelled.", "orange"); return

        self.is_processing = True; self.disable_ui_components(disable=True); self.trim_button.configure(state="disabled"); self.trim_delete_button.configure(state="disabled"); self.location_combobox.configure(state="disabled"); self.video_combobox.configure(state="disabled") # Disable dir selectors too
        self.update_status("Starting trim...", "blue")

        temp_output_path = None
        if delete_original:
            try: base, ext = os.path.splitext(os.path.basename(self.video_path)); temp_output_path = os.path.join(self.output_directory, f"{base}_temp_trim_{uuid.uuid4().hex}{ext}"); temp_files_to_cleanup.append(temp_output_path); print(f"Temp path for delete: {temp_output_path}")
            except Exception as e: print(f"Error generating temp filename: {e}"); self.update_status("Error preparing temp file.", "red"); self.reset_ui_after_processing(); return

        thread = threading.Thread(target=self.run_ffmpeg_trim, args=(delete_original, temp_output_path)); thread.daemon = True; thread.start()

    def run_ffmpeg_trim(self, delete_original, temp_output_path_for_delete):
        """Executes the ffmpeg command and handles optional deletion/renaming."""
        global temp_files_to_cleanup; final_output_path = None
        try:
            input_filename = self.video_path; base, ext = os.path.splitext(os.path.basename(input_filename))
            # Use self.output_directory for output
            if delete_original:
                output_filename = temp_output_path_for_delete; final_output_path = os.path.join(self.output_directory, os.path.basename(input_filename)) # Final path in new dir
                if not output_filename: raise ValueError("Temp output path missing.")
            else:
                output_filename_base = os.path.join(self.output_directory, f"{base}{TRIM_SUFFIX}{ext}"); output_filename = output_filename_base; counter = 1
                while os.path.exists(output_filename): output_filename = os.path.join(self.output_directory, f"{base}{TRIM_SUFFIX}_{counter}{ext}"); counter += 1
                final_output_path = output_filename

            start_str = format_time(self.start_time); trim_duration = max(0.1, self.end_time - self.start_time)
            command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', input_filename, '-ss', start_str, '-t', str(trim_duration), '-c', 'copy', '-map', '0', '-avoid_negative_ts', 'make_zero', '-y', output_filename]
            self.update_status("Processing with FFmpeg...", "blue"); print(f"Running FFmpeg command: {' '.join(command)}")

            startupinfo = None
            if platform.system() == 'Windows': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                print(f"FFmpeg OK. Output: {output_filename}")
                if delete_original:
                    self.update_status("Deleting original...", "blue"); time.sleep(0.5)
                    try:
                        print(f"Attempt delete: {input_filename}"); os.remove(input_filename); print(f"Delete OK: {input_filename}")
                        self.update_status("Renaming...", "blue"); time.sleep(0.5)
                        try:
                            # Ensure final path is unique before renaming
                            final_path_to_use = final_output_path; counter = 1
                            base_final, ext_final = os.path.splitext(final_output_path)
                            while os.path.exists(final_path_to_use): final_path_to_use = f"{base_final}_{counter}{ext_final}"; counter += 1
                            if final_path_to_use != final_output_path: print(f"Warning: Target filename existed, renaming to {os.path.basename(final_path_to_use)}")

                            print(f"Attempt rename: {output_filename} -> {final_path_to_use}"); os.rename(output_filename, final_path_to_use); print(f"Rename OK -> {final_path_to_use}")
                            if output_filename in temp_files_to_cleanup: temp_files_to_cleanup.remove(output_filename)
                            self.update_status("Trim & Delete successful!", "green"); self.after(100, lambda: self.post_trim_success(final_path_to_use))
                        except OSError as rename_err: error_message = f"RENAME FAILED: {rename_err}\nTrimmed video saved as:\n{os.path.basename(output_filename)}"; print(error_message); self.update_status(error_message, "red"); self.after(100, self.reset_ui_after_processing)
                    except OSError as delete_err: error_message = f"DELETE FAILED: {delete_err}\nOriginal NOT deleted.\nTrimmed video saved as:\n{os.path.basename(output_filename)}"; print(error_message); self.update_status(error_message, "red"); self.after(100, self.reset_ui_after_processing)
                else: self.update_status("Trim successful!", "green"); self.after(100, lambda: self.post_trim_success(final_output_path))
            else:
                error_message = f"FFmpeg failed (code {process.returncode}):\n{stderr[-500:]}"
                print(error_message)
                self.update_status(error_message, "red")
                
                if delete_original and output_filename and os.path.exists(output_filename):
                    print(f"FFmpeg failed, cleaning temp: {output_filename}")
                    try: os.remove(output_filename)
                    except OSError as e: print(f"Error cleaning failed temp: {e}")
                    if output_filename in temp_files_to_cleanup: temp_files_to_cleanup.remove(output_filename)
                self.after(100, self.reset_ui_after_processing)
        except Exception as e:
            error_message = f"Unexpected error during trim process: {e}"; print(error_message); self.update_status(error_message, "red")
            if delete_original and temp_output_path_for_delete and os.path.exists(temp_output_path_for_delete):
                try:
                    os.remove(temp_output_path_for_delete)
                except OSError as e:
                    print(f"Error cleaning temp after error: {e}")
                    if temp_output_path_for_delete in temp_files_to_cleanup: temp_files_to_cleanup.remove(temp_output_path_for_delete)
            self.after(100, self.reset_ui_after_processing)

    # --- Post-Trim & Cleanup ---
    def post_trim_success(self, output_filepath):
        """Actions after successful trim."""
        print(f"Trim process successful. Final file: {output_filepath}")
        open_file_explorer(output_filepath)
        self.update_status("Done! Closing...", "green")
        # Before closing, refresh the input directory view in case
        # the deleted/trimmed file affects the list
        self.after(100, self.update_video_selection_dropdown)
        self.after(1600, self.on_closing) # Slightly longer delay


    def reset_ui_after_processing(self):
        """Resets UI elements after processing."""
        self.is_processing = False
        # Always enable directory/video selectors
        self.location_combobox.configure(state="normal")
        self.video_combobox.configure(state="normal" if self.video_filenames else "disabled")
        # Enable other components only if a video is loaded
        if self.video_path: self.disable_ui_components(disable=False)
        else: self.disable_ui_components(disable=True)


    def update_status(self, message, color="gray"):
        """Updates the status label text and color."""
        def _update(): self.status_label.configure(text=message, text_color=color)
        self.after(0, _update)


    def show_error_and_quit(self, message):
        """Displays an error message box and quits."""
        print(f"FATAL ERROR: {message}")
        if not hasattr(self, 'title') or not self.winfo_exists(): root = tkinter.Tk(); root.withdraw(); tkinter.messagebox.showerror("Error", message); root.destroy()
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
    # --- Dependency Checks ---
    try: from PIL import Image, ImageTk
    except ImportError: print("ERROR: Pillow not found. Install: pip install Pillow"); sys.exit(1)
    try: from dateutil import parser as date_parser
    except ImportError: print("ERROR: python-dateutil not found. Install: pip install python-dateutil"); sys.exit(1)

    customtkinter.set_appearance_mode("System"); customtkinter.set_default_color_theme("blue")

    # --- Determine and Validate Initial Directory ---
    initial_dir = load_last_directory() # Try loading saved path first
    if initial_dir is None:
        initial_dir = INITIAL_VIDEO_DIRECTORY # Fallback to hardcoded value

    valid_initial_dir = False
    needs_user_selection = False

    # Check if the determined path is valid
    if initial_dir != 'path/to/your/video/clips' and os.path.isdir(initial_dir):
        valid_initial_dir = True
    else:
        needs_user_selection = True # Mark that we need to ask the user

    # If the directory wasn't valid, prompt the user
    if needs_user_selection:
        # Create a temporary root for the dialogs
        root = tkinter.Tk()
        root.withdraw() # Hide the root window

        message = ""
        if initial_dir == 'path/to/your/video/clips':
            message = "Welcome! Please select your starting video directory."
            tkinter.messagebox.showinfo("Setup", message)
        else: # Configured/saved directory doesn't exist
             message = f"Initial directory not found or invalid:\n{initial_dir}\n\nPlease select a valid directory."
             tkinter.messagebox.showwarning("Directory Not Found", message)

        # Ask the user to select a directory
        selected_dir = tkinter.filedialog.askdirectory(title="Select Starting Video Directory")

        if selected_dir and os.path.isdir(selected_dir):
            initial_dir = selected_dir # Use the selected directory
            valid_initial_dir = True
            print(f"Using selected initial directory: {initial_dir}")
            # --- SAVE the newly selected directory ---
            save_last_directory(initial_dir)
        else:
            tkinter.messagebox.showerror("Error", "No valid directory selected. Application cannot start.")
            valid_initial_dir = False

        root.destroy() # Clean up the temporary root

    # --- Launch App ---
    if valid_initial_dir:
        app = VideoTrimmerApp(initial_input_dir=initial_dir)
        if app and app.winfo_exists():
            app.mainloop()
        else:
            print("Application failed to initialize.")
            cleanup_temp_files()
            sys.exit(1)
    else:
        print("Application exiting due to invalid initial directory.")
        sys.exit(1)
