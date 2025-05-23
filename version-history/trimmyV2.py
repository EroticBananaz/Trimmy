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
from PIL import Image, ImageTk # Requires Pillow: pip install Pillow

# --- Configuration ---
# Set the directory to monitor for videos.
# IMPORTANT: Replace 'path/to/your/video/clips' with the actual path.
# Use forward slashes '/' even on Windows.
VIDEO_DIRECTORY = 'C:/obs/test'
# Supported video file extensions
VIDEO_EXTENSIONS = ('*.mp4', '*.mov', '*.avi', '*.mkv', '*.wmv', '*.flv')
# Number of recent files to list
RECENT_FILES_COUNT = 5
# Thumbnail settings
THUMBNAIL_WIDTH = 240
THUMBNAIL_HEIGHT = 135 # Approximate 16:9 aspect ratio
THUMBNAIL_UPDATE_DELAY_MS = 300 # Delay thumbnail update after slider stops moving
# --- End Configuration ---

# --- Global Variables ---
# To store references to temporary thumbnail files for cleanup
temp_thumbnail_files = []
# Placeholder image data (simple gray box)
placeholder_img = Image.new('RGB', (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), color = 'gray')

# --- Helper Functions ---

def format_time(seconds):
    """Converts seconds to HH:MM:SS.ms format."""
    if seconds is None or not isinstance(seconds, (int, float)) or seconds < 0:
        return "00:00:00.000"
    try:
        delta = datetime.timedelta(seconds=seconds)
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds_part = divmod(remainder, 60)
        milliseconds = int(delta.microseconds / 1000)
        return f"{hours:02}:{minutes:02}:{seconds_part:02}.{milliseconds:03}"
    except Exception: # Catch potential overflow or other errors
        return "00:00:00.000"


