import tkinter
import tkinter.filedialog
import tkinter.messagebox
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
import tempfile
import uuid
from PIL import Image
from dateutil import parser as date_parser

# --- Configuration & Global Variables ---
INITIAL_VIDEO_DIRECTORY = '' # Effectively unused now that we load from config or prompt
VIDEO_EXTENSIONS = ('*.mp4', '*.mov', '*.avi', '*.mkv', '*.wmv', '*.flv')
RECENT_FILES_COUNT = 5
THUMBNAIL_WIDTH = 320
THUMBNAIL_HEIGHT = 180
THUMBNAIL_UPDATE_DELAY_MS = 300
TRIM_SUFFIX = "_trimmy"
SCRUB_INCREMENT = 0.5
temp_files_to_cleanup = []
BROWSE_OPTION = "Browse..."
STATUS_MESSAGE_CLEAR_DELAY_MS = 5000
FILENAME_INVALID_CHARS = r'/\:*?"<>|'
CONFIG_FILENAME = "config.json"
INITIAL_LOCATION_PROMPT = "Click to Select Video Directory..."

# --- Helper Functions ---
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
    # Check to prevent infinite loop if size_bytes is extremely large or NaN/inf
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
    config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                last_dir = config.get("last_input_directory")
                if last_dir and os.path.isdir(last_dir):
                    print(f"Loaded last directory from config: {last_dir}")
                    return last_dir
                else: print("Config found, but last directory is invalid or missing.")
    except (json.JSONDecodeError, IOError, Exception) as e: print(f"Error loading config file ({config_path}): {e}")
    print("No valid last directory found in config or config does not exist.")
    return None

def save_last_directory(directory_path):
    config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
    config_data = {}
    # Load existing config to preserve other settings, like recent_input_directories
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load existing config to save last directory: {e}")
            config_data = {} # Start fresh if unreadable

    config_data["last_input_directory"] = directory_path
    try:
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=4)
        print(f"Saved last directory to config: {directory_path}")
        return True
    except (IOError, Exception) as e:
        print(f"Error saving config file ({config_path}): {e}")
        return False

def get_video_metadata(file_path):
    if not file_path or not os.path.exists(file_path): print(f"Error: File not found - {file_path}"); return None, None, None, None
    try:
        startupinfo = None
        if platform.system() == 'Windows': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffprobe', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    except (FileNotFoundError, subprocess.CalledProcessError): print("Error: ffprobe not found."); tkinter.messagebox.showerror("Error", "ffprobe (part of FFmpeg) not found in system PATH.\nPlease install FFmpeg and ensure it's added to PATH."); return None, None, None, None
    command = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
    try:
        startupinfo = None
        if platform.system() == 'Windows': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
        metadata = json.loads(process.stdout)
        duration = 0.0; creation_time_str_formatted = "N/A"; file_size_str = "N/A"; file_size_bytes = None; creation_time_tag = None
        if 'format' in metadata:
            if 'duration' in metadata['format']:
                try: duration = float(metadata['format']['duration'])
                except (ValueError, TypeError): duration = 0.0
            if 'tags' in metadata['format'] and 'creation_time' in metadata['format']['tags']:
                 creation_time_tag = metadata['format']['tags']['creation_time']
                 try:
                     dt_object = date_parser.isoparse(creation_time_tag)
                     dt_object = dt_object.astimezone(None) if dt_object.tzinfo else dt_object
                     creation_time_str_formatted = dt_object.strftime('%m/%d/%y %H:%M')
                 except ValueError as e: print(f"Warning: Could not parse tag '{creation_time_tag}': {e}."); creation_time_tag = None
            if 'size' in metadata['format']:
                try: file_size_bytes = int(metadata['format']['size'])
                except (ValueError, TypeError): pass
        if creation_time_tag is None:
             try:
                 mtime = os.path.getmtime(file_path)
                 dt_object = datetime.datetime.fromtimestamp(mtime)
                 creation_time_str_formatted = dt_object.strftime('%m/%d/%y %H:%M')
             except Exception as e: print(f"Warning: Could not get file mod time: {e}"); creation_time_str_formatted = "N/A"
        if file_size_bytes is None:
            try: file_size_bytes = os.path.getsize(file_path)
            except OSError as e: print(f"Warning: Could not get file size: {e}"); file_size_bytes = None
        if file_size_bytes is not None: file_size_str = format_size(file_size_bytes)
        return duration, creation_time_str_formatted, file_size_str, file_size_bytes
    except subprocess.CalledProcessError as e: print(f"ffprobe error: {e}\n{e.stderr}"); return None, None, None, None
    except json.JSONDecodeError as e: print(f"ffprobe JSON error: {e}\n{process.stdout if hasattr(process, 'stdout') else 'No stdout'}"); return None, None, None, None
    except Exception as e: print(f"Metadata error: {e}"); return None, None, None, None

def find_recent_videos(directory, count):
    if not directory or not os.path.isdir(directory): print(f"Video search dir invalid: {directory}"); return []
    all_videos = []
    for ext_pattern in VIDEO_EXTENSIONS:
        all_videos.extend(glob.glob(os.path.join(directory, ext_pattern)))
    if not all_videos: print(f"No videos found in {directory}"); return []
    try: all_videos.sort(key=os.path.getmtime, reverse=True); return all_videos[:count]
    except Exception as e: print(f"Error sorting videos: {e}"); return []

def extract_thumbnail(video_path, time_seconds, output_path):
    global temp_files_to_cleanup
    if not video_path or not os.path.exists(video_path): print(f"Thumb Error: Input not found - {video_path}"); return False
    try:
        startupinfo = None
        if platform.system() == 'Windows': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
    except (FileNotFoundError, subprocess.CalledProcessError): print("Error: ffmpeg not found."); tkinter.messagebox.showerror("Error", "ffmpeg not found in system PATH.\nPlease install FFmpeg and ensure it's added to PATH."); return False
    valid_time_seconds = max(0, time_seconds) if isinstance(time_seconds, (int, float)) else 0
    time_str = format_time(valid_time_seconds).split('.')[0]
    command = ['ffmpeg', '-ss', time_str, '-i', video_path, '-frames:v', '1', '-q:v', '3',
               '-vf', f'scale={THUMBNAIL_WIDTH}:-1:force_original_aspect_ratio=decrease,crop={THUMBNAIL_WIDTH}:{THUMBNAIL_HEIGHT}',
               '-y', output_path]
    try:
        startupinfo = None
        if platform.system() == 'Windows': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            if output_path not in temp_files_to_cleanup: # Ensure no duplicates
                temp_files_to_cleanup.append(output_path)
            return True
        else:
            print(f"Error extracting thumbnail: Output file not created or empty. Command: {' '.join(command)}")
            if os.path.exists(output_path): os.remove(output_path)
            return False
    except subprocess.CalledProcessError as e:
        print(f"Error extracting thumbnail: {e}\nStderr: {e.stderr}\nCommand: {' '.join(command)}")
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except OSError: pass
        return False
    except Exception as e:
        print(f"An unexpected error during thumbnail extraction: {e}\nCommand: {' '.join(command)}")
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except OSError: pass
        return False

def cleanup_temp_files():
    global temp_files_to_cleanup
    print("Cleaning up temporary files..."); cleaned_count = 0; errors = 0
    # Iterate over a copy of the list if modifying it
    for f in list(temp_files_to_cleanup):
        try:
            if f and os.path.exists(f): os.remove(f); cleaned_count +=1
        except OSError as e: print(f"Error removing temp file {f}: {e}"); errors += 1
        except Exception as e: print(f"Unexpected error removing temp file {f}: {e}"); errors += 1
        finally:
             if f in temp_files_to_cleanup: temp_files_to_cleanup.remove(f)
    print(f"Cleanup finished. Removed {cleaned_count} files, {errors} errors."); temp_files_to_cleanup = []


