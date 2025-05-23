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
INITIAL_VIDEO_DIRECTORY = ''
VIDEO_EXTENSIONS = ('*.mp4', '*.mov', '*.avi', '*.mkv', '*.wmv', '*.flv') # These are glob patterns
RECENT_FILES_COUNT = 5
THUMBNAIL_WIDTH = 320
THUMBNAIL_HEIGHT = 180
THUMBNAIL_UPDATE_DELAY_MS = 300
TRIM_SUFFIX = "_trimmy"
SCRUB_INCREMENT = 0.5
temp_files_to_cleanup = []
# placeholder_img_pil is defined in __init__ now for CTkImage
BROWSE_OPTION = "Browse..."
STATUS_MESSAGE_CLEAR_DELAY_MS = 5000
FILENAME_INVALID_CHARS = r'/\:*?"<>|'
CONFIG_FILENAME = "config.json"

# --- Helper Functions (Assumed to be correct from previous step) ---
# format_time, format_size, get_parent_directories, load_last_directory, 
# save_last_directory, get_video_metadata, find_recent_videos, 
# extract_thumbnail, cleanup_temp_files
# Make sure these functions are present and correct as in your previous version.
# For brevity, they are not repeated here but are crucial.
def format_time(seconds):
    if seconds is None or not isinstance(seconds, (int, float)) or seconds < 0:
        return "00:00:00"
    try:
        if seconds == float('inf') or seconds != seconds:
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
    while size_bytes >= 1024 and i < len(size_name)-1: size_bytes /= 1024.0; i += 1
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
    print("No valid last directory found in config.")
    return None

def save_last_directory(directory_path):
    config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
    config = {"last_input_directory": directory_path}
    try:
        with open(config_path, 'w') as f: json.dump(config, f, indent=4)
        print(f"Saved last directory to config: {directory_path}")
        return True
    except (IOError, Exception) as e: print(f"Error saving config file ({config_path}): {e}"); return False

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
    except json.JSONDecodeError as e: print(f"ffprobe JSON error: {e}\n{process.stdout}"); return None, None, None, None
    except Exception as e: print(f"Metadata error: {e}"); return None, None, None, None

def find_recent_videos(directory, count):
    if not directory or not os.path.isdir(directory): print(f"Video search dir invalid: {directory}"); return []
    all_videos = []
    for ext_pattern in VIDEO_EXTENSIONS: # ext_pattern is like '*.mp4'
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
    for f in list(temp_files_to_cleanup): 
        try:
            if f and os.path.exists(f): os.remove(f); cleaned_count +=1
        except OSError as e: print(f"Error removing temp file {f}: {e}"); errors += 1
        except Exception as e: print(f"Unexpected error removing temp file {f}: {e}"); errors += 1
        finally:
             if f in temp_files_to_cleanup: temp_files_to_cleanup.remove(f) 
    print(f"Cleanup finished. Removed {cleaned_count} files, {errors} errors."); temp_files_to_cleanup = []