def get_video_metadata(file_path):
    """Gets video duration and other info using ffprobe."""
    if not file_path or not os.path.exists(file_path):
        print(f"Error: File not found - {file_path}")
        return None, None, None

    # Check if ffprobe exists (only needs to be done once ideally, but check here for safety)
    try:
        # Use STARTUPINFO for Windows to hide console window
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        subprocess.run(['ffprobe', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: ffprobe not found. Make sure FFmpeg (which includes ffprobe) is installed and in your system's PATH.")
        # Consider showing a pop-up error here as well if it's critical
        return None, None, None

    command = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        file_path
    ]
    try:
        # Use STARTUPINFO for Windows to hide console window
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
        metadata = json.loads(process.stdout)

        duration = None
        creation_time_str = None

        if 'format' in metadata and 'duration' in metadata['format']:
            try:
                duration = float(metadata['format']['duration'])
            except (ValueError, TypeError):
                print(f"Warning: Could not parse duration from metadata for {file_path}")
                duration = 0.0 # Default to 0 if parsing fails

        if 'format' in metadata and 'tags' in metadata['format'] and 'creation_time' in metadata['format']['tags']:
             creation_time_str = metadata['format']['tags']['creation_time']
        else:
            try:
                mtime = os.path.getmtime(file_path)
                creation_time_str = datetime.datetime.fromtimestamp(mtime).isoformat() + 'Z'
            except Exception:
                 creation_time_str = "N/A"

        try:
            file_size_bytes = os.path.getsize(file_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            file_size_str = f"{file_size_mb:.2f} MB"
        except OSError:
            file_size_str = "N/A"

        return duration, creation_time_str, file_size_str

    except subprocess.CalledProcessError as e:
        print(f"Error running ffprobe: {e}")
        print(f"Stderr: {e.stderr}")
        return None, None, None
    except json.JSONDecodeError as e:
        print(f"Error parsing ffprobe JSON output: {e}")
        print(f"Output was: {process.stdout}")
        return None, None, None
    except Exception as e:
        print(f"An unexpected error occurred while getting metadata: {e}")
        return None, None, None


def find_recent_videos(directory, count):
    """Finds the most recently modified video files in the specified directory."""
    if not os.path.isdir(directory):
        print(f"Error: Directory not found - {directory}")
        return []

    all_videos = []
    for ext in VIDEO_EXTENSIONS:
        # Use recursive=False if you don't want to search subdirectories
        all_videos.extend(glob.glob(os.path.join(directory, ext)))

    if not all_videos:
        print(f"No video files found in {directory}")
        return []

    try:
        # Sort files by modification time, newest first
        all_videos.sort(key=os.path.getmtime, reverse=True)
        return all_videos[:count] # Return the top 'count' files
    except Exception as e:
        print(f"Error sorting or finding recent files: {e}")
        return []

def extract_thumbnail(video_path, time_seconds, output_path):
    """Extracts a single frame from the video at the specified time using ffmpeg."""
    if not video_path or not os.path.exists(video_path):
        print(f"Thumbnail Error: Input video not found - {video_path}")
        return False

    # Check if ffmpeg exists
    try:
        # Use STARTUPINFO for Windows to hide console window
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: ffmpeg not found. Is it installed and in PATH?")
        return False

    time_str = format_time(time_seconds) # Use formatted time for -ss

    command = [
        'ffmpeg',
        '-ss', time_str,    # Seek to the specified time
        '-i', video_path,
        '-frames:v', '1',   # Extract only one video frame
        '-q:v', '3',        # Quality scale for JPG (1=best, 31=worst, 2-5 is good)
        '-vf', f'scale={THUMBNAIL_WIDTH}:-1', # Scale width, maintain aspect ratio
        '-y',               # Overwrite output file if it exists
        output_path
    ]

    try:
        # Use STARTUPINFO for Windows to hide console window
        startupinfo = None
        if platform.system() == 'Windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        print(f"Extracting thumbnail: {' '.join(command)}") # Log command
        process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
        print(f"Thumbnail extracted successfully to {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error extracting thumbnail: {e}")
        print(f"Stderr: {e.stderr}")
        # Clean up potentially corrupted output file
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        return False
    except Exception as e:
        print(f"An unexpected error occurred during thumbnail extraction: {e}")
        if os.path.exists(output_path):
             try:
                 os.remove(output_path)
             except OSError:
                 pass
        return False

def open_file_explorer(path):
    """Opens the file explorer to the specified path."""
    try:
        norm_path = os.path.normpath(path)
        if platform.system() == "Windows":
            # Best way for Windows, opens folder and selects file if path is a file
            subprocess.run(['explorer', '/select,', norm_path], check=True)
            # If path is just a directory, open it
            # os.startfile(norm_path) # Alternative, might just open the dir
        elif platform.system() == "Darwin": # macOS
            subprocess.run(['open', '-R', norm_path], check=True) # Reveals file in Finder
        else: # Linux and other Unix-like
             # Try to open the directory containing the file/path
             dir_path = os.path.dirname(norm_path) if os.path.isfile(norm_path) else norm_path
             subprocess.run(['xdg-open', dir_path], check=True)
    except FileNotFoundError:
         print(f"Error: Could not open file explorer. Command not found.")
    except subprocess.CalledProcessError as e:
         print(f"Error opening file explorer: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while opening the file explorer: {e}")


def cleanup_temp_files():
    """Deletes temporary thumbnail files."""
    global temp_thumbnail_files
    print("Cleaning up temporary files...")
    for f in temp_thumbnail_files:
        try:
            if os.path.exists(f):
                os.remove(f)
                print(f"Removed: {f}")
        except OSError as e:
            print(f"Error removing temp file {f}: {e}")
    temp_thumbnail_files = [] # Clear the list


# --- Main Application Class ---

class VideoTrimmerApp(customtkinter.CTk):
    def __init__(self, recent_video_paths):
        super().__init__()

        if not recent_video_paths:
            self.show_error_and_quit("No recent video files found in the specified directory.")
            return

        self.recent_videos = recent_video_paths # Store full paths
        self.video_path = self.recent_videos[0] # Default to the most recent
        self.video_filenames = [os.path.basename(p) for p in self.recent_videos] # For display

        self.duration = 0.0
        self.start_time = 0.0
        self.end_time = 0.0
        self.is_processing = False
        self.start_thumb_job = None # For debouncing thumbnail updates
        self.end_thumb_job = None   # For debouncing thumbnail updates

        # --- Configure Window ---
        self.title("Video Trimmer V2")
        self.geometry("650x650") # Increased size for thumbnails
        self.resizable(False, False)
        # Center the window
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        size = tuple(int(_) for _ in self.geometry().split('+')[0].split('x'))
        x = screen_width/2 - size[0]/2
        y = screen_height/2 - size[1]/2 - 50 # Move up slightly
        self.geometry("+%d+%d" % (x, y))

        # --- Create UI Elements ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1) # Two columns for thumbnails

        # Video Selection Dropdown
        self.video_select_label = customtkinter.CTkLabel(self, text="Select Video:")
        self.video_select_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 5), sticky="w")

        self.video_combobox = customtkinter.CTkComboBox(self, values=self.video_filenames, command=self.on_video_selected)
        self.video_combobox.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 15), sticky="ew")
        self.video_combobox.set(self.video_filenames[0]) # Set default selection

        # File Info Display (uses a frame for better layout)
        self.info_frame = customtkinter.CTkFrame(self)
        self.info_frame.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 15), sticky="ew")
        self.info_frame.grid_columnconfigure(0, weight=1)

        self.info_label = customtkinter.CTkLabel(self.info_frame, text="File Information:", font=customtkinter.CTkFont(weight="bold"), anchor="w")
        self.info_label.grid(row=0, column=0, padx=10, pady=(5, 0), sticky="w")

        self.file_info_display = customtkinter.CTkLabel(self.info_frame, text="Loading...", justify=tkinter.LEFT, anchor="w")
        self.file_info_display.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")


        # Start Time Slider & Label
        self.start_time_label = customtkinter.CTkLabel(self, text=f"Start Time: {format_time(self.start_time)}")
        self.start_time_label.grid(row=3, column=0, columnspan=2, padx=20, pady=(10, 0), sticky="w")

        self.start_slider = customtkinter.CTkSlider(self, from_=0, to=1.0, command=self.update_start_time) # Initial range, updated later
        self.start_slider.set(0)
        self.start_slider.grid(row=4, column=0, columnspan=2, padx=20, pady=(5, 10), sticky="ew")

        # End Time Slider & Label
        self.end_time_label = customtkinter.CTkLabel(self, text=f"End Time: {format_time(self.end_time)}")
        self.end_time_label.grid(row=5, column=0, columnspan=2, padx=20, pady=(10, 0), sticky="w")

        self.end_slider = customtkinter.CTkSlider(self, from_=0, to=1.0, command=self.update_end_time) # Initial range, updated later
        self.end_slider.set(1.0)
        self.end_slider.grid(row=6, column=0, columnspan=2, padx=20, pady=(5, 20), sticky="ew")

        # Thumbnail Display Area
        self.thumb_frame = customtkinter.CTkFrame(self)
        self.thumb_frame.grid(row=7, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.thumb_frame.grid_columnconfigure(0, weight=1)
        self.thumb_frame.grid_columnconfigure(1, weight=1)

        self.start_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="Start Frame")
        self.start_thumb_label_text.grid(row=0, column=0, pady=(5,2))
        self.start_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=None) # Placeholder for image
        self.start_thumb_label.grid(row=1, column=0, padx=10, pady=(0,10))

        self.end_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="End Frame")
        self.end_thumb_label_text.grid(row=0, column=1, pady=(5,2))
        self.end_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=None) # Placeholder for image
        self.end_thumb_label.grid(row=1, column=1, padx=10, pady=(0,10))

        # Status Label
        self.status_label = customtkinter.CTkLabel(self, text="", text_color="gray")
        self.status_label.grid(row=8, column=0, columnspan=2, padx=20, pady=5, sticky="ew")

        # Trim Button
        self.trim_button = customtkinter.CTkButton(self, text="Trim Video", command=self.start_trim_thread)
        self.trim_button.grid(row=9, column=0, columnspan=2, padx=20, pady=(10, 20))

        # --- Initial Load ---
        self.load_video_data(self.video_path) # Load data for the default video
        self.display_placeholder_thumbnails() # Show placeholders initially

        # --- Protocol Handler ---
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def display_placeholder_thumbnails(self):
        """Displays gray boxes in the thumbnail labels."""
        try:
            ctk_placeholder = customtkinter.CTkImage(light_image=placeholder_img, dark_image=placeholder_img, size=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
            self.start_thumb_label.configure(image=ctk_placeholder, text="")
            self.start_thumb_label.image = ctk_placeholder # Keep reference
            self.end_thumb_label.configure(image=ctk_placeholder, text="")
            self.end_thumb_label.image = ctk_placeholder # Keep reference
        except Exception as e:
            print(f"Error displaying placeholder thumbnails: {e}")


    def load_video_data(self, video_path):
        """Loads metadata and updates UI for the given video path."""
        self.video_path = video_path
        self.update_status(f"Loading metadata for {os.path.basename(video_path)}...", "gray")
        self.display_placeholder_thumbnails() # Show placeholders while loading

        duration_new, creation_time, file_size = get_video_metadata(self.video_path)

        if duration_new is None:
             self.show_error_and_quit(f"Could not get metadata for:\n{os.path.basename(self.video_path)}\n\nIs FFmpeg/ffprobe installed and in PATH?")
             return # Should quit, but return just in case

        self.duration = duration_new
        # Reset times and sliders
        self.start_time = 0.0
        self.end_time = self.duration if self.duration > 0 else 1.0 # Avoid 0 duration range

        # Update sliders' range and value
        # Need to handle duration being potentially 0 or very small
        slider_max = max(self.duration, 0.1) # Ensure slider range is at least 0.1
        self.start_slider.configure(to=slider_max)
        self.start_slider.set(0)
        self.end_slider.configure(to=slider_max)
        self.end_slider.set(slider_max) # Set to actual max value

        # Update labels
        self.start_time_label.configure(text=f"Start Time: {format_time(self.start_time)}")
        self.end_time_label.configure(text=f"End Time: {format_time(self.end_time)}")

        # Update file info display
        file_info_text = (
            f"File: {os.path.basename(self.video_path)}\n"
            f"Duration: {format_time(self.duration)}\n"
            f"Created: {creation_time if creation_time else 'N/A'}\n"
            f"Size: {file_size if file_size else 'N/A'}"
        )
        self.file_info_display.configure(text=file_info_text)
        self.update_status("") # Clear loading message

        # Load initial thumbnails for the new video
        self.schedule_thumbnail_update('start', self.start_time, immediate=True)
        self.schedule_thumbnail_update('end', self.end_time, immediate=True)


    def on_video_selected(self, selected_filename):
        """Callback when a video is chosen from the dropdown."""
        print(f"Video selected: {selected_filename}")
        # Find the full path corresponding to the selected filename
        try:
            selected_index = self.video_filenames.index(selected_filename)
            new_video_path = self.recent_videos[selected_index]
            # Check if it's actually different before reloading everything
            if new_video_path != self.video_path:
                 self.load_video_data(new_video_path)
            else:
                 print("Selected video is the same as current.")
        except ValueError:
            print(f"Error: Could not find path for selected filename {selected_filename}")
            self.update_status("Error selecting video.", "red")


    def update_start_time(self, value):
        """Callback when the start slider is moved."""
        self.start_time = float(value)
        if self.start_time > self.end_time:
            self.start_time = self.end_time
            self.start_slider.set(self.start_time)

        self.start_time_label.configure(text=f"Start Time: {format_time(self.start_time)}")
        # Schedule thumbnail update with debounce
        self.schedule_thumbnail_update('start', self.start_time)

    def update_end_time(self, value):
        """Callback when the end slider is moved."""
        self.end_time = float(value)
        if self.end_time < self.start_time:
            self.end_time = self.start_time
            self.end_slider.set(self.end_time)

        self.end_time_label.configure(text=f"End Time: {format_time(self.end_time)}")
        # Schedule thumbnail update with debounce
        self.schedule_thumbnail_update('end', self.end_time)


    def schedule_thumbnail_update(self, thumb_type, time_sec, immediate=False):
        """Schedules or cancels thumbnail extraction using self.after for debouncing."""
        if thumb_type == 'start':
            if self.start_thumb_job:
                self.after_cancel(self.start_thumb_job) # Cancel pending job
            if immediate:
                 self.generate_and_display_thumbnail(thumb_type, time_sec)
            else:
                 self.start_thumb_job = self.after(THUMBNAIL_UPDATE_DELAY_MS,
                                                   lambda t=thumb_type, s=time_sec: self.generate_and_display_thumbnail(t, s))
        elif thumb_type == 'end':
            if self.end_thumb_job:
                self.after_cancel(self.end_thumb_job) # Cancel pending job
            if immediate:
                 self.generate_and_display_thumbnail(thumb_type, time_sec)
            else:
                 self.end_thumb_job = self.after(THUMBNAIL_UPDATE_DELAY_MS,
                                                 lambda t=thumb_type, s=time_sec: self.generate_and_display_thumbnail(t, s))


    def generate_and_display_thumbnail(self, thumb_type, time_seconds):
        """Extracts thumbnail and updates the corresponding UI label."""
        global temp_thumbnail_files
        if not self.video_path: return

        # Create a temporary file path for the thumbnail
        try:
            # Use NamedTemporaryFile to get a path, close it, then let ffmpeg write to it.
            # Suffix is important for Pillow/Tkinter later.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", prefix=f"thumb_{thumb_type}_") as temp_file:
                temp_thumb_path = temp_file.name
            print(f"Attempting to generate thumbnail at path: {temp_thumb_path}") # Debug print
            temp_thumbnail_files.append(temp_thumb_path) # Add to list for cleanup

        except Exception as e:
            print(f"Error creating temporary file for thumbnail: {e}")
            self.update_status(f"Error creating temp file for {thumb_type} thumb.", "red")
            return

        # Run ffmpeg extraction in a separate thread to avoid blocking UI
        thread = threading.Thread(target=self._run_thumbnail_extraction, args=(thumb_type, time_seconds, temp_thumb_path))
        thread.daemon = True
        thread.start()

    def _run_thumbnail_extraction(self, thumb_type, time_seconds, temp_thumb_path):
        """Worker function for thumbnail extraction thread."""
        success = extract_thumbnail(self.video_path, time_seconds, temp_thumb_path)

        # Schedule UI update back on the main thread
        self.after(0, self._update_thumbnail_label, thumb_type, temp_thumb_path, success)

    def _update_thumbnail_label(self, thumb_type, image_path, success):
        """Updates the CTkLabel with the new thumbnail image (runs in main thread)."""
        target_label = self.start_thumb_label if thumb_type == 'start' else self.end_thumb_label

        if success and os.path.exists(image_path) and os.path.getsize(image_path) > 0:
            try:
                # Open with Pillow and create CTkImage
                pil_image = Image.open(image_path)
                # Resize if needed (FFmpeg scaling might not be perfect)
                pil_image.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)

                ctk_image = customtkinter.CTkImage(light_image=pil_image, dark_image=pil_image, size=(pil_image.width, pil_image.height))

                target_label.configure(image=ctk_image, text="")
                target_label.image = ctk_image # Keep a reference! Important!
                print(f"Updated {thumb_type} thumbnail display.")

            except Exception as e:
                print(f"Error loading or displaying thumbnail {image_path}: {e}")
                # Display placeholder if loading fails
                self.display_placeholder_thumbnails() # Reset both for simplicity
                self.update_status(f"Error loading {thumb_type} thumbnail.", "red")
        else:
            print(f"Thumbnail extraction failed or file invalid for {thumb_type}. Path: {image_path}")
            # Display placeholder if extraction failed
            self.display_placeholder_thumbnails() # Reset both for simplicity
            # Optionally keep the failed temp path in the list for cleanup attempt later


    def start_trim_thread(self):
        """Starts the trimming process in a separate thread."""
        if self.is_processing:
            print("Already processing.")
            return

        if abs(self.end_time - self.start_time) < 0.1:
             self.update_status("Error: Start and End times are too close.", "red")
             return

        self.is_processing = True
        self.trim_button.configure(state="disabled", text="Processing...")
        self.start_slider.configure(state="disabled")
        self.end_slider.configure(state="disabled")
        self.video_combobox.configure(state="disabled") # Disable dropdown during processing
        self.update_status("Starting trim...", "blue")

        thread = threading.Thread(target=self.run_ffmpeg_trim)
        thread.daemon = True
        thread.start()

    def run_ffmpeg_trim(self):
        """Executes the ffmpeg command for trimming."""
        try:
            # Use STARTUPINFO for Windows to hide console window
            startupinfo = None
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            # Check ffmpeg version (redundant if checked elsewhere, but safe)
            subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)

            input_filename = self.video_path
            output_dir = os.path.dirname(input_filename)
            base, ext = os.path.splitext(os.path.basename(input_filename))
            output_filename_base = os.path.join(output_dir, f"{base}_trimmed{ext}")
            output_filename = output_filename_base

            # Ensure output filename is unique
            counter = 1
            while os.path.exists(output_filename):
                 output_filename = os.path.join(output_dir, f"{base}_trimmed_{counter}{ext}")
                 counter += 1

            start_str = format_time(self.start_time)
            trim_duration = self.end_time - self.start_time

            # Command using -ss, -t, and -c copy
            command = [
                'ffmpeg',
                '-i', input_filename,
                '-ss', start_str,
                '-t', str(trim_duration),
                '-c', 'copy',
                '-map', '0',
                '-avoid_negative_ts', 'make_zero', # Often helpful with -c copy
                '-y', # Although we make unique names, -y prevents prompts on potential overwrites if logic fails
                output_filename
            ]

            self.update_status("Processing with FFmpeg...", "blue")
            print(f"Running FFmpeg command: {' '.join(command)}")

            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                self.update_status("Trim successful!", "green")
                print("FFmpeg finished successfully.")
                self.after(100, lambda: self.post_trim_success(output_filename)) # Pass output filename
            else:
                error_message = f"FFmpeg error (code {process.returncode}):\n{stderr[-500:]}"
                self.update_status(error_message, "red")
                print(error_message)
                self.after(100, self.reset_ui_after_processing)

        except FileNotFoundError:
             error_message = "Error: ffmpeg not found. Is it installed and in PATH?"
             self.update_status(error_message, "red")
             print(error_message)
             self.after(100, self.reset_ui_after_processing)
        except subprocess.CalledProcessError as e:
             error_message = f"Error checking/running ffmpeg: {e}"
             self.update_status(error_message, "red")
             print(error_message)
             self.after(100, self.reset_ui_after_processing)
        except Exception as e:
            error_message = f"An unexpected error occurred during trimming: {e}"
            self.update_status(error_message, "red")
            print(error_message)
            self.after(100, self.reset_ui_after_processing)


    def post_trim_success(self, output_filepath):
        """Actions after successful trim."""
        # Open file explorer, revealing the *newly created* file
        open_file_explorer(output_filepath)

        self.update_status("Done! Closing...", "green")
        self.after(1500, self.on_closing)


    def reset_ui_after_processing(self):
        """Resets UI elements after processing (usually on failure)."""
        self.is_processing = False
        self.trim_button.configure(state="normal", text="Trim Video")
        self.start_slider.configure(state="normal")
        self.end_slider.configure(state="normal")
        self.video_combobox.configure(state="normal") # Re-enable dropdown


    def update_status(self, message, color="gray"):
        """Updates the status label text and color."""
        def _update():
            self.status_label.configure(text=message, text_color=color)
        self.after(0, _update)


    def show_error_and_quit(self, message):
        """Displays an error message box and quits the application."""
        print(f"ERROR: {message}") # Log error
        # Ensure Tkinter root is initialized if called early
        if not hasattr(self, 'title') or not self.winfo_exists():
            root = tkinter.Tk()
            root.withdraw()
            tkinter.messagebox.showerror("Error", message)
            root.destroy()
        else:
            tkinter.messagebox.showerror("Error", message)
            self.destroy() # Destroy the main window if it exists
        cleanup_temp_files() # Attempt cleanup before exiting
        sys.exit(1) # Exit script with error code


    def on_closing(self):
        """Handles the window closing event."""
        print("Closing application.")
        cleanup_temp_files() # Clean up temp files on exit
        self.destroy()
        # sys.exit() # No need for sys.exit() here, destroy() handles it