# --- CustomFilenameDialog Class ---
class CustomFilenameDialog(customtkinter.CTkToplevel):
    def __init__(self, parent, title="Set Output Filename"):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.lift()
        self.grab_set()
        self.result = None
        _dialog_width = 350
        self.label = customtkinter.CTkLabel(self, text="Enter filename (no extension, .mp4 will be added):")
        self.label.pack(padx=20, pady=(20, 10))
        self.entry_var = tkinter.StringVar()
        self.entry_var.trace_add("write", self._validate_input)
        self.entry = customtkinter.CTkEntry(self, textvariable=self.entry_var, width=int(_dialog_width * 0.8))
        self.entry.pack(padx=20, pady=(0, 5))
        self.entry.focus_set()
        self.error_label = customtkinter.CTkLabel(self, text="", text_color="red", height=10)
        self.error_label.pack(padx=20, pady=(0, 10))
        self.button_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.button_frame.pack(padx=20, pady=(0, 20))
        self.ok_button = customtkinter.CTkButton(self.button_frame, text="OK", command=self._on_ok)
        self.ok_button.pack(side=tkinter.LEFT, padx=5)
        self.cancel_button = customtkinter.CTkButton(self.button_frame, text="Cancel", command=self._on_cancel)
        self.cancel_button.pack(side=tkinter.LEFT, padx=5)
        self.bind("<Return>", lambda event: self._on_ok() if self.ok_button.cget("state") == "normal" else None)
        self.bind("<Escape>", lambda event: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._validate_input()
        self.update_idletasks()
        parent_x = parent.winfo_x(); parent_y = parent.winfo_y()
        parent_width = parent.winfo_width(); parent_height = parent.winfo_height()
        dialog_width = self.winfo_reqwidth(); dialog_height = self.winfo_reqheight()
        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)
        self.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
    def _validate_input(self, *args):
        current_text = self.entry_var.get()
        if not current_text:
            self.ok_button.configure(state="normal")
            self.error_label.configure(text="")
            return
        if any(char in FILENAME_INVALID_CHARS for char in current_text):
            self.ok_button.configure(state="disabled")
            self.error_label.configure(text=f"Invalid chars (e.g., {FILENAME_INVALID_CHARS[0]})")
        else:
            self.ok_button.configure(state="normal")
            self.error_label.configure(text="")
    def _on_ok(self):
        if self.ok_button.cget("state") == "normal":
            self.result = self.entry_var.get().strip()
            self.grab_release(); self.destroy()
    def _on_cancel(self):
        self.result = None
        self.grab_release(); self.destroy()
    def get_input(self):
        self.master.wait_window(self)
        return self.result