# --- CustomFilenameDialog Class (Assumed correct) ---
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

        # ... (Variable initializations from your code) ...
        if not initial_input_dir or not os.path.isdir(initial_input_dir):
            print("No initial directory selected.")
            initial_input_dir = None
        self.current_input_directory = os.path.normpath(initial_input_dir) if initial_input_dir else None
        self.output_directory = self.current_input_directory
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

        self.title("Trimmy v.0.8")
        self.geometry("700x900")
        self.resizable(False, False)

        # --- CTkImage Setup for Thumbnails ---
        self.placeholder_pil_image = Image.new('RGB', (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), color='gray')
        self.placeholder_ctk_image = customtkinter.CTkImage(light_image=self.placeholder_pil_image,
                                                             dark_image=self.placeholder_pil_image,
                                                             size=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
        self.current_start_thumb_ctk = self.placeholder_ctk_image
        self.current_end_thumb_ctk = self.placeholder_ctk_image
        # --- End CTkImage Setup ---

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_columnconfigure(3, weight=0)

        # --- Row 0, 1: Location ---
        self.location_label = customtkinter.CTkLabel(self, text="Location:")
        self.location_label.grid(row=0, column=0, columnspan=4, padx=20, pady=(20, 5), sticky="w")
        self.location_combobox = customtkinter.CTkComboBox(self, values=[], command=self.on_location_selected, state="readonly")
        self.location_combobox.grid(row=1, column=0, columnspan=4, padx=20, pady=(0, 15), sticky="ew")

        self.location_overlay_canvas = tkinter.Canvas(self, highlightthickness=0, bg=self.cget("bg"), bd=0)
        self.location_overlay_canvas.place(in_=self.location_combobox, relx=0, rely=0, relwidth=1, relheight=1)
        self.location_overlay_canvas.bind("<Button-1>", self.on_location_combobox_clicked)

        # --- Row 2, 3: Select Video & Refresh ---
        self.video_select_label = customtkinter.CTkLabel(self, text="Select Video:")
        self.video_select_label.grid(row=2, column=0, columnspan=2, padx=20, pady=(5, 5), sticky="w")
        # MODIFICATION: Initialize with a placeholder value and set it.
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

        # --- Row 5-8: Sliders & Scrub ---
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

        # --- Row 9: Thumbnails ---
        self.thumb_frame = customtkinter.CTkFrame(self)
        self.thumb_frame.grid(row=9, column=0, columnspan=4, padx=20, pady=10, sticky="ew")
        self.thumb_frame.grid_columnconfigure(0, weight=1); self.thumb_frame.grid_columnconfigure(1, weight=1)
        self.start_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="Start Frame"); self.start_thumb_label_text.grid(row=0, column=0, pady=(5,2))
        self.start_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=self.current_start_thumb_ctk); self.start_thumb_label.grid(row=1, column=0, padx=10, pady=(0,10))
        self.end_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="End Frame"); self.end_thumb_label_text.grid(row=0, column=1, pady=(5,2))
        self.end_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=self.current_end_thumb_ctk); self.end_thumb_label.grid(row=1, column=1, padx=10, pady=(0,10))

        # ... (Rest of the UI layout: Destination, Rename Checkbox, Status Label, Button Frame - assumed correct) ...
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
        self.button_frame.grid_columnconfigure(0, weight=1)
        self.button_frame.grid_columnconfigure(1, weight=0)
        self.button_frame.grid_columnconfigure(2, weight=0)
        self.button_frame.grid_columnconfigure(3, weight=0)
        self.button_frame.grid_columnconfigure(4, weight=1)
        self.trim_button = customtkinter.CTkButton(self.button_frame, text="Trim", command=lambda: self.start_trim_thread(delete_original=False))
        self.trim_button.grid(row=0, column=1, padx=10, pady=5)
        self.trim_delete_button = customtkinter.CTkButton(self.button_frame, text="Trim & Delete", command=lambda: self.start_trim_thread(delete_original=True), fg_color="#D32F2F", hover_color="#B71C1C")
        self.trim_delete_button.grid(row=0, column=3, padx=10, pady=5)

        # Initial setup
        self.populate_location_dropdown()
        self.update_destination_dropdown()
        self.refresh_video_list()
        # self.display_placeholder_thumbnails() # Already handled by CTkImage init and refresh if no video
        if not self.video_path: self.disable_ui_components(disable=True)
        else: self.disable_ui_components(disable=False)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.center_window()

    def initialize_location_combobox(self):

        self.location_combobox.set(BROWSE_OPTION)
        self.location_combobox.configure(state="readonly")


    def on_location_combobox_clicked(self, event=None):
        new_dir = tkinter.filedialog.askdirectory(initialdir=os.getcwd(), title="Select Video Directory")
        if new_dir and os.path.isdir(new_dir):
            self.current_input_directory = os.path.normpath(new_dir)
            self.add_recent_directory(new_dir)
            save_last_directory(new_dir)
            self.populate_location_dropdown()  # Switches to real recent-list
            self.refresh_video_list()
        if hasattr(self, "location_overlay_canvas"):
            self.location_overlay_canvas.destroy()
            self.location_overlay_canvas = None

    def add_recent_directory(self, new_path):
        """
        Add a new directory to recent list and save to config.json
        """
        config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
        try:
            config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)

            recent = config.get("recent_input_directories", [])
            recent = [os.path.normpath(p) for p in recent if os.path.isdir(p) and p != new_path]
            recent.insert(0, os.path.normpath(new_path))
            config["recent_input_directories"] = recent[:5]  # keep max 5

            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Failed to update recent directory list: {e}")

    def center_window(self): # Assumed correct
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = self.winfo_width()
        window_height = self.winfo_height()
        x_coord = int((screen_width / 2) - (window_width / 2))
        y_coord = int((screen_height / 2) - (window_height / 2) - 30) 
        self.geometry(f"{window_width}x{window_height}+{x_coord}+{y_coord}")

    def disable_ui_components(self, disable=True): # Assumed mostly correct, focus on video_combobox state in refresh
        state_val = "disabled" if disable else "normal"
        widgets_to_toggle = [
            self.start_slider, self.end_slider,
            self.start_scrub_left_button, self.start_scrub_right_button,
            self.end_scrub_left_button, self.end_scrub_right_button,
            self.trim_button, self.trim_delete_button,
            self.destination_combobox,
            self.refresh_button, 
            self.rename_checkbox
        ]
        if self.is_processing: 
            state_val = "disabled" 
            if self.refresh_button: self.refresh_button.configure(state="disabled")

        for widget in widgets_to_toggle:
            if widget: widget.configure(state=state_val)
        
        # Video combobox state is primarily handled by refresh_video_list based on content
        if self.video_combobox:
            if disable and not self.video_filenames: # Explicitly ensure "No videos found" text if disabling and no files
                 self.video_combobox.configure(values=[])
                 self.video_combobox.set("No videos found")
                 self.video_combobox.configure(state="disabled")
            elif disable: # Disabling for other reasons (e.g. processing, or no video loaded)
                self.video_combobox.configure(state="disabled")
            elif not disable and self.video_filenames: # Enabling and have videos
                self.video_combobox.configure(state="normal")
            elif not disable and not self.video_filenames: # Enabling but no videos (should stay disabled and show placeholder)
                 self.video_combobox.configure(values=[])
                 self.video_combobox.set("No videos found")
                 self.video_combobox.configure(state="disabled")


        if disable:
            if not self.video_path: 
                self.display_placeholder_thumbnails()
                self.file_info_display.configure(text="Select a video")
                self.start_time_label.configure(text="Start Time: --:--:--.---")
                self.end_time_label.configure(text="End Time: --:--:--.---")
                if self.start_slider: self.start_slider.set(0)
                if self.end_slider: self.end_slider.set(1.0) 
        else: 
            if not self.video_path:
                 # If enabling UI in general, but no video is actually loaded,
                 # many controls should remain disabled.
                 # This case is complex; refresh_video_list should primarily handle enabling based on video load.
                 pass # refresh_video_list and on_video_selected are better places to manage fine-grained enabling

    def refresh_video_list(self, preserve_selection=False):
        previously_selected_filename = None
        if preserve_selection and self.video_path:
            previously_selected_filename = os.path.basename(self.video_path)

        self.recent_videos = find_recent_videos(self.current_input_directory, RECENT_FILES_COUNT)
        self.video_filenames = [os.path.basename(p) for p in self.recent_videos]

        if self.video_filenames:
            self.video_combobox.configure(values=self.video_filenames, state="normal")
            target_selection = None
            new_selection_made = False
            if previously_selected_filename and previously_selected_filename in self.video_filenames:
                target_selection = previously_selected_filename
            else:
                target_selection = self.video_filenames[0]
                new_selection_made = True
            
            self.video_combobox.set(target_selection) # Set the text

            if new_selection_made or not self.video_path: # If new video selected OR if no video was loaded prior
                self.after(10, lambda: self.on_video_selected(target_selection))
            # else: # Selection preserved and video was already loaded, UI should be fine
                # self.disable_ui_components(disable=False) # Ensure UI is enabled
        else: # No videos found
            self.video_path = None
            self.video_combobox.configure(values=[]) # Clear values
            self.video_combobox.set("No videos found") # Set text
            self.video_combobox.configure(state="disabled") # THEN disable
            self.disable_ui_components(disable=True)
            dir_label = os.path.basename(self.current_input_directory) if self.current_input_directory else "selected location"
        self.update_status(f"No videos found in {dir_label}", "orange", is_temporary=True)
            # self.output_directory = None # Keep output dir as is
        
        if not self.is_processing and self.refresh_button:
            self.refresh_button.configure(state="normal")


    def display_placeholder_thumbnails(self):
        self.current_start_thumb_ctk = self.placeholder_ctk_image
        self.current_end_thumb_ctk = self.placeholder_ctk_image
        if self.start_thumb_label and self.start_thumb_label.winfo_exists():
            self.start_thumb_label.configure(image=self.current_start_thumb_ctk)
        if self.end_thumb_label and self.end_thumb_label.winfo_exists():
            self.end_thumb_label.configure(image=self.current_end_thumb_ctk)

    def schedule_thumbnail_update(self, time_seconds, for_start_thumb):
        if not self.video_path:
            self.display_placeholder_thumbnails() # Show placeholders if no video
            return

        job_attr = 'start_thumb_job' if for_start_thumb else 'end_thumb_job'
        existing_job = getattr(self, job_attr)
        if existing_job:
            self.after_cancel(existing_job)
        
        # Display placeholder immediately while new one is scheduled
        label_to_update = self.start_thumb_label if for_start_thumb else self.end_thumb_label
        if label_to_update and label_to_update.winfo_exists():
            label_to_update.configure(image=self.placeholder_ctk_image)
        if for_start_thumb:
            self.current_start_thumb_ctk = self.placeholder_ctk_image
        else:
            self.current_end_thumb_ctk = self.placeholder_ctk_image

        new_job = self.after(THUMBNAIL_UPDATE_DELAY_MS, lambda t=time_seconds, fst=for_start_thumb: self.generate_and_display_thumbnail(t, fst))
        setattr(self, job_attr, new_job)

    def generate_and_display_thumbnail(self, time_seconds, for_start_thumb):
        if not self.video_path or not os.path.exists(self.video_path):
            self.display_placeholder_thumbnails()
            return

        temp_thumb_dir = tempfile.gettempdir()
        thumb_filename = f"trimmy_thumb_{uuid.uuid4().hex}.jpg"
        thumb_path = os.path.join(temp_thumb_dir, thumb_filename)
        
        # Placeholder already set by schedule_thumbnail_update
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

        new_image_to_set = self.placeholder_ctk_image

        if success and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            try:
                pil_img = Image.open(thumb_path)
                ctk_img = customtkinter.CTkImage(light_image=pil_img,
                                                 dark_image=pil_img, # Same for dark mode unless specified
                                                 size=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
                new_image_to_set = ctk_img
            except Exception as e:
                print(f"Error loading thumbnail image {thumb_path}: {e}")
                if os.path.exists(thumb_path) and thumb_path in temp_files_to_cleanup:
                    try: temp_files_to_cleanup.remove(thumb_path); os.remove(thumb_path)
                    except: pass # Ignore cleanup error
        else: # Extraction failed or file is bad/empty
            if os.path.exists(thumb_path) and thumb_path in temp_files_to_cleanup:
                 try: temp_files_to_cleanup.remove(thumb_path); os.remove(thumb_path)
                 except: pass

        if for_start_thumb:
            self.current_start_thumb_ctk = new_image_to_set
        else:
            self.current_end_thumb_ctk = new_image_to_set
        
        label.configure(image=new_image_to_set)

    # ... (on_refresh_clicked, populate_location_dropdown, on_location_selected, update_destination_dropdown, on_destination_selected,
    #      on_video_selected, load_video_data, update_info_display, update_start_time, update_end_time,
    #      scrub_start_left, scrub_start_right, scrub_end_left, scrub_end_right,
    #      start_trim_thread, run_ffmpeg_trim, post_trim_success, reset_ui_after_processing,
    #      update_status, _revert_to_persistent_status, show_error_and_quit, on_closing - assumed correct from previous state)
    def on_refresh_clicked(self):
        """Handles the refresh button click."""
        print("Refresh button clicked.")
        if self.is_processing:
            self.update_status("Cannot refresh while processing.", "orange", is_temporary=True)
            return
        self.update_status("Refreshing video list...", "blue", is_temporary=True)
        self.refresh_video_list(preserve_selection=True)
    def on_location_selected(self, selected_path):
        """Handles selection from the location combobox."""
        if selected_path == BROWSE_OPTION:
            new_dir = tkinter.filedialog.askdirectory(initialdir=self.current_input_directory, title="Select Video Directory")
            if new_dir and os.path.isdir(new_dir):
                self.current_input_directory = os.path.normpath(new_dir)
            else: 
                self.location_combobox.set(self.current_input_directory) 
                return
        else:
            self.current_input_directory = os.path.normpath(selected_path)
        print(f"Location changed to: {self.current_input_directory}")
        save_last_directory(self.current_input_directory)
        self.populate_location_dropdown() 
        self.update_destination_dropdown() 
        self.video_path = None 
        self.refresh_video_list() 
        if not self.video_filenames: 
            self.disable_ui_components(True)
            self.update_info_display() 
            self.display_placeholder_thumbnails()

    def populate_location_dropdown(self):
        recent_dirs = []

        if self.current_input_directory and os.path.isdir(self.current_input_directory):
            display_path = self.current_input_directory
        else:
            display_path = BROWSE_OPTION
        # Load recent from config
        config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
        recent_dirs = []
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    recent_dirs = config.get("recent_input_directories", [])
                    recent_dirs = [p for p in recent_dirs if os.path.isdir(p)]
            except Exception as e:
                print(f"Error loading recent dirs: {e}")

        self.location_options = [BROWSE_OPTION] + recent_dirs
        self.location_combobox.configure(values=[BROWSE_OPTION] + recent_dirs)
        self.location_combobox.set(display_path)

    def update_destination_dropdown(self):
        """Populates the destination dropdown."""
        if not self.output_directory or not os.path.isdir(self.output_directory):
            if self.current_input_directory and os.path.isdir(self.current_input_directory):
                self.output_directory = self.current_input_directory
            else: 
                self.output_directory = os.getcwd()
        parents_of_output = get_parent_directories(self.output_directory)
        destination_paths = [BROWSE_OPTION]
        if self.output_directory not in destination_paths : destination_paths.append(self.output_directory)
        if self.current_input_directory and self.current_input_directory != self.output_directory and self.current_input_directory not in destination_paths:
            destination_paths.append(self.current_input_directory)
        for p in parents_of_output:
            if p not in destination_paths: destination_paths.append(p)
        self.destination_options = [p for i, p in enumerate(destination_paths) if p not in destination_paths[:i]] 
        self.destination_combobox.configure(values=self.destination_options)
        if self.output_directory in self.destination_options:
            self.destination_combobox.set(self.output_directory)
        elif self.destination_options:
            self.destination_combobox.set(self.destination_options[0])
    def on_destination_selected(self, selected_path):
        """Handles selection from the destination combobox."""
        if selected_path == BROWSE_OPTION:
            new_dir = tkinter.filedialog.askdirectory(initialdir=self.output_directory, title="Select Output Directory")
            if new_dir and os.path.isdir(new_dir):
                self.output_directory = os.path.normpath(new_dir)
        else:
            self.output_directory = os.path.normpath(selected_path)
        print(f"Output directory set to: {self.output_directory}")
        self.update_destination_dropdown() 
    def on_video_selected(self, selected_filename):
        """Handles selection from the video combobox."""
        if self.is_processing: return
        if not selected_filename or selected_filename == "No videos found" or selected_filename == "Initializing...": # Added Initializing
            self.video_path = None
            self.disable_ui_components(True)
            self.update_info_display() 
            self.display_placeholder_thumbnails()
            return
        self.video_path = os.path.join(self.current_input_directory, selected_filename)
        if not os.path.exists(self.video_path):
            self.update_status(f"Error: {selected_filename} not found.", "red", is_temporary=True)
            self.video_path = None
            self.refresh_video_list(preserve_selection=False) 
            return
        print(f"Video selected: {self.video_path}")
        self.load_video_data()
    def load_video_data(self):
        """Loads metadata for the selected video and updates UI."""
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
            self.disable_ui_components(True)
            self.update_info_display() 
            self.display_placeholder_thumbnails()
            if self.video_combobox: self.video_combobox.set("Select video") 
            return
        self.duration = duration_s
        self.original_size_bytes = size_bytes
        self.current_filename = os.path.basename(self.video_path)
        self.current_creation_time = ctime_str
        self.current_size_str = size_str
        self.current_duration_str = format_time(self.duration)
        self.start_time = 0.0
        self.end_time = self.duration
        self.start_slider.configure(to=self.duration)
        self.end_slider.configure(to=self.duration)
        self.start_slider.set(self.start_time)
        self.end_slider.set(self.end_time)
        self.update_start_time(self.start_time) 
        self.update_end_time(self.end_time)   
        self.update_info_display()
        self.disable_ui_components(False) 
        self.update_status(f"Loaded: {self.current_filename}", "green", is_temporary=True)
        self.rename_checkbox.deselect() 
        self.pending_custom_filename = None
    def update_info_display(self):
        """Updates the file information display area."""
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
        value = float(value_str_or_float)
        if self.is_processing: return
        if value >= self.end_time - 0.1:
            value = max(0, self.end_time - 0.1)
        self.start_time = value
        self.start_slider.set(self.start_time)
        self.start_time_label.configure(text=f"Start Time: {format_time(self.start_time)}")
        self.schedule_thumbnail_update(self.start_time, for_start_thumb=True)
    def update_end_time(self, value_str_or_float): # Accept float directly too
        """Callback for end slider change."""
        value = float(value_str_or_float)
        if self.is_processing: return
        self.end_time = min(self.duration, max(value, self.start_time)) 
        if self.end_slider.get() != self.end_time: 
            self.end_slider.set(self.end_time)
        self.end_time_label.configure(text=f"End Time: {format_time(self.end_time)}")
        self.schedule_thumbnail_update(self.end_time, for_start_thumb=False)
    def scrub_start_left(self):
        if not self.video_path or self.is_processing: return
        new_time = max(0, self.start_time - SCRUB_INCREMENT)
        self.start_slider.set(new_time)
        self.update_start_time(new_time)
    def scrub_start_right(self):
        if not self.video_path or self.is_processing: return
        new_time = min(self.end_time - 0.1, self.start_time + SCRUB_INCREMENT)
        self.start_slider.set(new_time)
        self.update_start_time(new_time)
    def scrub_end_left(self):
        if not self.video_path or self.is_processing: return
        new_time = max(self.start_time + 0.1, self.end_time - SCRUB_INCREMENT)
        self.end_slider.set(new_time)
        self.update_end_time(new_time)
    def scrub_end_right(self):
        if not self.video_path or self.is_processing:return
        new_time = min(self.duration, self.end_time + SCRUB_INCREMENT)
        self.end_slider.set(new_time)
        self.update_end_time(new_time)

    def start_trim_thread(self, delete_original=False):
        self.pending_custom_filename = None
        if self.is_processing: print("Already processing."); return
        if not self.video_path: self.update_status("No video selected.", "red", is_temporary=True); return
        if not self.output_directory or not os.path.isdir(self.output_directory):
            self.update_status("Invalid output directory. Please select.", "red", is_temporary=True)
            self.on_destination_selected(BROWSE_OPTION) 
            if not self.output_directory or not os.path.isdir(self.output_directory): 
                 return 
            self.update_status("Output directory selected. Try trimming again.", "orange", is_temporary=True)
            return
        if abs(self.end_time - self.start_time) < 0.1: self.update_status("Error: Start/End times too close.", "red", is_temporary=True); return
        if self.rename_checkbox.get() == 1:
            dialog = CustomFilenameDialog(self, title="Set Output Filename")
            custom_basename = dialog.get_input()
            if custom_basename is None: 
                self.rename_checkbox.deselect()
                self.update_status("Rename cancelled. Using default name if applicable.", "orange", is_temporary=True)
                self.pending_custom_filename = None
            elif not custom_basename: 
                self.rename_checkbox.deselect()
                self.update_status("Empty name provided. Using default name if applicable.", "orange", is_temporary=True)
                self.pending_custom_filename = None
            else:
                self.pending_custom_filename = custom_basename + ".mp4" 
        if delete_original:
            confirm_msg = f"Permanently delete the original file?\n\n{os.path.basename(self.video_path)}\n\nThis cannot be undone."
            if self.pending_custom_filename and self.pending_custom_filename != os.path.basename(self.video_path):
                 confirm_msg += f"\n\nThe trimmed clip will be saved as: {self.pending_custom_filename}"
            confirm = tkinter.messagebox.askyesno("Confirm Delete", confirm_msg, icon='warning', parent=self)
            if not confirm:
                self.update_status("Trim & Delete cancelled.", "orange", is_temporary=True)
                return
        self.is_processing = True
        self.disable_ui_components(disable=True) 
        self.update_status("Starting trim...", "blue", is_persistent_trim_status=False)
        temp_output_path_for_delete_op = None
        if delete_original:
            try:
                base_temp, ext_temp = os.path.splitext(os.path.basename(self.video_path))
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
        original_input_path = self.video_path 
        try:
            if not original_input_path or not os.path.exists(original_input_path):
                raise ValueError("Original video path is invalid or file missing at trim time.")
            input_filename_full = original_input_path
            input_basename_no_ext, input_ext = os.path.splitext(os.path.basename(input_filename_full))
            if delete_original:
                ffmpeg_output_target = temp_path_for_delete_op
                if not ffmpeg_output_target: raise ValueError("Temporary output path for delete operation is missing.")
                temp_files_to_cleanup.append(ffmpeg_output_target)
                if custom_final_name_mp4:
                    final_output_path_actual = os.path.join(self.output_directory, custom_final_name_mp4)
                else:
                    final_output_path_actual = os.path.join(self.output_directory, os.path.basename(input_filename_full))
            else: 
                target_ext = input_ext 
                if custom_final_name_mp4: 
                    file_base, file_ext_custom = os.path.splitext(custom_final_name_mp4) 
                    # Use the extension from custom_final_name_mp4 if it's valid, otherwise default or input_ext
                    # Assuming custom_final_name_mp4 is "basename.some_ext" or just "basename" (then use input_ext or .mp4)
                    # Current logic: custom_final_name_mp4 = custom_basename + ".mp4" so file_ext_custom is ".mp4"
                    actual_output_ext = file_ext_custom if file_ext_custom else target_ext # Fallback to original if custom has no ext
                    
                    ffmpeg_output_target = os.path.join(self.output_directory, f"{file_base}{actual_output_ext}")
                    final_output_path_actual = ffmpeg_output_target 
                    counter = 1
                    while os.path.exists(final_output_path_actual):
                        final_output_path_actual = os.path.join(self.output_directory, f"{file_base}_{counter}{actual_output_ext}")
                        counter += 1
                    ffmpeg_output_target = final_output_path_actual 
                else: 
                    base_trimmy = os.path.join(self.output_directory, f"{input_basename_no_ext}{TRIM_SUFFIX}{target_ext}")
                    ffmpeg_output_target = base_trimmy
                    counter = 1
                    final_output_path_actual = ffmpeg_output_target 
                    while os.path.exists(final_output_path_actual):
                        final_output_path_actual = os.path.join(self.output_directory, f"{input_basename_no_ext}{TRIM_SUFFIX}_{counter}{target_ext}")
                        counter += 1
                    ffmpeg_output_target = final_output_path_actual
            if final_output_path_actual is None: final_output_path_actual = ffmpeg_output_target 
            start_str = format_time(self.start_time) 
            trim_duration = max(0.1, self.end_time - self.start_time)
            command = ['ffmpeg', '-hide_banner', '-loglevel', 'error',
                       '-ss', start_str,                              
                       '-i', input_filename_full,
                       '-t', str(trim_duration),                     
                       '-c', 'copy',                                 
                       '-map', '0',                                  
                       '-avoid_negative_ts', 'make_zero',            
                       '-y', ffmpeg_output_target]                   
            self.after(0, lambda: self.update_status("Processing with FFmpeg...", "blue", is_persistent_trim_status=False))
            print(f"Running FFmpeg command: {' '.join(command)}")
            startupinfo = None
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
            stdout, stderr = process.communicate()
            if process.returncode == 0 and os.path.exists(ffmpeg_output_target) and os.path.getsize(ffmpeg_output_target) > 0:
                print(f"FFmpeg OK. Output to: {ffmpeg_output_target}")
                success_msg_base = f"Done! Trimmed: {os.path.basename(final_output_path_actual)}\n(in {os.path.basename(self.output_directory)})"
                if delete_original:
                    self.after(0, lambda: self.update_status("Finalizing and deleting original...", "blue", is_persistent_trim_status=False))
                    time.sleep(0.2) 
                    renamed_successfully = False
                    if os.path.abspath(ffmpeg_output_target) != os.path.abspath(final_output_path_actual):
                        if os.path.exists(final_output_path_actual):
                            print(f"Warning: Target path '{final_output_path_actual}' for rename already exists. Trying unique.")
                            f_base, f_ext = os.path.splitext(final_output_path_actual)
                            f_counter = 1
                            new_final_path = f"{f_base}_{f_counter}{f_ext}"
                            while os.path.exists(new_final_path):
                                f_counter += 1
                                new_final_path = f"{f_base}_{f_counter}{f_ext}"
                            final_output_path_actual = new_final_path # Update to the new unique path
                            print(f"Using new unique final path: {final_output_path_actual}")
                            success_msg_base = f"Done! Trimmed: {os.path.basename(final_output_path_actual)}\n(in {os.path.basename(self.output_directory)})" # Update msg
                        try:
                            os.rename(ffmpeg_output_target, final_output_path_actual)
                            renamed_successfully = True
                        except OSError as rename_err:
                             print(f"Error renaming {ffmpeg_output_target} to {final_output_path_actual}: {rename_err}")
                             # Keep ffmpeg_output_target as the actual if rename fails
                             final_output_path_actual = ffmpeg_output_target 
                             success_msg_base = f"Done! Trimmed to temp: {os.path.basename(final_output_path_actual)}\nRename failed."

                    else: # Temp IS the final path (or no rename needed conceptually)
                        renamed_successfully = True # Or, effectively, no rename was required for the trimmed file.
                    
                    if renamed_successfully and temp_path_for_delete_op in temp_files_to_cleanup and temp_path_for_delete_op == ffmpeg_output_target :
                        temp_files_to_cleanup.remove(temp_path_for_delete_op)
                    try:
                        print(f"Attempt delete: {input_filename_full}"); os.remove(input_filename_full); print(f"Delete OK: {input_filename_full}")
                        full_success_msg = f"{success_msg_base}\nOriginal file permanently deleted."
                        self.after(0, lambda: self.update_status(full_success_msg, "green", is_persistent_trim_status=True))
                        self.after(100, lambda p=final_output_path_actual: self.post_trim_success(p, deleted_original_path=input_filename_full))
                    except OSError as os_err:
                        error_message = f"Trimmed to {os.path.basename(final_output_path_actual)} BUT OS ERROR deleting original: {os_err}"
                        print(error_message)
                        self.after(0, lambda: self.update_status(error_message, "orange", is_persistent_trim_status=True)) 
                        self.after(100, lambda p=final_output_path_actual: self.post_trim_success(p, deleted_original_path=None)) 
                else: 
                    self.after(0, lambda: self.update_status(success_msg_base, "green", is_persistent_trim_status=True))
                    self.after(100, lambda p=final_output_path_actual: self.post_trim_success(p))
            else:
                error_message = f"FFmpeg failed (code {process.returncode}):\n{stderr[-500:] if stderr else 'No stderr'}"
                if not (os.path.exists(ffmpeg_output_target) and os.path.getsize(ffmpeg_output_target) > 0) and process.returncode == 0:
                    error_message = "FFmpeg reported success, but output file is missing or empty."
                print(error_message)
                self.after(0, lambda: self.update_status(error_message, "red", is_persistent_trim_status=True))
                if ffmpeg_output_target and os.path.exists(ffmpeg_output_target):
                    print(f"FFmpeg failed, cleaning its partial output: {ffmpeg_output_target}")
                    try: os.remove(ffmpeg_output_target)
                    except OSError as e: print(f"Error cleaning failed ffmpeg output: {e}")
                    if ffmpeg_output_target in temp_files_to_cleanup: # If it was added (e.g. delete_original path)
                        try: temp_files_to_cleanup.remove(ffmpeg_output_target)
                        except ValueError: pass # Already removed or never added
                self.after(100, self.reset_ui_after_processing) 
        except Exception as e:
            import traceback
            detailed_error = traceback.format_exc()
            error_message = f"Unexpected error during trim: {type(e).__name__}: {e}\n{detailed_error}"
            print(error_message)
            self.after(0, lambda: self.update_status(f"Unexpected error: {e}", "red", is_persistent_trim_status=True))
            # Ensure any temp ffmpeg output target is cleaned if error occurs after its creation
            if ffmpeg_output_target and os.path.exists(ffmpeg_output_target) and ffmpeg_output_target in temp_files_to_cleanup:
                try:
                    os.remove(ffmpeg_output_target)
                    temp_files_to_cleanup.remove(ffmpeg_output_target)
                except Exception as clean_e: print(f"Error cleaning temp ffmpeg output after error: {clean_e}")
            self.after(100, self.reset_ui_after_processing) 
        finally:
            self.pending_custom_filename = None
    def post_trim_success(self, output_filepath, deleted_original_path=None):
        print(f"Trim process successful. Final file: {output_filepath}")
        self.is_processing = False 
        should_preserve = True
        if deleted_original_path and self.video_path == deleted_original_path:
            self.video_path = None 
            should_preserve = False # Original is gone, don't try to preserve its selection
        self.after(10, lambda: self.refresh_video_list(preserve_selection=should_preserve))
    def reset_ui_after_processing(self):
        self.is_processing = False
        self.pending_custom_filename = None
        self.refresh_video_list(preserve_selection=True)
    def update_status(self, message, color="gray", is_persistent_trim_status=False, is_temporary=False):
        if self.status_message_clear_job:
            self.after_cancel(self.status_message_clear_job)
            self.status_message_clear_job = None
        def _update_label():
            if hasattr(self, 'status_label') and self.status_label and self.status_label.winfo_exists(): 
                 self.status_label.configure(text=message, text_color=color)
        if is_persistent_trim_status:
            self.last_trim_status_message = message
            self.last_trim_status_color = color
            self.temporary_status_active = False
            self.after(0, _update_label)
        elif is_temporary:
            self.temporary_status_active = True
            self.after(0, _update_label)
            self.status_message_clear_job = self.after(STATUS_MESSAGE_CLEAR_DELAY_MS, self._revert_to_persistent_status)
        else: 
            self.temporary_status_active = False 
            self.after(0, _update_label)
    def _revert_to_persistent_status(self):
        self.temporary_status_active = False
        current_text = self.last_trim_status_message if self.last_trim_status_message else ""
        current_color = self.last_trim_status_color if self.last_trim_status_message else "gray"
        def _update_label():
            if hasattr(self, 'status_label') and self.status_label and self.status_label.winfo_exists():
                self.status_label.configure(text=current_text, text_color=current_color)
        self.after(0, _update_label)
        self.status_message_clear_job = None
    def show_error_and_quit(self, message): # Assumed correct
        print(f"FATAL ERROR: {message}")
        temp_root_created = False
        if not hasattr(self, 'title') or not self.winfo_exists():
            root = tkinter.Tk(); root.withdraw(); parent_for_messagebox = root; temp_root_created = True
        else: parent_for_messagebox = self
        if parent_for_messagebox.winfo_exists(): tkinter.messagebox.showerror("Critical Error", message, parent=parent_for_messagebox)
        if temp_root_created: root.destroy()
        elif self.winfo_exists(): self.destroy()
        cleanup_temp_files(); sys.exit(1)
    def on_closing(self): # Assumed correct
        print("Closing application.")
        if self.start_thumb_job: self.after_cancel(self.start_thumb_job)
        if self.end_thumb_job: self.after_cancel(self.end_thumb_job)
        if self.status_message_clear_job: self.after_cancel(self.status_message_clear_job)
        if self.is_processing: print("Warning: Closing while a trim operation is in progress.")
        cleanup_temp_files()
        if self.winfo_exists(): self.destroy()
        sys.exit(0)


# --- Script Entry Point (Assumed correct from previous versions) ---
if __name__ == "__main__":
    try:
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(['ffprobe', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception:
        print("ERROR: FFmpeg or ffprobe not found. Ensure they are in PATH.")
        sys.exit(1)

    customtkinter.set_appearance_mode("System")
    customtkinter.set_default_color_theme("blue")
    customtkinter.set_widget_scaling(1.1)
    customtkinter.set_window_scaling(1.1)

    app = VideoTrimmerApp(initial_input_dir=None)
    app.mainloop()
    customtkinter.set_appearance_mode("System"); customtkinter.set_default_color_theme("blue")
    initial_dir_loaded = load_last_directory()
    if initial_dir_loaded is None: initial_dir_loaded = INITIAL_VIDEO_DIRECTORY 
    final_initial_dir = None; needs_user_selection = False
    if initial_dir_loaded and initial_dir_loaded != 'path/to/your/video/clips' and os.path.isdir(initial_dir_loaded):
        final_initial_dir = initial_dir_loaded
        print(f"Using initial directory: {final_initial_dir}")
    else: needs_user_selection = True 
    if needs_user_selection:
        root_prompt = tkinter.Tk(); root_prompt.withdraw()
        message = f"Initial directory not found or invalid:\n'{initial_dir_loaded}'\n\nPlease select your primary video directory."
        tkinter.messagebox.showwarning("Initial Directory Setup", message, parent=None)
        selected_dir = tkinter.filedialog.askdirectory(title="Select Starting Video Directory", parent=root_prompt)
        if selected_dir and os.path.isdir(selected_dir):
            final_initial_dir = selected_dir
            print(f"User selected initial directory: {final_initial_dir}")
            save_last_directory(final_initial_dir)
        else:
            if selected_dir is not None: tkinter.messagebox.showerror("Error", "No valid directory selected. Application cannot start.", parent=root_prompt)
            else: print("Directory selection cancelled by user. Application cannot start.")
            if root_prompt.winfo_exists(): root_prompt.destroy()
            sys.exit(1) 
        if root_prompt.winfo_exists(): root_prompt.destroy()
    if final_initial_dir and os.path.isdir(final_initial_dir):
        app = None 
        try:
            customtkinter.set_widget_scaling(1.1)
            customtkinter.set_window_scaling(1.1)

            app = VideoTrimmerApp(initial_input_dir=final_initial_dir)
            if app and app.winfo_exists(): app.mainloop()
            else: print("Application window failed to initialize or was closed prematurely."); cleanup_temp_files(); sys.exit(1)
        except Exception as e:
            print(f"Unhandled exception during app initialization or mainloop: {e}")
            import traceback; traceback.print_exc()
            if app and hasattr(app, 'show_error_and_quit') : app.show_error_and_quit(f"Application crashed: {e}")
            else: tkinter.messagebox.showerror("Critical Error", f"Application crashed during startup: {e}")
            cleanup_temp_files(); sys.exit(1)
    else:
        print("Application exiting due to no valid initial directory.");
        root_final_err = tkinter.Tk(); root_final_err.withdraw()
        tkinter.messagebox.showerror("Error", "No valid initial video directory set. Application cannot start.", parent=root_final_err)
        root_final_err.destroy(); cleanup_temp_files(); sys.exit(1)