# --- Script Entry Point ---
if __name__ == "__main__":
    # Check Pillow Installation
    try:
        from PIL import Image, ImageTk
    except ImportError:
         root = tkinter.Tk()
         root.withdraw()
         tkinter.messagebox.showerror("Dependency Error", "Pillow library not found.\nPlease install it by running: pip install Pillow")
         root.destroy()
         sys.exit("Dependency Error: Pillow not found.")

    customtkinter.set_appearance_mode("System")
    customtkinter.set_default_color_theme("blue")

    # --- Validate Configuration ---
    if VIDEO_DIRECTORY == 'path/to/your/video/clips':
         root = tkinter.Tk()
         root.withdraw()
         tkinter.messagebox.showerror("Configuration Needed", "Please edit the script and set the 'VIDEO_DIRECTORY' variable.")
         root.destroy()
         sys.exit("Configuration Error: VIDEO_DIRECTORY not set.")

    if not os.path.isdir(VIDEO_DIRECTORY):
         root = tkinter.Tk()
         root.withdraw()
         tkinter.messagebox.showerror("Error", f"VIDEO_DIRECTORY does not exist:\n{VIDEO_DIRECTORY}")
         root.destroy()
         sys.exit(f"Directory not found: {VIDEO_DIRECTORY}")

    # --- Find Videos and Launch App ---
    recent_videos = find_recent_videos(VIDEO_DIRECTORY, RECENT_FILES_COUNT)

    if recent_videos:
        print(f"Found {len(recent_videos)} recent videos.")
        app = VideoTrimmerApp(recent_videos)
        if app.winfo_exists():
             app.mainloop()
        else:
             print("Application failed to initialize.")
    else:
        root = tkinter.Tk()
        root.withdraw()
        tkinter.messagebox.showinfo("No Videos", f"No video files found in:\n{VIDEO_DIRECTORY}")
        root.destroy()
        sys.exit(f"No videos found in {VIDEO_DIRECTORY}")