# --- Main Application Class ---
class VideoTrimmerApp(customtkinter.CTk):
    def __init__(self, initial_input_dir):
        super().__init__()

        # Attempt to normalize initial_input_dir, default to None if invalid
        if initial_input_dir and os.path.isdir(initial_input_dir):
            self.current_input_directory = os.path.normpath(initial_input_dir)
        else:
            self.current_input_directory = None
            print("No valid initial directory provided to app, overlay will be used.")

        self.output_directory = self.current_input_directory # Can be None initially
        self.location_options = []
        self.destination_options = []
        self.recent_videos = []
        self.video_filenames = []
        self.video_path = None
        self.pending_custom_filename = None
        self.current_filename = ""; self.current_creation_time = ""; self.current_duration_str = ""; self.current_size_str = ""
        self.duration = 0.0; self.start_time = 0.0; self.end_time = 0.0; self.original_size_bytes = None
        self.is_processing = False; self.start_thumb_job = None; self.end_thumb_job = None
        self.status_message_clear_job = None
        self.last_trim_status_message = ""
        self.last_trim_status_color = "gray"
        self.temporary_status_active = False
        self.location_overlay_canvas = None ### NEW: Initialize attribute

        self.up_directory_button = None

        self.title("Trimmy v.0.8")
        self.geometry("700x900")
        self.resizable(False, False)

        self.placeholder_pil_image = Image.new('RGB', (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), color='gray')
        self.placeholder_ctk_image = customtkinter.CTkImage(light_image=self.placeholder_pil_image,
                                                             dark_image=self.placeholder_pil_image,
                                                             size=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
        self.current_start_thumb_ctk = self.placeholder_ctk_image
        self.current_end_thumb_ctk = self.placeholder_ctk_image

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_columnconfigure(3, weight=0)

        # --- Row 0, 1: Location ---
        self.location_label = customtkinter.CTkLabel(self, text="Location:")
        self.location_label.grid(row=0, column=0, columnspan=4, padx=20, pady=(20, 5), sticky="w")
        self.location_combobox = customtkinter.CTkComboBox(self, values=[], command=self.on_location_selected) # state set below
        self.location_combobox.grid(row=1, column=0, columnspan=3, padx=(20,5), pady=(0, 15), sticky="ew")

        self.location_combobox = customtkinter.CTkComboBox(self, values=[], command=self.on_location_selected)
        self.location_combobox.grid(row=1, column=0, columnspan=3, padx=(20,5), pady=(0, 15), sticky="ew")

        self.up_directory_button = customtkinter.CTkButton(self, text=u"\u25B2", width=40, # Unicode for UP ARROW
                                                          command=self.on_up_directory_clicked)
        self.up_directory_button.grid(row=1, column=3, padx=(0, 20), pady=(0,15), sticky="e")

        ### MODIFIED: Conditional overlay creation ###
        if not self.current_input_directory:
            self.location_combobox.set(INITIAL_LOCATION_PROMPT)
            self.location_combobox.configure(state="disabled") # Disable direct interaction
            self.location_overlay_canvas = tkinter.Canvas(self, highlightthickness=0, bd=0)
            try: # Set background to match parent for pseudo-transparency
                self.location_overlay_canvas.configure(bg=self.cget("bg"))
            except tkinter.TclError: # Fallback if self.cget("bg") fails early
                 self.location_overlay_canvas.configure(bg="white") # Or some default
            self.location_overlay_canvas.place(in_=self.location_combobox, relx=0, rely=0, relwidth=1, relheight=1)
            self.location_overlay_canvas.bind("<Button-1>", self.on_location_combobox_clicked)
        else:
            self.location_combobox.configure(state="readonly") # Normal operation

        # --- Row 2, 3: Select Video & Refresh ---
        self.video_select_label = customtkinter.CTkLabel(self, text="Select Video:")
        self.video_select_label.grid(row=2, column=0, columnspan=2, padx=20, pady=(5, 5), sticky="w")
        self.video_combobox = customtkinter.CTkComboBox(self, values=["Initializing..."], command=self.on_video_selected)
        self.video_combobox.set("Initializing...")
        self.video_combobox.grid(row=3, column=0, columnspan=3, padx=(20,5), pady=(0, 15), sticky="ew")
        self.refresh_button = customtkinter.CTkButton(self, text="Refresh", width=80, command=self.on_refresh_clicked)
        self.refresh_button.grid(row=3, column=3, padx=(0, 20), pady=(0,15), sticky="e")

        # --- Row 4: Info Frame ---
        self.info_frame = customtkinter.CTkFrame(self)
        self.info_frame.grid(row=4, column=0, columnspan=4, padx=20, pady=(0, 15), sticky="ew")
        self.info_frame.grid_columnconfigure(0, weight=1)
        self.file_info_display = customtkinter.CTkLabel(self.info_frame, text="Select a video", justify=tkinter.LEFT, anchor="nw")
        self.file_info_display.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        # --- Sliders & Scrub ---
        self.start_time_label = customtkinter.CTkLabel(self, text=f"Start Time: {format_time(self.start_time)}")
        self.start_time_label.grid(row=5, column=0, columnspan=4, padx=20, pady=(10, 0), sticky="w")
        self.start_scrub_left_button = customtkinter.CTkButton(self, text="<", width=40, command=self.scrub_start_left)
        self.start_scrub_left_button.grid(row=6, column=0, padx=(20, 5), pady=(5, 10), sticky="w")
        self.start_slider = customtkinter.CTkSlider(self, from_=0, to=1.0, command=self.update_start_time)
        self.start_slider.grid(row=6, column=1, columnspan=2, padx=5, pady=(5, 10), sticky="ew")
        self.start_scrub_right_button = customtkinter.CTkButton(self, text=">", width=40, command=self.scrub_start_right)
        self.start_scrub_right_button.grid(row=6, column=3, padx=(5, 20), pady=(5, 10), sticky="e")
        self.end_time_label = customtkinter.CTkLabel(self, text=f"End Time: {format_time(self.end_time)}")
        self.end_time_label.grid(row=7, column=0, columnspan=4, padx=20, pady=(10, 0), sticky="w")
        self.end_scrub_left_button = customtkinter.CTkButton(self, text="<", width=40, command=self.scrub_end_left)
        self.end_scrub_left_button.grid(row=8, column=0, padx=(20, 5), pady=(5, 20), sticky="w")
        self.end_slider = customtkinter.CTkSlider(self, from_=0, to=1.0, command=self.update_end_time)
        self.end_slider.grid(row=8, column=1, columnspan=2, padx=5, pady=(5, 20), sticky="ew")
        self.end_scrub_right_button = customtkinter.CTkButton(self, text=">", width=40, command=self.scrub_end_right)
        self.end_scrub_right_button.grid(row=8, column=3, padx=(5, 20), pady=(5, 20), sticky="e")
        self.start_slider.set(0); self.end_slider.set(1.0)

        # --- Thumbnails ---
        self.thumb_frame = customtkinter.CTkFrame(self)
        self.thumb_frame.grid(row=9, column=0, columnspan=4, padx=20, pady=10, sticky="ew")
        self.thumb_frame.grid_columnconfigure(0, weight=1); self.thumb_frame.grid_columnconfigure(1, weight=1)
        self.start_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="Start Frame"); self.start_thumb_label_text.grid(row=0, column=0, pady=(5,2))
        self.start_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=self.current_start_thumb_ctk); self.start_thumb_label.grid(row=1, column=0, padx=10, pady=(0,10))
        self.end_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="End Frame"); self.end_thumb_label_text.grid(row=0, column=1, pady=(5,2))
        self.end_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=self.current_end_thumb_ctk); self.end_thumb_label.grid(row=1, column=1, padx=10, pady=(0,10))

        # --- Destination, Rename, Status, Buttons ---
        self.destination_label = customtkinter.CTkLabel(self, text="Destination:")
        self.destination_label.grid(row=10, column=0, columnspan=4, padx=20, pady=(10, 5), sticky="w")
        self.destination_combobox = customtkinter.CTkComboBox(self, values=[], command=self.on_destination_selected)
        self.destination_combobox.grid(row=11, column=0, columnspan=4, padx=20, pady=(0, 5), sticky="ew")
        self.rename_checkbox = customtkinter.CTkCheckBox(self, text="Rename")
        self.rename_checkbox.grid(row=12, column=0, columnspan=4, padx=20, pady=(5, 5), sticky="w")
        self.status_label = customtkinter.CTkLabel(self, text="", text_color="gray")
        self.status_label.grid(row=13, column=0, columnspan=4, padx=20, pady=5, sticky="ew")
        self.button_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.button_frame.grid(row=14, column=0, columnspan=4, padx=20, pady=(10, 20), sticky="ew")
        self.button_frame.grid_columnconfigure(0, weight=1) # For spacing
        self.button_frame.grid_columnconfigure(1, weight=0)
        self.button_frame.grid_columnconfigure(2, weight=0) # Spacer column
        self.button_frame.grid_columnconfigure(3, weight=0)
        self.button_frame.grid_columnconfigure(4, weight=1) # For spacing

        self.trim_button = customtkinter.CTkButton(self.button_frame, text="Trim", command=lambda: self.start_trim_thread(delete_original=False))
        self.trim_button.grid(row=0, column=1, padx=10, pady=5) # Centered more
        self.trim_delete_button = customtkinter.CTkButton(self.button_frame, text="Trim & Delete", command=lambda: self.start_trim_thread(delete_original=True), fg_color="#D32F2F", hover_color="#B71C1C")
        self.trim_delete_button.grid(row=0, column=3, padx=10, pady=5) # Centered more

        # --- Initial setup ---
        self.populate_location_dropdown() # Must be called AFTER overlay check
        self.update_destination_dropdown()

        if self.current_input_directory: ### MODIFIED: Only refresh if dir is set
            self.refresh_video_list()
        else: # No initial directory, set video combobox to placeholder and disable UI
            self.video_combobox.set("No videos found")
            self.video_combobox.configure(state="disabled")
            self.disable_ui_components(disable=True)
            self.update_status("Please select a video directory.", "orange")

        if not self.video_path and not self.location_overlay_canvas: # If no overlay and no video path, disable
            self.disable_ui_components(disable=True)
        elif self.video_path : # If video path exists, enable
            self.disable_ui_components(disable=False)
        # If overlay exists, disable_ui_components(True) was already called effectively

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.center_window()


    ### NEW/MODIFIED: Method specifically for overlay click ###
    def on_location_combobox_clicked(self, event=None):
        print("Location overlay clicked.")
        initial_dir_for_browse = self.current_input_directory if self.current_input_directory else os.getcwd()
        new_dir = tkinter.filedialog.askdirectory(initialdir=initial_dir_for_browse, title="Select Video Directory")

        if new_dir and os.path.isdir(new_dir):
            self.current_input_directory = os.path.normpath(new_dir)
            
            # Destroy overlay FIRST, so subsequent UI updates see it as gone
            if self.location_overlay_canvas:
                self.location_overlay_canvas.destroy()
                self.location_overlay_canvas = None
            
            # Now that overlay is gone, restore normal combobox state BEFORE populating it
            self.location_combobox.configure(state="readonly") 

            self.add_recent_directory(new_dir) # This should save to config

            # Now populate and update other UI
            self.populate_location_dropdown()  # This will now correctly set the new path
            self.update_destination_dropdown()
            self.refresh_video_list()
            self.disable_ui_components(disable=not bool(self.video_filenames))

            self.update_status(f"Directory set to: {os.path.basename(self.current_input_directory)}", "green", is_temporary=True)
        else:
            if self.location_overlay_canvas:
                self.update_status("No directory selected. Please select a video directory.", "orange")

    def add_recent_directory(self, new_path):
        config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
        config = {}
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load config to add recent directory: {e}")
            config = {} # Start fresh or with minimal structure if loading failed

        recent = config.get("recent_input_directories", [])
        # Normalize paths before comparison and ensure they are directories
        new_path_norm = os.path.normpath(new_path)
        recent = [os.path.normpath(p) for p in recent if os.path.isdir(p) and os.path.normpath(p) != new_path_norm]
        recent.insert(0, new_path_norm)
        config["recent_input_directories"] = recent[:RECENT_FILES_COUNT] # Keep max count

        # Also update the last_input_directory when a new one is chosen this way
        config["last_input_directory"] = new_path_norm
        print(f"Setting last_input_directory via add_recent_directory: {new_path_norm}")

        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
            print(f"Updated config with recent directory and last directory: {new_path_norm}")
        except Exception as e:
            print(f"Failed to update config file with recent/last directory: {e}")


    def center_window(self):
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = self.winfo_width()
        window_height = self.winfo_height()
        x_coord = int((screen_width / 2) - (window_width / 2))
        y_coord = int((screen_height / 2) - (window_height / 2) - 30) # Minor offset up
        self.geometry(f"{window_width}x{window_height}+{x_coord}+{y_coord}")

    def disable_ui_components(self, disable=True):
        state_val = "disabled" if disable else "normal"
        # Always disable refresh if processing, otherwise base on 'disable'
        refresh_state = "disabled" if self.is_processing else state_val

        widgets_to_toggle = [
            self.start_slider, self.end_slider,
            self.start_scrub_left_button, self.start_scrub_right_button,
            self.end_scrub_left_button, self.end_scrub_right_button,
            self.trim_button, self.trim_delete_button,
            self.destination_combobox,
            self.rename_checkbox
        ]
        if self.refresh_button: self.refresh_button.configure(state=refresh_state)

        if self.is_processing: # If processing, all these are disabled
            state_val = "disabled"

        for widget in widgets_to_toggle:
            if widget: widget.configure(state=state_val)

        # Video combobox state
        if self.video_combobox:
            if self.is_processing:
                self.video_combobox.configure(state="disabled")
            elif disable:
                current_text = self.video_combobox.get()
                if not self.video_filenames or current_text == "Initializing...":
                    self.video_combobox.configure(values=[]) # Clear values
                    self.video_combobox.set("No videos found")
                # else keep current text if it's a filename but still disable
                self.video_combobox.configure(state="disabled")
            else: # not disable
                if self.video_filenames:
                    self.video_combobox.configure(state="normal") # Or "readonly" if you prefer
                else:
                    self.video_combobox.configure(values=[])
                    self.video_combobox.set("No videos found")
                    self.video_combobox.configure(state="disabled")
        
        # Location combobox state (only if no overlay is active)
        if not self.location_overlay_canvas and self.location_combobox:
             self.location_combobox.configure(state="disabled" if self.is_processing else "readonly")


        if disable and not self.is_processing: # Only reset these if disabling NOT due to processing
            if not self.video_path:
                self.display_placeholder_thumbnails()
                self.file_info_display.configure(text="Select a video")
                self.start_time_label.configure(text="Start Time: --:--:--") # Removed ms for placeholder
                self.end_time_label.configure(text="End Time: --:--:--")
                if self.start_slider: self.start_slider.set(0)
                if self.end_slider: self.end_slider.set(1.0)

    def refresh_video_list(self, preserve_selection=False):
        # If overlay is active, don't try to refresh video list yet
        if self.location_overlay_canvas:
            print("Video list refresh deferred: Location not yet set.")
            self.video_combobox.set("No videos found") # Or "Set location first"
            self.video_combobox.configure(state="disabled")
            self.disable_ui_components(True) # Keep UI mostly disabled
            return

        if not self.current_input_directory:
            print("Video list refresh failed: No current input directory.")
            self.video_combobox.set("No videos found")
            self.video_combobox.configure(state="disabled")
            self.disable_ui_components(True)
            self.update_status("Cannot refresh: No directory selected.", "orange", is_temporary=True)
            return

        previously_selected_filename = None
        if preserve_selection and self.video_path:
            previously_selected_filename = os.path.basename(self.video_path)

        self.recent_videos = find_recent_videos(self.current_input_directory, RECENT_FILES_COUNT)
        self.video_filenames = [os.path.basename(p) for p in self.recent_videos]

        if self.video_filenames:
            self.video_combobox.configure(values=self.video_filenames, state="normal") # Or "readonly"
            target_selection = None
            new_selection_made = False
            if previously_selected_filename and previously_selected_filename in self.video_filenames:
                target_selection = previously_selected_filename
            elif self.video_filenames: # Make sure list is not empty
                target_selection = self.video_filenames[0]
                new_selection_made = True
            
            if target_selection:
                self.video_combobox.set(target_selection)
                if new_selection_made or not self.video_path:
                    self.after(10, lambda: self.on_video_selected(target_selection))
                else: # Selection preserved, video already loaded
                    self.disable_ui_components(disable=False) # Ensure UI is enabled
            else: # Should not happen if self.video_filenames is true, but as a fallback
                self.video_combobox.set("Select video")
                self.disable_ui_components(disable=True)


        else: # No videos found
            self.video_path = None
            self.video_combobox.configure(values=[])
            self.video_combobox.set("No videos found")
            self.video_combobox.configure(state="disabled")
            self.disable_ui_components(disable=True) # Disables most things
            dir_label = os.path.basename(self.current_input_directory) if self.current_input_directory else "selected location"
            self.update_status(f"No videos found in {dir_label}", "orange", is_temporary=True)

        if not self.is_processing and self.refresh_button:
            self.refresh_button.configure(state="normal" if self.current_input_directory else "disabled")


    def display_placeholder_thumbnails(self):
        self.current_start_thumb_ctk = self.placeholder_ctk_image
        self.current_end_thumb_ctk = self.placeholder_ctk_image
        if self.start_thumb_label and self.start_thumb_label.winfo_exists():
            self.start_thumb_label.configure(image=self.current_start_thumb_ctk)
        if self.end_thumb_label and self.end_thumb_label.winfo_exists():
            self.end_thumb_label.configure(image=self.current_end_thumb_ctk)

    def schedule_thumbnail_update(self, time_seconds, for_start_thumb):
        if not self.video_path:
            self.display_placeholder_thumbnails()
            return

        job_attr = 'start_thumb_job' if for_start_thumb else 'end_thumb_job'
        existing_job = getattr(self, job_attr)
        if existing_job:
            self.after_cancel(existing_job)

        label_to_update = self.start_thumb_label if for_start_thumb else self.end_thumb_label
        if label_to_update and label_to_update.winfo_exists():
            label_to_update.configure(image=self.placeholder_ctk_image) # Show placeholder immediately

        new_job = self.after(THUMBNAIL_UPDATE_DELAY_MS, lambda t=time_seconds, fst=for_start_thumb: self.generate_and_display_thumbnail(t, fst))
        setattr(self, job_attr, new_job)

    def generate_and_display_thumbnail(self, time_seconds, for_start_thumb):
        if not self.video_path or not os.path.exists(self.video_path):
            self.display_placeholder_thumbnails()
            return

        temp_thumb_dir = tempfile.gettempdir()
        thumb_filename = f"trimmy_thumb_{uuid.uuid4().hex}.jpg"
        thumb_path = os.path.join(temp_thumb_dir, thumb_filename)

        thread = threading.Thread(target=self._run_thumbnail_extraction,
                                  args=(self.video_path, time_seconds, thumb_path, for_start_thumb),
                                  daemon=True)
        thread.start()

    def _run_thumbnail_extraction(self, video_path, time_seconds, thumb_path, for_start_thumb):
        success = extract_thumbnail(video_path, time_seconds, thumb_path)
        self.after(0, self._update_thumbnail_label, thumb_path, for_start_thumb, success)

    def _update_thumbnail_label(self, thumb_path, for_start_thumb, success):
        label = self.start_thumb_label if for_start_thumb else self.end_thumb_label
        if not (label and label.winfo_exists()): return

        new_image_to_set = self.placeholder_ctk_image # Default to placeholder

        if success and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            try:
                pil_img = Image.open(thumb_path)
                ctk_img = customtkinter.CTkImage(light_image=pil_img, dark_image=pil_img,
                                                 size=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
                new_image_to_set = ctk_img
            except Exception as e:
                print(f"Error loading thumbnail image {thumb_path}: {e}")
                # Cleanup failed thumb if it exists and is in our list
                if os.path.exists(thumb_path) and thumb_path in temp_files_to_cleanup:
                    try: temp_files_to_cleanup.remove(thumb_path); os.remove(thumb_path)
                    except: pass
        else: # Extraction failed or file is bad/empty
            if os.path.exists(thumb_path) and thumb_path in temp_files_to_cleanup:
                 try: temp_files_to_cleanup.remove(thumb_path); os.remove(thumb_path)
                 except: pass

        if for_start_thumb:
            self.current_start_thumb_ctk = new_image_to_set
        else:
            self.current_end_thumb_ctk = new_image_to_set
        label.configure(image=new_image_to_set)


    def on_refresh_clicked(self):
        print("Refresh button clicked.")
        if self.is_processing:
            self.update_status("Cannot refresh while processing.", "orange", is_temporary=True)
            return
        if self.location_overlay_canvas: # If overlay is active, means location not set
            self.update_status("Please select a video directory first.", "orange", is_temporary=True)
            # Optionally, briefly flash the location combobox or give focus
            if hasattr(self.location_combobox, 'focus_set'): self.location_combobox.focus_set()
            return

        self.update_status("Refreshing video list...", "blue", is_temporary=True)
        self.refresh_video_list(preserve_selection=True)

    def on_location_selected(self, selected_path_value): # Normal combobox selection
        print(f"Location combobox selected: {selected_path_value}")
        if self.location_overlay_canvas: # Should not happen if overlay is active
            print("Warning: on_location_selected called while overlay is active.")
            return

        if selected_path_value == INITIAL_LOCATION_PROMPT: # Should not be selectable if overlay gone
            return

        if selected_path_value == BROWSE_OPTION:
            initial_dir_for_browse = self.current_input_directory if self.current_input_directory else os.getcwd()
            new_dir = tkinter.filedialog.askdirectory(initialdir=initial_dir_for_browse, title="Select Video Directory")
            if new_dir and os.path.isdir(new_dir):
                self.current_input_directory = os.path.normpath(new_dir)
            else: # User cancelled or selected invalid
                # Re-set combobox to current valid directory if browse was cancelled
                if self.current_input_directory:
                    self.location_combobox.set(self.current_input_directory)
                else: # No valid current dir, and browse cancelled
                    self.location_combobox.set(BROWSE_OPTION) # Or INITIAL_LOCATION_PROMPT if appropriate
                return # Don't proceed with updates
        else: # A direct path was selected from recents
            self.current_input_directory = os.path.normpath(selected_path_value)

        print(f"Location changed to: {self.current_input_directory}")
        self.add_recent_directory(self.current_input_directory) # This also saves as last_input_directory
        # save_last_directory(self.current_input_directory) # Handled by add_recent_directory

        self.populate_location_dropdown() # Re-populates and sets current selection
        self.update_destination_dropdown()
        self.video_path = None # Reset video path as directory changed
        self.refresh_video_list() # Refresh videos for the new directory

        if not self.video_filenames:
            self.disable_ui_components(True)
            self.update_info_display()
            self.display_placeholder_thumbnails()
            self.update_status(f"No videos found in {os.path.basename(self.current_input_directory)}.", "orange", is_temporary=True)
        else:
            self.update_status(f"Directory set to: {os.path.basename(self.current_input_directory)}", "green", is_temporary=True)


    def populate_location_dropdown(self):
        recent_dirs_from_config = []
        config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    loaded_recents = config.get("recent_input_directories", [])
                    # Filter for valid directories and normalize
                    recent_dirs_from_config = [os.path.normpath(p) for p in loaded_recents if os.path.isdir(p)]
            except Exception as e:
                print(f"Error loading recent dirs from config: {e}")

        # These are the items that will appear in the dropdown list when expanded
        dropdown_list_items = [BROWSE_OPTION]
        
        # Add recent directories to the dropdown list,
        # EXCLUDING the current_input_directory if it happens to be in recents.
        current_norm_path = os.path.normpath(self.current_input_directory) if self.current_input_directory and os.path.isdir(self.current_input_directory) else None

        for r_dir in recent_dirs_from_config:
            if r_dir != current_norm_path and r_dir not in dropdown_list_items: # Don't add current dir to dropdown
                dropdown_list_items.append(r_dir)
        
        self.location_options = dropdown_list_items # These are the values for the dropdown
        self.location_combobox.configure(values=self.location_options)

        # Determine what text to display in the combobox's main field
        display_text_in_combobox = BROWSE_OPTION # Default

        if current_norm_path: # If there's a valid current directory
            display_text_in_combobox = current_norm_path
        elif self.location_overlay_canvas: # Only if NO current directory AND overlay exists
            display_text_in_combobox = INITIAL_LOCATION_PROMPT
        # If no current_input_directory and no overlay, it defaults to BROWSE_OPTION (already set)
        
        self.location_combobox.set(display_text_in_combobox)


    def update_destination_dropdown(self):
        if not self.output_directory or not os.path.isdir(self.output_directory):
            if self.current_input_directory and os.path.isdir(self.current_input_directory):
                self.output_directory = self.current_input_directory
            else: # Fallback if current_input_directory is also not set (e.g. initial state)
                self.output_directory = os.getcwd()

        parents_of_output = get_parent_directories(self.output_directory)
        destination_paths_set = {BROWSE_OPTION} # Use a set for uniqueness initially

        if self.output_directory: destination_paths_set.add(self.output_directory)
        if self.current_input_directory: destination_paths_set.add(self.current_input_directory)
        for p in parents_of_output: destination_paths_set.add(p)
        
        # Convert set to list, maintaining a preferred order if possible
        ordered_dest_options = [BROWSE_OPTION]
        if self.output_directory and self.output_directory != BROWSE_OPTION:
            ordered_dest_options.append(self.output_directory)
        if self.current_input_directory and self.current_input_directory not in ordered_dest_options:
             ordered_dest_options.append(self.current_input_directory)
        for p in parents_of_output:
            if p not in ordered_dest_options: ordered_dest_options.append(p)
        # Ensure all unique paths from the set are included if missed by ordered logic
        for p in destination_paths_set:
            if p not in ordered_dest_options: ordered_dest_options.append(p)

        self.destination_options = ordered_dest_options
        self.destination_combobox.configure(values=self.destination_options)

        if self.output_directory in self.destination_options:
            self.destination_combobox.set(self.output_directory)
        elif self.destination_options:
            self.destination_combobox.set(self.destination_options[0]) # Default to BROWSE_OPTION
        else: # Should not happen as BROWSE_OPTION is always there
            self.destination_combobox.set("")


    def on_destination_selected(self, selected_path):
        if selected_path == BROWSE_OPTION:
            initial_dir_for_browse = self.output_directory if self.output_directory else os.getcwd()
            new_dir = tkinter.filedialog.askdirectory(initialdir=initial_dir_for_browse, title="Select Output Directory")
            if new_dir and os.path.isdir(new_dir):
                self.output_directory = os.path.normpath(new_dir)
            # else: user cancelled, keep current output_directory
        else:
            self.output_directory = os.path.normpath(selected_path)
        print(f"Output directory set to: {self.output_directory}")
        self.update_destination_dropdown()

    def on_video_selected(self, selected_filename):
        if self.is_processing: return
        if not selected_filename or selected_filename in ["No videos found", "Initializing...", INITIAL_LOCATION_PROMPT]:
            self.video_path = None
            self.disable_ui_components(True) # Disables most things
            self.update_info_display()
            self.display_placeholder_thumbnails()
            return

        # If current_input_directory is somehow None here, we can't form a path
        if not self.current_input_directory:
            self.update_status("Error: Input directory not set.", "red", is_temporary=True)
            self.video_path = None
            self.refresh_video_list() # This will show "No videos found"
            return

        self.video_path = os.path.join(self.current_input_directory, selected_filename)
        if not os.path.exists(self.video_path):
            self.update_status(f"Error: {selected_filename} not found.", "red", is_temporary=True)
            self.video_path = None
            self.refresh_video_list(preserve_selection=False) # Re-scan
            return

        print(f"Video selected: {self.video_path}")
        self.load_video_data()

    def load_video_data(self):
        if not self.video_path:
            self.disable_ui_components(True)
            self.update_info_display()
            self.display_placeholder_thumbnails()
            return

        self.update_status(f"Loading {os.path.basename(self.video_path)}...", "blue", is_temporary=True)
        duration_s, ctime_str, size_str, size_bytes = get_video_metadata(self.video_path)

        if duration_s is None:
            self.update_status(f"Error loading metadata for {os.path.basename(self.video_path)}.", "red", is_temporary=True)
            self.video_path = None
            # Attempt to re-select or clear
            self.refresh_video_list(preserve_selection=False) # This might select another video or show "No videos"
            # If refresh_video_list resulted in no video, it will call disable_ui_components(True)
            if not self.video_path:
                self.disable_ui_components(True)
                self.update_info_display()
                self.display_placeholder_thumbnails()
            return

        self.duration = duration_s
        self.original_size_bytes = size_bytes
        self.current_filename = os.path.basename(self.video_path)
        self.current_creation_time = ctime_str
        self.current_size_str = size_str
        self.current_duration_str = format_time(self.duration)

        self.start_time = 0.0
        self.end_time = self.duration if self.duration > 0 else 1.0 # Ensure end_time > start_time for slider
        
        # Configure sliders based on actual duration
        self.start_slider.configure(to=self.duration if self.duration > 0 else 1.0)
        self.end_slider.configure(to=self.duration if self.duration > 0 else 1.0)
        self.start_slider.set(self.start_time)
        self.end_slider.set(self.end_time)

        self.update_start_time(self.start_time) # This will also schedule thumb
        self.update_end_time(self.end_time)     # This will also schedule thumb
        self.update_info_display()
        self.disable_ui_components(False) # Enable UI components
        self.update_status(f"Loaded: {self.current_filename}", "green", is_temporary=True)
        self.rename_checkbox.deselect()
        self.pending_custom_filename = None

    def update_info_display(self):
        if not self.video_path :
            self.file_info_display.configure(text="Select a video to see details.")
            return
        info_text = (
            f"File: {self.current_filename}\n"
            f"Duration: {self.current_duration_str}\n"
            f"Created: {self.current_creation_time}\n"
            f"Size: {self.current_size_str}"
        )
        self.file_info_display.configure(text=info_text)

    def update_start_time(self, value_str_or_float):
        try: value = float(value_str_or_float)
        except ValueError: return # Invalid input
        if self.is_processing: return

        # Ensure start time is not too close to or past end time
        # Allow a very small difference for precision issues
        if value >= self.end_time - 0.01: # Allow start == end for thumbnail, but trim needs diff
            value = max(0, self.end_time - 0.05) # Keep a small gap if trying to go past
        value = max(0, value) # Cannot be negative

        self.start_time = value
        # self.start_slider.set(self.start_time) # Slider might call this, avoid recursion if from slider
        self.start_time_label.configure(text=f"Start Time: {format_time(self.start_time)}")
        self.schedule_thumbnail_update(self.start_time, for_start_thumb=True)

    def update_end_time(self, value_str_or_float):
        try: value = float(value_str_or_float)
        except ValueError: return
        if self.is_processing: return

        # Ensure end time is not before or too close to start time
        if value <= self.start_time + 0.01: # Allow end == start for thumbnail
            value = min(self.duration, self.start_time + 0.05) # Keep a small gap
        value = min(self.duration, value) # Cannot exceed total duration

        self.end_time = value
        # self.end_slider.set(self.end_time) # Slider might call this
        self.end_time_label.configure(text=f"End Time: {format_time(self.end_time)}")
        self.schedule_thumbnail_update(self.end_time, for_start_thumb=False)

    def scrub_start_left(self):
        if not self.video_path or self.is_processing: return
        new_time = max(0, self.start_time - SCRUB_INCREMENT)
        self.start_slider.set(new_time) # This will trigger update_start_time
        # self.update_start_time(new_time) # Called by slider command

    def scrub_start_right(self):
        if not self.video_path or self.is_processing: return
        # Ensure new_time doesn't exceed end_time - small_delta
        new_time = min(self.end_time - 0.05, self.start_time + SCRUB_INCREMENT)
        new_time = max(0, new_time) # Ensure not negative
        self.start_slider.set(new_time)
        # self.update_start_time(new_time)

    def scrub_end_left(self):
        if not self.video_path or self.is_processing: return
        # Ensure new_time doesn't go below start_time + small_delta
        new_time = max(self.start_time + 0.05, self.end_time - SCRUB_INCREMENT)
        new_time = min(self.duration, new_time) # Ensure not over duration
        self.end_slider.set(new_time)
        # self.update_end_time(new_time)

    def scrub_end_right(self):
        if not self.video_path or self.is_processing:return
        new_time = min(self.duration, self.end_time + SCRUB_INCREMENT)
        self.end_slider.set(new_time)
        # self.update_end_time(new_time)

    def start_trim_thread(self, delete_original=False):
        self.pending_custom_filename = None
        if self.is_processing: print("Already processing."); return
        if not self.video_path: self.update_status("No video selected.", "red", is_temporary=True); return

        if not self.output_directory or not os.path.isdir(self.output_directory):
            self.update_status("Invalid output directory. Please select.", "red", is_temporary=True)
            # Try to trigger destination selection
            self.on_destination_selected(BROWSE_OPTION)
            if not self.output_directory or not os.path.isdir(self.output_directory):
                 self.update_status("Output directory still not set. Trim cancelled.", "red", is_temporary=True)
                 return
            self.update_status("Output directory selected. Try trimming again.", "orange", is_temporary=True)
            return

        if abs(self.end_time - self.start_time) < 0.1: # Minimum trim duration
            self.update_status("Error: Trim duration too short (min 0.1s).", "red", is_temporary=True); return

        if self.rename_checkbox.get() == 1:
            dialog = CustomFilenameDialog(self, title="Set Output Filename")
            custom_basename = dialog.get_input()
            if custom_basename is None:
                self.rename_checkbox.deselect()
                self.update_status("Rename cancelled. Using default name.", "orange", is_temporary=True)
                self.pending_custom_filename = None
            elif not custom_basename.strip(): # Check if empty after stripping
                self.rename_checkbox.deselect()
                self.update_status("Empty name provided. Using default name.", "orange", is_temporary=True)
                self.pending_custom_filename = None
            else:
                self.pending_custom_filename = custom_basename.strip() + ".mp4" # Ensure .mp4 for custom
        else:
            self.pending_custom_filename = None


        if delete_original:
            confirm_msg = f"Permanently delete the original file?\n\n{os.path.basename(self.video_path)}\n\nThis cannot be undone."
            if self.pending_custom_filename and self.pending_custom_filename != os.path.basename(self.video_path):
                 confirm_msg += f"\n\nThe trimmed clip will be saved as: {self.pending_custom_filename}"
            confirm = tkinter.messagebox.askyesno("Confirm Delete", confirm_msg, icon='warning', parent=self)
            if not confirm:
                self.update_status("Trim & Delete cancelled.", "orange", is_temporary=True)
                self.pending_custom_filename = None # Clear if rename was part of a cancelled delete
                return

        self.is_processing = True
        self.disable_ui_components(disable=True) # Disables UI based on is_processing
        self.update_status("Starting trim...", "blue", is_persistent_trim_status=False)

        temp_output_path_for_delete_op = None
        if delete_original:
            try:
                base_temp, ext_temp = os.path.splitext(os.path.basename(self.video_path))
                # Ensure temp file is in the intended output directory for permissions etc.
                temp_output_path_for_delete_op = os.path.join(self.output_directory, f"{base_temp}_temp_trim_{uuid.uuid4().hex}{ext_temp}")
            except Exception as e:
                print(f"Error generating temp filename for delete op: {e}")
                self.update_status("Error preparing temp file for delete operation.", "red", is_persistent_trim_status=True)
                self.reset_ui_after_processing()
                return

        thread = threading.Thread(target=self.run_ffmpeg_trim, args=(delete_original, temp_output_path_for_delete_op, self.pending_custom_filename), daemon=True)
        thread.start()

    def run_ffmpeg_trim(self, delete_original, temp_path_for_delete_op, custom_final_name_mp4):
        global temp_files_to_cleanup
        final_output_path_actual = None
        ffmpeg_output_target = None
        original_input_path = self.video_path # Cache, as self.video_path might change if UI refreshes

        try:
            if not original_input_path or not os.path.exists(original_input_path):
                raise ValueError("Original video path is invalid or file missing at trim time.")

            input_filename_full = original_input_path
            input_basename_no_ext, input_ext = os.path.splitext(os.path.basename(input_filename_full))

            if delete_original:
                ffmpeg_output_target = temp_path_for_delete_op # FFmpeg writes to this temp file
                if not ffmpeg_output_target: raise ValueError("Temporary output path for delete operation is missing.")
                # Add to cleanup in case of failure before rename/delete_original success
                if ffmpeg_output_target not in temp_files_to_cleanup:
                    temp_files_to_cleanup.append(ffmpeg_output_target)

                if custom_final_name_mp4: # e.g. "mytrim.mp4"
                    # Final path will be the custom name, in the output directory
                    final_output_path_actual = os.path.join(self.output_directory, custom_final_name_mp4)
                else:
                    # Final path will be the original name, in the output directory
                    final_output_path_actual = os.path.join(self.output_directory, os.path.basename(input_filename_full))
            else: # Not deleting original
                target_ext = ".mp4" if custom_final_name_mp4 else input_ext # Use .mp4 if custom name, else original ext

                if custom_final_name_mp4: # e.g. "mytrim.mp4"
                    # custom_final_name_mp4 already includes .mp4
                    file_base, _ = os.path.splitext(custom_final_name_mp4) # "mytrim"
                    actual_output_name = custom_final_name_mp4 # "mytrim.mp4"
                else:
                    file_base = f"{input_basename_no_ext}{TRIM_SUFFIX}" # "original_trimmy"
                    actual_output_name = f"{file_base}{target_ext}" # "original_trimmy.mp4" or .mov etc.

                # Handle existing file for non-delete operations by appending counter
                final_output_path_actual = os.path.join(self.output_directory, actual_output_name)
                counter = 1
                while os.path.exists(final_output_path_actual):
                    final_output_path_actual = os.path.join(self.output_directory, f"{file_base}_{counter}{target_ext}")
                    counter += 1
                ffmpeg_output_target = final_output_path_actual # FFmpeg writes directly to final unique path

            if final_output_path_actual is None: final_output_path_actual = ffmpeg_output_target

            start_str = format_time(self.start_time)
            trim_duration = max(0.1, self.end_time - self.start_time) # Ensure positive duration

            command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', # Keep error for stderr parsing
                       '-ss', start_str,
                       '-i', input_filename_full,
                       '-t', str(trim_duration),
                       '-c', 'copy', # Lossless copy
                       '-map', '0', # Map all streams
                       '-avoid_negative_ts', 'make_zero', # Or 'auto' for newer ffmpeg
                       '-y', # Overwrite output (ffmpeg_output_target)
                       ffmpeg_output_target]

            self.after(0, lambda: self.update_status("Processing with FFmpeg...", "blue", is_persistent_trim_status=False))
            print(f"Running FFmpeg command: {' '.join(command)}")

            startupinfo = None
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
            stdout, stderr = process.communicate() # Wait for completion

            if process.returncode == 0 and os.path.exists(ffmpeg_output_target) and os.path.getsize(ffmpeg_output_target) > 0:
                print(f"FFmpeg successful. Output to: {ffmpeg_output_target}")
                success_msg_base = f"Done! Trimmed: {os.path.basename(final_output_path_actual)}\n(in {os.path.basename(self.output_directory)})"

                if delete_original:
                    self.after(0, lambda: self.update_status("Finalizing and deleting original...", "blue", is_persistent_trim_status=False))
                    time.sleep(0.1) # Brief pause

                    renamed_temp_successfully = False
                    # If temp file is different from final desired path (can happen if custom name == original name)
                    if os.path.abspath(ffmpeg_output_target) != os.path.abspath(final_output_path_actual):
                        if os.path.exists(final_output_path_actual): # Safety: if final path already exists (e.g. user manually created it)
                            print(f"Warning: Target path '{final_output_path_actual}' for rename already exists. Trying to delete it first.")
                            try: os.remove(final_output_path_actual)
                            except OSError as e:
                                print(f"Could not delete existing file at final_output_path_actual: {e}")
                                # Fallback: save with a unique name based on the temp name
                                final_output_path_actual = ffmpeg_output_target + "_final_fallback" + input_ext
                                success_msg_base = f"Done! Trimmed: {os.path.basename(final_output_path_actual)}\n(Rename failed, saved as temp variation)"

                        try:
                            os.rename(ffmpeg_output_target, final_output_path_actual)
                            renamed_temp_successfully = True
                            print(f"Renamed temp {ffmpeg_output_target} to {final_output_path_actual}")
                            # If rename was successful, the temp file is no longer at its old path
                            if ffmpeg_output_target in temp_files_to_cleanup:
                                temp_files_to_cleanup.remove(ffmpeg_output_target)
                        except OSError as rename_err:
                             print(f"Error renaming {ffmpeg_output_target} to {final_output_path_actual}: {rename_err}")
                             # Keep ffmpeg_output_target as the actual if rename fails, but update the message
                             final_output_path_actual = ffmpeg_output_target # The trimmed file is the temp file
                             success_msg_base = f"Done! Trimmed to temp: {os.path.basename(final_output_path_actual)}\nOriginal NOT deleted due to rename error."
                             # Do NOT proceed to delete original if rename failed
                             self.after(0, lambda: self.update_status(f"{success_msg_base}", "orange", is_persistent_trim_status=True))
                             self.after(100, lambda p=final_output_path_actual: self.post_trim_success(p, deleted_original_path=None)) # Pass None for deleted path
                             return # Exit trim process here
                    else: # ffmpeg_output_target IS final_output_path_actual (no rename needed for the trimmed file itself)
                        renamed_temp_successfully = True # Effectively
                        if ffmpeg_output_target in temp_files_to_cleanup: # Remove from cleanup as it's now the final file
                             temp_files_to_cleanup.remove(ffmpeg_output_target)


                    # Proceed to delete original ONLY IF temp file handling (rename or direct write) was okay
                    if renamed_temp_successfully:
                        try:
                            print(f"Attempting to delete original: {input_filename_full}")
                            os.remove(input_filename_full)
                            print(f"Successfully deleted original: {input_filename_full}")
                            full_success_msg = f"{success_msg_base}\nOriginal file permanently deleted."
                            self.after(0, lambda: self.update_status(full_success_msg, "green", is_persistent_trim_status=True))
                            self.after(100, lambda p=final_output_path_actual, d=input_filename_full: self.post_trim_success(p, deleted_original_path=d))
                        except OSError as os_err:
                            error_message = f"Trimmed to {os.path.basename(final_output_path_actual)} BUT OS ERROR deleting original: {os_err}"
                            print(error_message)
                            self.after(0, lambda: self.update_status(error_message, "orange", is_persistent_trim_status=True))
                            self.after(100, lambda p=final_output_path_actual: self.post_trim_success(p, deleted_original_path=None))
                else: # Not deleting original
                    self.after(0, lambda: self.update_status(success_msg_base, "green", is_persistent_trim_status=True))
                    self.after(100, lambda p=final_output_path_actual: self.post_trim_success(p))
            else: # FFmpeg failed
                error_detail = stderr if stderr else stdout # stderr is usually more informative for errors
                error_message = f"FFmpeg failed (code {process.returncode}):\n{error_detail[-500:] if error_detail else 'No FFmpeg output'}"
                if not (os.path.exists(ffmpeg_output_target) and os.path.getsize(ffmpeg_output_target) > 0) and process.returncode == 0:
                    error_message = "FFmpeg reported success, but output file is missing or empty."

                print(error_message)
                self.after(0, lambda: self.update_status(error_message, "red", is_persistent_trim_status=True))
                if ffmpeg_output_target and os.path.exists(ffmpeg_output_target): # Cleanup failed output
                    print(f"FFmpeg failed, cleaning its partial output: {ffmpeg_output_target}")
                    try: os.remove(ffmpeg_output_target)
                    except OSError as e: print(f"Error cleaning failed ffmpeg output: {e}")
                    if ffmpeg_output_target in temp_files_to_cleanup:
                        try: temp_files_to_cleanup.remove(ffmpeg_output_target)
                        except ValueError: pass
                self.after(100, self.reset_ui_after_processing)
        except Exception as e:
            import traceback
            detailed_error = traceback.format_exc()
            error_message = f"Unexpected error during trim: {type(e).__name__}: {e}\n{detailed_error}"
            print(error_message)
            self.after(0, lambda: self.update_status(f"Unexpected trim error: {e}", "red", is_persistent_trim_status=True))
            if ffmpeg_output_target and os.path.exists(ffmpeg_output_target) and ffmpeg_output_target in temp_files_to_cleanup:
                try:
                    os.remove(ffmpeg_output_target)
                    temp_files_to_cleanup.remove(ffmpeg_output_target)
                except Exception as clean_e: print(f"Error cleaning temp ffmpeg output after error: {clean_e}")
            self.after(100, self.reset_ui_after_processing)
        finally:
            self.pending_custom_filename = None # Clear this regardless of outcome


    def post_trim_success(self, output_filepath, deleted_original_path=None):
        print(f"Trim process ended. Final file: {output_filepath if output_filepath else 'None'}")
        self.is_processing = False # Set before refresh_video_list

        should_preserve_selection_in_list = True
        # If the original was deleted AND it was the currently selected video_path
        if deleted_original_path and self.video_path == deleted_original_path:
            self.video_path = None # Original is gone, clear current video_path
            should_preserve_selection_in_list = False # Don't try to re-select it
            # UI will update to "No video selected" or select the next available
        
        # Refresh the video list. If original deleted, it won't be there.
        # If a new file was created in current dir, it might appear.
        self.refresh_video_list(preserve_selection=should_preserve_selection_in_list)
        # If refresh_video_list doesn't find any videos or fails to select one,
        # it will call disable_ui_components(True).
        # If it does select a video, it enables UI.
        # If no video is selected after refresh, ensure UI is appropriately disabled.
        if not self.video_path:
            self.disable_ui_components(True)
        else:
            self.disable_ui_components(False)


    def reset_ui_after_processing(self):
        self.is_processing = False
        self.pending_custom_filename = None
        # Refresh list, preserving selection if current video still exists.
        # This also handles re-enabling UI components via disable_ui_components.
        self.refresh_video_list(preserve_selection=True)
        if not self.video_path and not self.location_overlay_canvas: # Additional check
            self.disable_ui_components(True)


    def update_status(self, message, color="gray", is_persistent_trim_status=False, is_temporary=False):
        if self.status_message_clear_job:
            self.after_cancel(self.status_message_clear_job)
            self.status_message_clear_job = None

        def _update_label():
            if hasattr(self, 'status_label') and self.status_label and self.status_label.winfo_exists():
                 self.status_label.configure(text=message, text_color=color)

        if is_persistent_trim_status: # This is for trim results typically
            self.last_trim_status_message = message
            self.last_trim_status_color = color
            self.temporary_status_active = False
            self.after(0, _update_label)
        elif is_temporary: # For short-lived messages like "Loading..."
            # Only show temporary if no persistent trim status is more important,
            # OR if the temporary message is an error itself.
            # This logic might need refinement based on desired priority.
            # For now, temporary always shows.
            self.temporary_status_active = True
            self.after(0, _update_label)
            self.status_message_clear_job = self.after(STATUS_MESSAGE_CLEAR_DELAY_MS, self._revert_to_persistent_status)
        else: # General status updates, not overriding persistent trim status unless it's an error
            if not self.last_trim_status_message or color == "red": # Show if no persistent or if it's an error
                self.last_trim_status_message = "" # Clear old persistent if this one is not for trim result
            self.temporary_status_active = False
            self.after(0, _update_label)


    def _revert_to_persistent_status(self):
        self.temporary_status_active = False
        # Default to empty status if no persistent message was set
        current_text = self.last_trim_status_message if self.last_trim_status_message else ""
        current_color = self.last_trim_status_color if self.last_trim_status_message else "gray"

        # However, if current_input_directory is still None (overlay is active), show prompt
        if not self.current_input_directory and self.location_overlay_canvas:
            current_text = "Please select a video directory."
            current_color = "orange"

        def _update_label():
            if hasattr(self, 'status_label') and self.status_label and self.status_label.winfo_exists():
                self.status_label.configure(text=current_text, text_color=current_color)
        self.after(0, _update_label)
        self.status_message_clear_job = None


    def show_error_and_quit(self, message):
        print(f"FATAL ERROR: {message}")
        temp_root_created = False
        parent_for_messagebox = self
        if not (hasattr(self, 'title') and self.winfo_exists()):
            # If self (main window) doesn't exist or isn't fully formed
            try:
                root = tkinter.Tk(); root.withdraw(); parent_for_messagebox = root; temp_root_created = True
            except tkinter.TclError: # In case Tk subsystem isn't available at all
                print("TclError: Cannot create Tk root for error message.")
                cleanup_temp_files(); sys.exit(1)

        if parent_for_messagebox and hasattr(parent_for_messagebox, 'winfo_exists') and parent_for_messagebox.winfo_exists():
            tkinter.messagebox.showerror("Critical Error", message, parent=parent_for_messagebox)

        if temp_root_created and hasattr(parent_for_messagebox, 'destroy'): parent_for_messagebox.destroy()
        elif hasattr(self, 'destroy') and self.winfo_exists(): self.destroy()
        cleanup_temp_files(); sys.exit(1)


    def on_closing(self):
        print("Closing application.")
        if self.start_thumb_job: self.after_cancel(self.start_thumb_job)
        if self.end_thumb_job: self.after_cancel(self.end_thumb_job)
        if self.status_message_clear_job: self.after_cancel(self.status_message_clear_job)

        if self.is_processing:
            # Consider if a warning dialog is needed here
            print("Warning: Closing while a trim operation might be in progress in a thread.")
            # Threads are daemonic, so they should exit when main thread exits,
            # but FFmpeg process might be orphaned if not handled carefully.
            # For now, we just print a warning.

        cleanup_temp_files()
        if self.winfo_exists(): self.destroy()
        sys.exit(0) # Ensure clean exit


# --- Script Entry Point ---
if __name__ == "__main__":
    # 1. Check for FFmpeg/ffprobe first
    try:
        startupinfo_check = None
        if platform.system() == 'Windows':
            startupinfo_check = subprocess.STARTUPINFO()
            startupinfo_check.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo_check.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo_check)
        subprocess.run(['ffprobe', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo_check)
        print("FFmpeg and ffprobe found.")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        error_msg = f"ERROR: FFmpeg or ffprobe not found or not executable.\nPlease ensure they are installed and in your system's PATH.\nDetails: {e}"
        print(error_msg)
        # Show a Tkinter error box for this critical startup failure
        root_err = tkinter.Tk(); root_err.withdraw()
        tkinter.messagebox.showerror("Startup Error", error_msg, parent=root_err)
        root_err.destroy()
        sys.exit(1)
    except Exception as e: # Catch any other unexpected error during check
        error_msg = f"An unexpected error occurred while checking for FFmpeg/ffprobe: {e}"
        print(error_msg)
        root_err = tkinter.Tk(); root_err.withdraw()
        tkinter.messagebox.showerror("Startup Error", error_msg, parent=root_err)
        root_err.destroy()
        sys.exit(1)


    # 2. Set CustomTkinter appearance (once)
    customtkinter.set_appearance_mode("System")
    customtkinter.set_default_color_theme("blue")
    # Consider making scaling configurable or based on system DPI later
    customtkinter.set_widget_scaling(1.1)
    customtkinter.set_window_scaling(1.1)

    # 3. Attempt to load the last used directory
    initial_dir_for_app = load_last_directory()
    # If load_last_directory returns None (no config, or invalid path in config),
    # initial_dir_for_app will be None. The VideoTrimmerApp.__init__ will handle this
    # by creating the overlay for the user to select a directory.

    # 4. Create and run the application
    app_instance = None # For error handling scope
    try:
        app_instance = VideoTrimmerApp(initial_input_dir=initial_dir_for_app)
        if app_instance and app_instance.winfo_exists():
            app_instance.mainloop()
        else:
            # This case should ideally be caught by errors within VideoTrimmerApp init
            print("Application window failed to initialize or was closed prematurely before mainloop.")
            cleanup_temp_files()
            sys.exit(1)
    except Exception as e:
        # Catch-all for unexpected errors during app instantiation or mainloop
        print(f"Unhandled exception during app initialization or mainloop: {e}")
        import traceback
        traceback.print_exc()
        error_message_to_show = f"The application encountered a critical error and needs to close:\n\n{type(e).__name__}: {e}"
        if app_instance and hasattr(app_instance, 'show_error_and_quit') and app_instance.winfo_exists():
            # If app instance exists and is functional enough to show its own error
            app_instance.show_error_and_quit(error_message_to_show)
        else:
            # Fallback to a basic Tkinter error message if app instance is not available/usable
            root_crash_err = tkinter.Tk()
            root_crash_err.withdraw()
            tkinter.messagebox.showerror("Application Critical Error", error_message_to_show, parent=root_crash_err)
            if root_crash_err.winfo_exists(): root_crash_err.destroy()
        cleanup_temp_files() # Ensure cleanup is attempted
        sys.exit(1)
    finally:
        # This block will run whether an exception occurred or not,
        # but only after the try block (including mainloop) completes or an unhandled exception propagates.
        # on_closing() should handle cleanup if app closes normally.
        # If an exception caused premature exit before on_closing, cleanup here is a failsafe.
        # However, daemonic threads might still be running if main thread exits abruptly.
        print("Application has exited or encountered a fatal error.")