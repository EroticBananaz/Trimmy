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
from PIL import Image, ImageTk
from dateutil import parser as date_parser

# --- Configuration & Global Variables ---
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

# --- Helper Functions (Assumed correct from previous versions) ---
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

# save_last_directory is effectively handled by add_recent_directory now
# def save_last_directory(directory_path): ...

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
            if output_path not in temp_files_to_cleanup:
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

class VideoTrimmerApp(customtkinter.CTk):
    def __init__(self, initial_input_dir):
        super().__init__()

        if initial_input_dir and os.path.isdir(initial_input_dir):
            self.current_input_directory = os.path.normpath(initial_input_dir)
        else:
            self.current_input_directory = None
            print("No valid initial directory provided to app, overlay will be used.")

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
        self.location_overlay_canvas = None
        self.up_directory_button = None
        self.vlc_instance = None
        self.vlc_player = None
        self.preview_video_widget = None # This will be the Tkinter Frame for VLC
        self.is_preview_loaded = False
        self.temp_preview_path = None
        self.preview_playing = False # To track play/pause state for button icon
        self.play_icon_image = None
        self.pause_icon_image = None
        self.current_icon_photoimage = None # For displaying on canvas
        self.icon_canvas = None
        self.icon_animation_job = None
        self.icon_alpha = 0 # For fading, 0 (transparent) to 255 (opaque) if we use PIL for alpha
        self.icon_size_scale = 1.0
        try:
            # Assuming icons are in the same directory as the script or an 'assets' subfolder
            script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            play_path = os.path.join(script_dir, "assets/play-button.png") # ADJUST PATH
            pause_path = os.path.join(script_dir, "assets/pause-button.png") # ADJUST PATH

            if os.path.exists(play_path) and os.path.exists(pause_path):
                self.play_icon_image_pil = Image.open(play_path).convert("RGBA")
                self.pause_icon_image_pil = Image.open(pause_path).convert("RGBA")
                print("Play and Pause icons loaded.")
            else:
                print("Error: Play or Pause icon not found. Animation will be disabled.")
                # Fallback or disable icon feature
                self.play_icon_image_pil = None
                self.pause_icon_image_pil = None

        except Exception as e:
            print(f"Error loading icon images: {e}")
            self.play_icon_image_pil = None
            self.pause_icon_image_pil = None

        try:
            import vlc
            self.vlc_instance = vlc.Instance()
            self.vlc_player = self.vlc_instance.media_player_new()
            print("VLC initialized successfully.")
        except Exception as e:
            print(f"VLC initialization error: {e}. Preview player will be disabled.")
            tkinter.messagebox.showwarning("VLC Missing", 
                                           "VLC library or player not found. Video preview will be disabled.\n"
                                           "Please ensure VLC media player is installed.")
        self.title("Trimmy v.0.8 - Up Button") # You can name this Trimmy V10 if you like
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
        self.location_combobox = customtkinter.CTkComboBox(self, values=[], command=self.on_location_selected)
        self.location_combobox.grid(row=1, column=0, columnspan=3, padx=(20,5), pady=(0, 15), sticky="ew")

        self.up_directory_button = customtkinter.CTkButton(self, text=u"\u25B2", width=40,
                                                           command=self.on_up_directory_clicked)
        self.up_directory_button.grid(row=1, column=3, padx=(0, 20), pady=(0,15), sticky="e")

        # --- MODIFIED: REMOVED THE FIRST DUPLICATE OVERLAY CREATION BLOCK ---
        # The first block that was here has been deleted.
        # This is now the ONLY block that handles overlay creation or normal combobox state.

        self.location_overlay_canvas = None
        if not self.current_input_directory:
            # 1. Configure the underlying disabled combobox - NO TEXT NEEDED HERE NOW
            self.location_combobox.configure(state="disabled")
            # self.location_combobox.set("") # Optional: Clear any default text explicitly

            # --- Mimicking CTkComboBox Appearance on Canvas ---
            # Get theme colors (these might need adjustment if your theme is very custom)
            try:
                combobox_bg_color = self._apply_appearance_mode(customtkinter.ThemeManager.theme["CTkComboBox"]["fg_color"])
                combobox_border_color = self._apply_appearance_mode(customtkinter.ThemeManager.theme["CTkComboBox"]["border_color"])
                combobox_text_color = self._apply_appearance_mode(customtkinter.ThemeManager.theme["CTkLabel"]["text_color"]) # Use label color for general text
                # For the dropdown arrow, CTkComboBox uses a specific button color
                combobox_button_color = self._apply_appearance_mode(customtkinter.ThemeManager.theme["CTkComboBox"]["button_color"])
                combobox_button_hover_color = self._apply_appearance_mode(customtkinter.ThemeManager.theme["CTkComboBox"]["button_hover_color"]) # Not used directly here but good to know

            except KeyError: # Fallback if theme keys are not as expected
                combobox_bg_color = "gray16" if customtkinter.get_appearance_mode().lower() == "dark" else "gray86"
                combobox_border_color = "gray40" if customtkinter.get_appearance_mode().lower() == "dark" else "gray60"
                combobox_text_color = "white" if customtkinter.get_appearance_mode().lower() == "dark" else "black"
                combobox_button_color = "gray25" if customtkinter.get_appearance_mode().lower() == "dark" else "gray75"


            self.location_overlay_canvas = tkinter.Canvas(self,
                                                        background=combobox_bg_color, # Use combobox bg
                                                        highlightthickness=customtkinter.ThemeManager.theme["CTkComboBox"]["border_width"], # Use theme border width
                                                        highlightbackground=combobox_border_color, # Use theme border color
                                                        bd=0,
                                                        insertbackground=combobox_text_color # Cursor color if it were editable (not relevant here)
                                                        )
            
            self.location_overlay_canvas.place(in_=self.location_combobox, relx=0, rely=0, relwidth=1, relheight=1)
            self.location_overlay_canvas.bind("<Button-1>", self.on_location_combobox_clicked)

            # --- Draw elements on the canvas ---
            # We need to wait for the canvas to be sized to draw accurately.
            # However, for initial placement, we can estimate or use fixed coords if combobox height is known.
            # A more robust way is to bind to <Configure> and redraw, or draw after update_idletasks.

            def draw_overlay_elements(event=None): # event is None if called directly
                if not self.location_overlay_canvas or not self.location_overlay_canvas.winfo_exists():
                    return

                self.location_overlay_canvas.delete("all") # Clear previous drawings if any (e.g. on resize)
                
                width = self.location_overlay_canvas.winfo_width()
                height = self.location_overlay_canvas.winfo_height()

                if width <=1 or height <=1: # Not yet sized
                    self.after(50, draw_overlay_elements) # Try again shortly
                    return

                # 1. Draw the main background (already set by canvas background)

                # 2. Draw the "Dropdown Arrow" box (mimicking the button part of CTkComboBox)
                #    The CTkComboBox arrow button is typically square-ish on the right.
                arrow_box_width = height - 4 # Make it slightly smaller than height, with some padding
                arrow_box_x1 = width - arrow_box_width - 2 # 2px padding from right edge
                arrow_box_y1 = 2 # 2px padding from top
                arrow_box_x2 = width - 2
                arrow_box_y2 = height - 2
                
                # For CTk this button often has rounded corners, which is hard for basic canvas.
                # We'll draw a simple rectangle.
                self.location_overlay_canvas.create_rectangle(arrow_box_x1, arrow_box_y1, 
                                                              arrow_box_x2, arrow_box_y2,
                                                              fill=combobox_button_color, # Color of the button area
                                                              outline=combobox_border_color, # Use border color for its outline
                                                              width=0) # No extra outline if fill is distinct

                # 3. Draw the arrow polygon (triangle)
                arrow_size = 6 # Size of the arrow
                arrow_center_x = arrow_box_x1 + (arrow_box_width / 2)
                arrow_center_y = arrow_box_y1 + (height / 2) -2 # Adjust vertical centering
                
                arrow_points = [
                    arrow_center_x - arrow_size, arrow_center_y - arrow_size / 2, # Top-left
                    arrow_center_x + arrow_size, arrow_center_y - arrow_size / 2, # Top-right
                    arrow_center_x, arrow_center_y + arrow_size / 2              # Bottom-center
                ]
                self.location_overlay_canvas.create_polygon(arrow_points, fill=combobox_text_color, outline="")


                # 4. Draw the Prompt Text
                text_x = 10  # Padding from left
                text_y = height / 2 # Vertically centered
                # Use a CTkFont if possible for consistency
                try:
                    font_details = customtkinter.ThemeManager.theme["CTkFont"]
                    overlay_font = (font_details["family"], font_details["size"])
                except:
                    overlay_font = ("sans-serif", 12) # Fallback

                self.location_overlay_canvas.create_text(text_x, text_y,
                                                         text="Select Working Directory...",
                                                         anchor="w", # West (left) anchored
                                                         fill=combobox_text_color,
                                                         font=overlay_font)
            
            # Call it once after a short delay to allow widgets to initialize their sizes
            self.after(100, draw_overlay_elements)
            # Optionally, bind to <Configure> if you expect the combobox to resize dynamically (unlikely here)
            # self.location_overlay_canvas.bind("<Configure>", draw_overlay_elements)

        else: # current_input_directory IS set
            self.location_combobox.configure(state="readonly")

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

        self.preview_player_container = customtkinter.CTkFrame(self, fg_color="transparent")
        self.preview_player_container.grid(row=10, column=0, columnspan=4, padx=20, pady=10, sticky="ew")
        self.preview_player_container.grid_columnconfigure(0, weight=1)

        PREVIEW_PLAYER_WIDTH = 320 
        PREVIEW_PLAYER_HEIGHT = 180
        self.preview_video_widget = tkinter.Frame(self.preview_player_container, bg="black",
                                                  width=PREVIEW_PLAYER_WIDTH, height=PREVIEW_PLAYER_HEIGHT)
        self.preview_video_widget.pack(pady=5, side=tkinter.TOP) # Use pack to allow icon canvas to overlay easily
        self.preview_video_widget.bind("<Button-1>", self.on_preview_area_clicked)

        self.icon_canvas = tkinter.Canvas(self.preview_player_container,
                                        width=PREVIEW_PLAYER_WIDTH,
                                        height=PREVIEW_PLAYER_HEIGHT,
                                        highlightthickness=0, bd=0)   
        
        current_bg_for_icon_canvas = None
        try:
            # Try to get the resolved background of the preview_player_container
            # CTkFrame fg_color="transparent" means it takes parent's bg.
            # We might need to go up to the main 'self' if the container is also transparent.
            
            # First, try the container's explicitly set fg_color (which acts as bg)
            container_fg_color_setting = self.preview_player_container.cget("fg_color")

            if container_fg_color_setting == "transparent":
                # If container is transparent, use the main app window's background
                main_app_bg_setting = self.cget("fg_color") # fg_color of CTk() is its background
                if isinstance(main_app_bg_setting, (list, tuple)) and len(main_app_bg_setting) == 2:
                    current_bg_for_icon_canvas = main_app_bg_setting[0] if customtkinter.get_appearance_mode().lower() == "light" else main_app_bg_setting[1]
                elif isinstance(main_app_bg_setting, str):
                    current_bg_for_icon_canvas = main_app_bg_setting
            elif isinstance(container_fg_color_setting, (list, tuple)) and len(container_fg_color_setting) == 2:
                current_bg_for_icon_canvas = container_fg_color_setting[0] if customtkinter.get_appearance_mode().lower() == "light" else container_fg_color_setting[1]
            elif isinstance(container_fg_color_setting, str):
                current_bg_for_icon_canvas = container_fg_color_setting
            
            if not current_bg_for_icon_canvas: # Fallback if still not determined
                raise ValueError("Background color could not be determined.")

        except Exception as e:
            print(f"Warning: Could not determine container bg for icon_canvas: {e}. Using fallback.")
            # Fallback to a common CustomTkinter background color
            # These are typical default background colors for CTkFrames/CTk.
            if customtkinter.get_appearance_mode().lower() == "dark":
                current_bg_for_icon_canvas = "#2B2B2B" # Common dark mode background
            else:
                current_bg_for_icon_canvas = "#DBDBDB" # Common light mode background
            # As a last resort if even main window bg fails:
            # current_bg_for_icon_canvas = "SystemButtonFace" 

        self.icon_canvas.configure(bg=current_bg_for_icon_canvas)
        print(f"Icon canvas background set to: {current_bg_for_icon_canvas}")


        self.icon_canvas.place(in_=self.preview_video_widget, relx=0, rely=0, relwidth=1, relheight=1)
        self.icon_canvas.bind("<Button-1>", self.on_preview_area_clicked)
        self.icon_canvas_item = None

        self.icon_canvas.configure(bg=current_bg_for_icon_canvas)

        self.icon_canvas.place(in_=self.preview_video_widget, relx=0, rely=0, relwidth=1, relheight=1)
        self.icon_canvas.bind("<Button-1>", self.on_preview_area_clicked)
        self.icon_canvas_item = None

        preview_controls_frame = customtkinter.CTkFrame(self.preview_player_container, fg_color="transparent")
        preview_controls_frame.pack(pady=(5,0), side=tkinter.TOP)

        self.generate_preview_button = customtkinter.CTkButton(preview_controls_frame, text="Make Preview", command=self.on_generate_preview_clicked)
        self.generate_preview_button.pack(side=tkinter.LEFT, padx=5)

        self.fixed_play_pause_button = customtkinter.CTkButton(preview_controls_frame, text="\u25B6", command=self.on_play_pause_preview_clicked, state="disabled", width=40)
        self.fixed_play_pause_button.pack(side=tkinter.LEFT, padx=5)

        self.fixed_mute_button = customtkinter.CTkButton(preview_controls_frame, text="\U0001F50A", command=self.on_mute_preview_clicked, state="disabled", width=40)
        self.fixed_mute_button.pack(side=tkinter.LEFT, padx=5)

        # Play/Pause Button (Text will change)
        self.play_pause_preview_button = customtkinter.CTkButton(preview_controls_frame, text="\u25B6 Play", # Play symbol
                                                                 command=self.on_play_pause_preview_clicked, state="disabled")
        self.play_pause_preview_button.pack(side=tkinter.LEFT, padx=5)

        # Mute/Unmute Button (Text will change)
        self.mute_preview_button = customtkinter.CTkButton(preview_controls_frame, text="\U0001F50A Mute", # Speaker symbol
                                                           command=self.on_mute_preview_clicked, state="disabled")
        self.mute_preview_button.pack(side=tkinter.LEFT, padx=5)

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
        self.button_frame.grid_columnconfigure(0, weight=1)
        self.button_frame.grid_columnconfigure(1, weight=0)
        self.button_frame.grid_columnconfigure(2, weight=0)
        self.button_frame.grid_columnconfigure(3, weight=0)
        self.button_frame.grid_columnconfigure(4, weight=1)
        self.trim_button = customtkinter.CTkButton(self.button_frame, text="Trim", command=lambda: self.start_trim_thread(delete_original=False))
        self.trim_button.grid(row=0, column=1, padx=10, pady=5)
        self.trim_delete_button = customtkinter.CTkButton(self.button_frame, text="Trim & Delete", command=lambda: self.start_trim_thread(delete_original=True), fg_color="#D32F2F", hover_color="#B71C1C")
        self.trim_delete_button.grid(row=0, column=3, padx=10, pady=5)

        # --- Initial setup ---
        self.populate_location_dropdown() # Call AFTER overlay check
        self.update_destination_dropdown()
        self._update_up_button_state() 

        if self.current_input_directory:
            self.refresh_video_list()
        else:
            self.video_combobox.set("No videos found")
            self.video_combobox.configure(state="disabled")
            self.disable_ui_components(disable=True) 
            self.update_status("Please select a video directory.", "orange")

        if not self.video_path and not self.location_overlay_canvas:
            self.disable_ui_components(disable=True)
        elif self.video_path:
            self.disable_ui_components(disable=False)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.center_window()

        if self.vlc_player:
            self.after(200, self._setup_vlc_display_output)

    def _setup_vlc_display_output(self):
        if self.vlc_player and self.preview_video_widget and self.preview_video_widget.winfo_exists():
            try:
                if platform.system() == "Windows":
                    self.vlc_player.set_hwnd(self.preview_video_widget.winfo_id())
                    print(f"VLC HWND set to: {self.preview_video_widget.winfo_id()}")
                elif platform.system() == "Linux":
                    self.vlc_player.set_xwindow(self.preview_video_widget.winfo_id())
                    print(f"VLC XWindow set to: {self.preview_video_widget.winfo_id()}")
                # macOS (set_nsobject) requires more complex handling, often via ctypes or objc bridges.
                # For now, macOS might not display video in the frame without further specific code.
                elif platform.system() == "Darwin": # macOS
                    print("macOS VLC video embedding requires additional steps (set_nsobject).")
                    # from_void_p = ctypes.c_void_p.from_void_p if hasattr(ctypes, 'c_void_p') else ctypes.void_p.from_buffer
                    # nsview = from_void_p(self.preview_video_widget.winfo_id())
                    # self.vlc_player.set_nsobject(nsview) # This line is illustrative and needs proper ctypes/objc setup
                    pass # Placeholder for macOS specific implementation
                else:
                    print(f"Unsupported platform for VLC display embedding: {platform.system()}")

            except Exception as e:
                print(f"Error setting VLC display window handle: {e}")
        elif not self.vlc_player:
            print("VLC player not initialized, cannot set display output.")
        elif not self.preview_video_widget or not self.preview_video_widget.winfo_exists():
            print("Preview video widget not available, cannot set VLC display output.")

    def on_generate_preview_clicked(self):
        if not self.vlc_player:
            self.update_status("Preview player not available (VLC error).", "orange", is_temporary=True)
            return
        self.update_status("Preview generation not yet implemented.", "orange", is_temporary=True)
        print("Generate Preview Clicked")

    def on_preview_area_clicked(self, event=None):
        """Handles clicks on the video area or the icon canvas to toggle play/pause."""
        if not self.is_preview_loaded or not self.vlc_player:
            return

        if self.vlc_player.is_playing():
            self.vlc_player.pause() 
            self.preview_playing = False 
            if self.play_icon_image_pil: 
                self.show_animated_icon(self.play_icon_image_pil)
            self.fixed_play_pause_button.configure(text="\u25B6") 
        else:
            self.vlc_player.play()
            self.preview_playing = True
            if self.pause_icon_image_pil:
                self.show_animated_icon(self.pause_icon_image_pil)
            self.fixed_play_pause_button.configure(text="\u23F8")


    def show_animated_icon(self, pil_image_to_show):
        """Starts the animation sequence for the given icon."""
        if not pil_image_to_show or \
           not self.icon_canvas or \
           not self.icon_canvas.winfo_exists() or \
           not self.play_icon_image_pil or \
           not self.pause_icon_image_pil: 
            print("Cannot show animated icon - dependencies missing.")
            return

        if self.icon_animation_job:
            self.after_cancel(self.icon_animation_job)
            self.icon_animation_job = None 

        self.current_icon_pil = pil_image_to_show 
        self.icon_alpha_anim = 0  
        self.icon_size_scale_anim = 0.6  
        self.animation_phase = "appearing" 
        self._animate_icon_step()

    def _animate_icon_step(self):
        if not self.icon_canvas or not self.icon_canvas.winfo_exists() or not self.current_icon_pil:
            if self.icon_animation_job: 
                 self.after_cancel(self.icon_animation_job)
                 self.icon_animation_job = None
            return

        if self.icon_canvas_item: 
            self.icon_canvas.delete(self.icon_canvas_item)
            self.icon_canvas_item = None

        animation_speed_ms = 30 
        max_alpha_steps = 10 
        scale_increment = 0.04
        final_scale = 1.0
        hold_time_ms = 400 

        if self.animation_phase == "appearing":
            self.icon_alpha_anim += 1
            self.icon_size_scale_anim += scale_increment
            if self.icon_alpha_anim >= max_alpha_steps and self.icon_size_scale_anim >= final_scale:
                self.icon_alpha_anim = max_alpha_steps
                self.icon_size_scale_anim = final_scale
                self.animation_phase = "visible"
                self.icon_animation_job = self.after(hold_time_ms, self._animate_icon_step)
            else:
                self.icon_animation_job = self.after(animation_speed_ms, self._animate_icon_step)
        
        elif self.animation_phase == "visible":
            self.animation_phase = "fading"
            self.icon_animation_job = self.after(animation_speed_ms, self._animate_icon_step)

        elif self.animation_phase == "fading":
            self.icon_alpha_anim -= 1
            self.icon_size_scale_anim -= (scale_increment / 2) 
            if self.icon_alpha_anim <= 0:
                self.icon_alpha_anim = 0
                if self.icon_animation_job: self.after_cancel(self.icon_animation_job); self.icon_animation_job = None
                return 
            else:
                self.icon_animation_job = self.after(animation_speed_ms, self._animate_icon_step)
        
        self.icon_alpha_anim = max(0, min(max_alpha_steps, self.icon_alpha_anim))
        self.icon_size_scale_anim = max(0.1, min(final_scale, self.icon_size_scale_anim))

        if self.icon_alpha_anim > 0 :
            base_w, base_h = self.current_icon_pil.size
            new_w = int(base_w * self.icon_size_scale_anim)
            new_h = int(base_h * self.icon_size_scale_anim)

            if new_w <= 0 or new_h <= 0: 
                if self.icon_animation_job: self.after_cancel(self.icon_animation_job); self.icon_animation_job = None
                return 

            resized_pil_img = self.current_icon_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            current_alpha_value = int((self.icon_alpha_anim / max_alpha_steps) * 255)
            final_image_pil = resized_pil_img.copy()
            
            # Ensure image has an alpha channel before trying to split or putalpha
            if final_image_pil.mode != 'RGBA':
                final_image_pil = final_image_pil.convert('RGBA')

            alpha_channel = final_image_pil.split()[-1] 
            new_alpha = alpha_channel.point(lambda i: min(i, current_alpha_value)) 
            final_image_pil.putalpha(new_alpha)

            try:
                self._temp_photo_image = ImageTk.PhotoImage(final_image_pil) 
                
                canvas_w = self.icon_canvas.winfo_width()
                canvas_h = self.icon_canvas.winfo_height()
                
                if canvas_w > 1 and canvas_h > 1: # Ensure canvas is sized
                    self.icon_canvas_item = self.icon_canvas.create_image(
                        canvas_w / 2, canvas_h / 2, 
                        image=self._temp_photo_image 
                    )
                else: # Canvas not ready, try again if job is still active
                    if self.icon_animation_job:
                         self.after_cancel(self.icon_animation_job) # Cancel current broken step
                    self.icon_animation_job = self.after(animation_speed_ms, self._animate_icon_step) # Reschedule


            except Exception as e:
                print(f"Error creating/drawing animated icon: {e}")
                if self.icon_animation_job:
                    self.after_cancel(self.icon_animation_job)
                    self.icon_animation_job = None
        elif self.icon_animation_job: 
            self.after_cancel(self.icon_animation_job)
            self.icon_animation_job = None        

    def on_play_pause_preview_clicked(self):
        if not self.vlc_player: return
        self.update_status("Play/Pause Preview not yet implemented.", "orange", is_temporary=True)
        print("Play/Pause Preview Clicked")

    def on_mute_preview_clicked(self):
        if not self.vlc_player: return
        self.update_status("Mute Preview not yet implemented.", "orange", is_temporary=True)
        print("Mute Preview Clicked")


    def disable_ui_components(self, disable=True):
        # ... (existing state_val, refresh_state, and widgets_to_toggle) ...
        state_val = "disabled" if disable else "normal"
        refresh_state = "disabled" if self.is_processing else state_val
        widgets_to_toggle = [
            self.start_slider, self.end_slider,
            self.start_scrub_left_button, self.start_scrub_right_button,
            self.end_scrub_left_button, self.end_scrub_right_button,
            self.trim_button, self.trim_delete_button,
            self.destination_combobox,
            self.rename_checkbox
            # Removed preview buttons from here, will handle based on more specific states
        ]
        if self.refresh_button: self.refresh_button.configure(state=refresh_state)

        if self.is_processing: # If processing, all these are disabled
            state_val = "disabled"
        
        for widget in widgets_to_toggle:
            if widget: widget.configure(state=state_val)

        # ... (video_combobox and location_combobox state logic as before) ...
        if self.video_combobox: # ...
            if self.is_processing: self.video_combobox.configure(state="disabled")
            elif disable:
                current_text = self.video_combobox.get()
                if not self.video_filenames or current_text == "Initializing...":
                    self.video_combobox.configure(values=[])
                    self.video_combobox.set("No videos found")
                self.video_combobox.configure(state="disabled")
            else:
                if self.video_filenames: self.video_combobox.configure(state="normal")
                else:
                    self.video_combobox.configure(values=[])
                    self.video_combobox.set("No videos found")
                    self.video_combobox.configure(state="disabled")

        can_control_preview = not self.is_processing and self.is_preview_loaded and self.vlc_player
        if self.play_pause_preview_button:
            self.play_pause_preview_button.configure(state="normal" if can_control_preview else "disabled")
        if self.mute_preview_button:
            self.mute_preview_button.configure(state="normal" if can_control_preview else "disabled")
        
        self._update_up_button_state()

        if disable and not self.is_processing: # Only reset these if disabling NOT due to processing
            if not self.video_path: # And no video is loaded
                self.display_placeholder_thumbnails()
                self.file_info_display.configure(text="Select a video")
                self.start_time_label.configure(text="Start Time: --:--:--")
                self.end_time_label.configure(text="End Time: --:--:--")
                if self.start_slider: self.start_slider.set(0)
                if self.end_slider: self.end_slider.set(1.0)
                # Also reset preview player state if UI is generally disabled
                if self.play_pause_preview_button: self.play_pause_preview_button.configure(text="\u25B6 Play") # Reset to Play
                self.preview_playing = False        

        can_generate_preview = not self.is_processing and self.video_path and self.vlc_player
        if self.generate_preview_button:
            self.generate_preview_button.configure(state="normal" if can_generate_preview else "disabled")                    
        
        if not self.location_overlay_canvas and self.location_combobox:
             self.location_combobox.configure(state="disabled" if self.is_processing else "readonly")         

    def on_closing(self):
        print("Closing application.")
        # ... (cancel existing jobs like thumb, status) ...
        if self.start_thumb_job: self.after_cancel(self.start_thumb_job)
        if self.end_thumb_job: self.after_cancel(self.end_thumb_job)
        if self.status_message_clear_job: self.after_cancel(self.status_message_clear_job)

        if self.is_processing: print("Warning: Closing during processing.")

        ### NEW: Release VLC resources ###
        if self.vlc_player:
            if self.vlc_player.is_playing():
                self.vlc_player.stop()
            self.vlc_player.release()
            print("VLC player released.")
        if self.vlc_instance:
            self.vlc_instance.release()
            print("VLC instance released.")

        cleanup_temp_files() # Includes any temp preview files if added to the list
        if self.winfo_exists(): self.destroy()
        sys.exit(0)                                    

    def _is_root_directory(self, path_to_check):
        if not path_to_check or not os.path.isdir(path_to_check):
            return True
        norm_path = os.path.normpath(path_to_check)
        parent_path = os.path.dirname(norm_path)
        return norm_path == parent_path

    def _update_up_button_state(self):
        if not hasattr(self, 'up_directory_button') or not self.up_directory_button:
            return

        if self.is_processing or \
           not self.current_input_directory or \
           self._is_root_directory(self.current_input_directory) or \
           self.location_overlay_canvas is not None:
            self.up_directory_button.configure(state="disabled")
        else:
            self.up_directory_button.configure(state="normal")

    def on_up_directory_clicked(self, event=None):
        if self.is_processing or not self.current_input_directory or self.location_overlay_canvas:
            return

        current_path = os.path.normpath(self.current_input_directory)
        parent_dir = os.path.dirname(current_path)

        if parent_dir == current_path or not os.path.isdir(parent_dir):
            self.update_status("Already at the top level or cannot go further up.", "orange", is_temporary=True)
            self._update_up_button_state()
            return

        self.current_input_directory = parent_dir
        print(f"Moved up to directory: {self.current_input_directory}")

        self.add_recent_directory(self.current_input_directory) # Saves to config
        self.populate_location_dropdown() # Updates combobox text and dropdown items
        self.update_destination_dropdown()
        self.video_path = None # Reset as directory changed
        self.refresh_video_list() # Updates video list, which in turn calls disable_ui_components

        self.update_status(f"Moved to: {os.path.basename(self.current_input_directory)}", "green", is_temporary=True)
        # _update_up_button_state is called by refresh_video_list -> disable_ui_components

    def on_location_combobox_clicked(self, event=None): # Handler for the overlay click
        print("Location overlay clicked.")
        initial_dir_for_browse = self.current_input_directory if self.current_input_directory else os.getcwd()
        new_dir = tkinter.filedialog.askdirectory(initialdir=initial_dir_for_browse, title="Select Video Directory")

        if new_dir and os.path.isdir(new_dir):
            self.current_input_directory = os.path.normpath(new_dir)

            # Destroy overlay and set its reference to None FIRST
            if self.location_overlay_canvas:
                self.location_overlay_canvas.destroy()
                self.location_overlay_canvas = None # Crucial: update the attribute
            
            # Restore normal combobox state BEFORE populating it
            self.location_combobox.configure(state="readonly")

            self.add_recent_directory(new_dir) # This saves to config

            # Now populate and update other UI
            # populate_location_dropdown will now see self.location_overlay_canvas as None
            # and self.current_input_directory as the new path.
            self.populate_location_dropdown()
            self.update_destination_dropdown()
            self.refresh_video_list() # This calls disable_ui_components -> _update_up_button_state

            self.update_status(f"Directory set to: {os.path.basename(self.current_input_directory)}", "green", is_temporary=True)
        else: # User cancelled or selected invalid directory
            if self.location_overlay_canvas: # If overlay is still active because user cancelled
                self.update_status("No directory selected. Please select a video directory.", "orange")
            self._update_up_button_state() # Ensure button state is correct even on cancel

    

    def add_recent_directory(self, new_path):
        config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
        config = {}
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load config to add recent directory: {e}")
            config = {}

        recent = config.get("recent_input_directories", [])
        new_path_norm = os.path.normpath(new_path)
        recent = [os.path.normpath(p) for p in recent if os.path.isdir(p) and os.path.normpath(p) != new_path_norm]
        recent.insert(0, new_path_norm)
        config["recent_input_directories"] = recent[:RECENT_FILES_COUNT]
        config["last_input_directory"] = new_path_norm # Also save as last directory
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
        y_coord = int((screen_height / 2) - (window_height / 2) - 30)
        self.geometry(f"{window_width}x{window_height}+{x_coord}+{y_coord}")

    def disable_ui_components(self, disable=True):
        state_val = "disabled" if disable else "normal"
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

        if self.is_processing:
            state_val = "disabled"

        for widget in widgets_to_toggle:
            if widget: widget.configure(state=state_val)

        if self.video_combobox:
            if self.is_processing: self.video_combobox.configure(state="disabled")
            elif disable:
                current_text = self.video_combobox.get()
                if not self.video_filenames or current_text == "Initializing...":
                    self.video_combobox.configure(values=[])
                    self.video_combobox.set("No videos found")
                self.video_combobox.configure(state="disabled")
            else:
                if self.video_filenames: self.video_combobox.configure(state="normal")
                else:
                    self.video_combobox.configure(values=[])
                    self.video_combobox.set("No videos found")
                    self.video_combobox.configure(state="disabled")
        
        if not self.location_overlay_canvas and self.location_combobox:
             self.location_combobox.configure(state="disabled" if self.is_processing else "readonly")
        
        self._update_up_button_state() # Manage up button state

        if disable and not self.is_processing:
            if not self.video_path:
                self.display_placeholder_thumbnails()
                self.file_info_display.configure(text="Select a video")
                self.start_time_label.configure(text="Start Time: --:--:--")
                self.end_time_label.configure(text="End Time: --:--:--")
                if self.start_slider: self.start_slider.set(0)
                if self.end_slider: self.end_slider.set(1.0)

    def refresh_video_list(self, preserve_selection=False):
        if self.location_overlay_canvas:
            print("Video list refresh deferred: Location not yet set.")
            self.video_combobox.set("No videos found")
            self.video_combobox.configure(state="disabled")
            self.disable_ui_components(True)
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
            self.video_combobox.configure(values=self.video_filenames, state="normal")
            target_selection = None; new_selection_made = False
            if previously_selected_filename and previously_selected_filename in self.video_filenames:
                target_selection = previously_selected_filename
            elif self.video_filenames:
                target_selection = self.video_filenames[0]; new_selection_made = True
            
            if target_selection:
                self.video_combobox.set(target_selection)
                if new_selection_made or not self.video_path:
                    self.after(10, lambda: self.on_video_selected(target_selection))
                else: self.disable_ui_components(disable=False)
            else:
                self.video_combobox.set("Select video")
                self.disable_ui_components(disable=True)
        else:
            self.video_path = None
            self.video_combobox.configure(values=[])
            self.video_combobox.set("No videos found")
            self.video_combobox.configure(state="disabled")
            self.disable_ui_components(disable=True)
            dir_label = os.path.basename(self.current_input_directory) if self.current_input_directory else "selected location"
            self.update_status(f"No videos found in {dir_label}", "orange", is_temporary=True)

        if not self.is_processing and self.refresh_button:
            self.refresh_button.configure(state="normal" if self.current_input_directory else "disabled")
        self._update_up_button_state() # Ensure up button reflects directory state

    def display_placeholder_thumbnails(self):
        self.current_start_thumb_ctk = self.placeholder_ctk_image
        self.current_end_thumb_ctk = self.placeholder_ctk_image
        if self.start_thumb_label and self.start_thumb_label.winfo_exists():
            self.start_thumb_label.configure(image=self.current_start_thumb_ctk)
        if self.end_thumb_label and self.end_thumb_label.winfo_exists():
            self.end_thumb_label.configure(image=self.current_end_thumb_ctk)

    def schedule_thumbnail_update(self, time_seconds, for_start_thumb):
        if not self.video_path:
            self.display_placeholder_thumbnails(); return
        job_attr = 'start_thumb_job' if for_start_thumb else 'end_thumb_job'
        existing_job = getattr(self, job_attr)
        if existing_job: self.after_cancel(existing_job)
        label_to_update = self.start_thumb_label if for_start_thumb else self.end_thumb_label
        if label_to_update and label_to_update.winfo_exists():
            label_to_update.configure(image=self.placeholder_ctk_image)
        new_job = self.after(THUMBNAIL_UPDATE_DELAY_MS, lambda t=time_seconds, fst=for_start_thumb: self.generate_and_display_thumbnail(t, fst))
        setattr(self, job_attr, new_job)

    def generate_and_display_thumbnail(self, time_seconds, for_start_thumb):
        if not self.video_path or not os.path.exists(self.video_path):
            self.display_placeholder_thumbnails(); return
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
        new_image_to_set = self.placeholder_ctk_image
        if success and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            try:
                pil_img = Image.open(thumb_path)
                ctk_img = customtkinter.CTkImage(light_image=pil_img, dark_image=pil_img,
                                                 size=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
                new_image_to_set = ctk_img
            except Exception as e:
                print(f"Error loading thumbnail image {thumb_path}: {e}")
                if os.path.exists(thumb_path) and thumb_path in temp_files_to_cleanup:
                    try: temp_files_to_cleanup.remove(thumb_path); os.remove(thumb_path)
                    except: pass
        else:
            if os.path.exists(thumb_path) and thumb_path in temp_files_to_cleanup:
                 try: temp_files_to_cleanup.remove(thumb_path); os.remove(thumb_path)
                 except: pass
        if for_start_thumb: self.current_start_thumb_ctk = new_image_to_set
        else: self.current_end_thumb_ctk = new_image_to_set
        label.configure(image=new_image_to_set)

    def on_refresh_clicked(self):
        print("Refresh button clicked.")
        if self.is_processing:
            self.update_status("Cannot refresh while processing.", "orange", is_temporary=True); return
        if self.location_overlay_canvas:
            self.update_status("Please select a video directory first.", "orange", is_temporary=True)
            if hasattr(self.location_combobox, 'focus_set'): self.location_combobox.focus_set()
            return
        self.update_status("Refreshing video list...", "blue", is_temporary=True)
        self.refresh_video_list(preserve_selection=True)

    def on_location_selected(self, selected_path_value):
        print(f"Location combobox selected: {selected_path_value}")
        if self.location_overlay_canvas: return
        if selected_path_value == INITIAL_LOCATION_PROMPT: return

        if selected_path_value == BROWSE_OPTION:
            initial_dir_for_browse = self.current_input_directory if self.current_input_directory else os.getcwd()
            new_dir = tkinter.filedialog.askdirectory(initialdir=initial_dir_for_browse, title="Select Video Directory")
            if new_dir and os.path.isdir(new_dir):
                self.current_input_directory = os.path.normpath(new_dir)
            else:
                if self.current_input_directory: self.location_combobox.set(self.current_input_directory)
                else: self.location_combobox.set(BROWSE_OPTION)
                self._update_up_button_state() # Update if browse cancelled
                return
        else:
            self.current_input_directory = os.path.normpath(selected_path_value)

        print(f"Location changed to: {self.current_input_directory}")
        self.add_recent_directory(self.current_input_directory)
        self.populate_location_dropdown()
        self.update_destination_dropdown()
        self.video_path = None
        self.refresh_video_list()

        if not self.video_filenames:
            # disable_ui_components is called by refresh_video_list
            self.update_info_display()
            self.display_placeholder_thumbnails()
            self.update_status(f"No videos found in {os.path.basename(self.current_input_directory)}.", "orange", is_temporary=True)
        else:
            self.update_status(f"Directory set to: {os.path.basename(self.current_input_directory)}", "green", is_temporary=True)
        # _update_up_button_state is called by refresh_video_list -> disable_ui_components

    def populate_location_dropdown(self):
        recent_dirs_from_config = []
        config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    loaded_recents = config.get("recent_input_directories", [])
                    recent_dirs_from_config = [os.path.normpath(p) for p in loaded_recents if os.path.isdir(p)]
            except Exception as e:
                print(f"Error loading recent dirs from config: {e}")

        dropdown_list_items = [BROWSE_OPTION]
        current_norm_path = os.path.normpath(self.current_input_directory) if self.current_input_directory and os.path.isdir(self.current_input_directory) else None

        for r_dir in recent_dirs_from_config:
            if r_dir != current_norm_path and r_dir not in dropdown_list_items:
                dropdown_list_items.append(r_dir)
        
        self.location_options = dropdown_list_items
        self.location_combobox.configure(values=self.location_options)

        # Determine what text to display in the combobox's main field
        display_text_in_combobox = BROWSE_OPTION # Default

        # THIS IS THE KEY LOGIC CHANGE:
        if current_norm_path: # If there's a valid current directory (selected via overlay or loaded from config)
            display_text_in_combobox = current_norm_path
        elif self.location_overlay_canvas is not None: # Check if overlay OBJECT still exists
            # This branch is for the VERY initial state in __init__ BEFORE any interaction
            display_text_in_combobox = INITIAL_LOCATION_PROMPT
        # If no current_input_directory and overlay is None (shouldn't normally happen after initial setup),
        # it defaults to BROWSE_OPTION (which is already the value of display_text_in_combobox).
        
        self.location_combobox.set(display_text_in_combobox)

    def update_destination_dropdown(self):
        # ... (This method seems correct from previous versions, not re-listing for brevity) ...
        # Ensure it handles self.output_directory possibly being None initially
        if not self.output_directory or not os.path.isdir(self.output_directory):
            if self.current_input_directory and os.path.isdir(self.current_input_directory):
                self.output_directory = self.current_input_directory
            else: 
                self.output_directory = os.getcwd()
        parents_of_output = get_parent_directories(self.output_directory)
        destination_paths_set = {BROWSE_OPTION} 
        if self.output_directory: destination_paths_set.add(self.output_directory)
        if self.current_input_directory: destination_paths_set.add(self.current_input_directory)
        for p in parents_of_output: destination_paths_set.add(p)
        ordered_dest_options = [BROWSE_OPTION]
        if self.output_directory and self.output_directory != BROWSE_OPTION:
            ordered_dest_options.append(self.output_directory)
        if self.current_input_directory and self.current_input_directory not in ordered_dest_options:
             ordered_dest_options.append(self.current_input_directory)
        for p in parents_of_output:
            if p not in ordered_dest_options: ordered_dest_options.append(p)
        for p in destination_paths_set:
            if p not in ordered_dest_options: ordered_dest_options.append(p)
        self.destination_options = ordered_dest_options
        self.destination_combobox.configure(values=self.destination_options)
        if self.output_directory in self.destination_options:
            self.destination_combobox.set(self.output_directory)
        elif self.destination_options:
            self.destination_combobox.set(self.destination_options[0])
        else: self.destination_combobox.set("")


    def on_destination_selected(self, selected_path):
        # ... (This method seems correct, not re-listing) ...
        if selected_path == BROWSE_OPTION:
            initial_dir_for_browse = self.output_directory if self.output_directory else os.getcwd()
            new_dir = tkinter.filedialog.askdirectory(initialdir=initial_dir_for_browse, title="Select Output Directory")
            if new_dir and os.path.isdir(new_dir):
                self.output_directory = os.path.normpath(new_dir)
        else:
            self.output_directory = os.path.normpath(selected_path)
        print(f"Output directory set to: {self.output_directory}")
        self.update_destination_dropdown()


    def on_video_selected(self, selected_filename):
        # ... (This method seems correct, not re-listing) ...
        if self.is_processing: return
        if not selected_filename or selected_filename in ["No videos found", "Initializing...", INITIAL_LOCATION_PROMPT]:
            self.video_path = None; self.disable_ui_components(True)
            self.update_info_display(); self.display_placeholder_thumbnails()
            return
        if not self.current_input_directory:
            self.update_status("Error: Input directory not set.", "red", is_temporary=True)
            self.video_path = None; self.refresh_video_list()
            return
        self.video_path = os.path.join(self.current_input_directory, selected_filename)
        if not os.path.exists(self.video_path):
            self.update_status(f"Error: {selected_filename} not found.", "red", is_temporary=True)
            self.video_path = None; self.refresh_video_list(preserve_selection=False)
            return
        print(f"Video selected: {self.video_path}")
        self.load_video_data()


    def load_video_data(self):
        # ... (This method seems correct, not re-listing) ...
        if not self.video_path:
            self.disable_ui_components(True); self.update_info_display(); self.display_placeholder_thumbnails()
            return
        self.update_status(f"Loading {os.path.basename(self.video_path)}...", "blue", is_temporary=True)
        duration_s, ctime_str, size_str, size_bytes = get_video_metadata(self.video_path)
        if duration_s is None:
            self.update_status(f"Error loading metadata for {os.path.basename(self.video_path)}.", "red", is_temporary=True)
            self.video_path = None; self.refresh_video_list(preserve_selection=False)
            if not self.video_path:
                self.disable_ui_components(True); self.update_info_display(); self.display_placeholder_thumbnails()
            return
        self.duration = duration_s; self.original_size_bytes = size_bytes
        self.current_filename = os.path.basename(self.video_path); self.current_creation_time = ctime_str
        self.current_size_str = size_str; self.current_duration_str = format_time(self.duration)
        self.start_time = 0.0; self.end_time = self.duration if self.duration > 0 else 1.0
        slider_max = self.duration if self.duration > 0 else 1.0
        self.start_slider.configure(to=slider_max); self.end_slider.configure(to=slider_max)
        self.start_slider.set(self.start_time); self.end_slider.set(self.end_time)
        self.update_start_time(self.start_time); self.update_end_time(self.end_time)
        self.update_info_display(); self.disable_ui_components(False)
        self.update_status(f"Loaded: {self.current_filename}", "green", is_temporary=True)
        self.rename_checkbox.deselect(); self.pending_custom_filename = None


    def update_info_display(self):
        # ... (This method seems correct, not re-listing) ...
        if not self.video_path :
            self.file_info_display.configure(text="Select a video to see details.")
            return
        info_text = (f"File: {self.current_filename}\nDuration: {self.current_duration_str}\n"
                     f"Created: {self.current_creation_time}\nSize: {self.current_size_str}")
        self.file_info_display.configure(text=info_text)


    def update_start_time(self, value_str_or_float):
        # ... (This method seems correct, not re-listing) ...
        try: value = float(value_str_or_float)
        except ValueError: return
        if self.is_processing: return
        if value >= self.end_time - 0.01: value = max(0, self.end_time - 0.05)
        value = max(0, value)
        self.start_time = value
        self.start_time_label.configure(text=f"Start Time: {format_time(self.start_time)}")
        self.schedule_thumbnail_update(self.start_time, for_start_thumb=True)


    def update_end_time(self, value_str_or_float):
        # ... (This method seems correct, not re-listing) ...
        try: value = float(value_str_or_float)
        except ValueError: return
        if self.is_processing: return
        if value <= self.start_time + 0.01: value = min(self.duration, self.start_time + 0.05)
        value = min(self.duration, value)
        self.end_time = value
        self.end_time_label.configure(text=f"End Time: {format_time(self.end_time)}")
        self.schedule_thumbnail_update(self.end_time, for_start_thumb=False)


    def scrub_start_left(self):
        if not self.video_path or self.is_processing: return
        new_time = max(0, self.start_time - SCRUB_INCREMENT)
        self.start_slider.set(new_time)
    def scrub_start_right(self):
        if not self.video_path or self.is_processing: return
        new_time = min(self.end_time - 0.05, self.start_time + SCRUB_INCREMENT)
        new_time = max(0, new_time)
        self.start_slider.set(new_time)
    def scrub_end_left(self):
        if not self.video_path or self.is_processing: return
        new_time = max(self.start_time + 0.05, self.end_time - SCRUB_INCREMENT)
        new_time = min(self.duration, new_time)
        self.end_slider.set(new_time)
    def scrub_end_right(self):
        if not self.video_path or self.is_processing:return
        new_time = min(self.duration, self.end_time + SCRUB_INCREMENT)
        self.end_slider.set(new_time)

    def start_trim_thread(self, delete_original=False):
        # ... (This method seems mostly correct from previous versions, not re-listing for brevity) ...
        # Ensure self.pending_custom_filename is reset at the start
        self.pending_custom_filename = None
        if self.is_processing: print("Already processing."); return
        if not self.video_path: self.update_status("No video selected.", "red", is_temporary=True); return
        if not self.output_directory or not os.path.isdir(self.output_directory):
            self.update_status("Invalid output directory. Please select.", "red", is_temporary=True)
            self.on_destination_selected(BROWSE_OPTION)
            if not self.output_directory or not os.path.isdir(self.output_directory):
                 self.update_status("Output directory still not set. Trim cancelled.", "red", is_temporary=True); return
            self.update_status("Output directory selected. Try trimming again.", "orange", is_temporary=True); return
        if abs(self.end_time - self.start_time) < 0.1:
            self.update_status("Error: Trim duration too short (min 0.1s).", "red", is_temporary=True); return
        if self.rename_checkbox.get() == 1:
            dialog = CustomFilenameDialog(self, title="Set Output Filename")
            custom_basename = dialog.get_input()
            if custom_basename is None:
                self.rename_checkbox.deselect(); self.update_status("Rename cancelled.", "orange", is_temporary=True)
            elif not custom_basename.strip():
                self.rename_checkbox.deselect(); self.update_status("Empty name. Using default.", "orange", is_temporary=True)
            else: self.pending_custom_filename = custom_basename.strip() + ".mp4"
        if delete_original:
            confirm_msg = f"Permanently delete the original file?\n\n{os.path.basename(self.video_path)}\n\nThis cannot be undone."
            if self.pending_custom_filename: confirm_msg += f"\n\nThe trimmed clip: {self.pending_custom_filename}"
            if not tkinter.messagebox.askyesno("Confirm Delete", confirm_msg, icon='warning', parent=self):
                self.update_status("Trim & Delete cancelled.", "orange", is_temporary=True); self.pending_custom_filename = None; return
        self.is_processing = True; self.disable_ui_components(disable=True)
        self.update_status("Starting trim...", "blue", is_persistent_trim_status=False)
        temp_output_path_for_delete_op = None
        if delete_original:
            try:
                base_temp, ext_temp = os.path.splitext(os.path.basename(self.video_path))
                temp_output_path_for_delete_op = os.path.join(self.output_directory, f"{base_temp}_temp_trim_{uuid.uuid4().hex}{ext_temp}")
            except Exception as e:
                print(f"Error generating temp filename for delete op: {e}")
                self.update_status("Error preparing temp file.", "red", is_persistent_trim_status=True)
                self.reset_ui_after_processing(); return
        thread = threading.Thread(target=self.run_ffmpeg_trim, args=(delete_original, temp_output_path_for_delete_op, self.pending_custom_filename), daemon=True)
        thread.start()


    def run_ffmpeg_trim(self, delete_original, temp_path_for_delete_op, custom_final_name_mp4):
        # ... (This method seems mostly correct, careful review done, not re-listing full for brevity) ...
        global temp_files_to_cleanup
        final_output_path_actual = None; ffmpeg_output_target = None
        original_input_path = self.video_path
        try:
            if not original_input_path or not os.path.exists(original_input_path): raise ValueError("Original video path invalid.")
            input_basename_no_ext, input_ext = os.path.splitext(os.path.basename(original_input_path))
            if delete_original:
                ffmpeg_output_target = temp_path_for_delete_op
                if not ffmpeg_output_target: raise ValueError("Temp output path missing for delete.")
                if ffmpeg_output_target not in temp_files_to_cleanup: temp_files_to_cleanup.append(ffmpeg_output_target)
                final_output_path_actual = os.path.join(self.output_directory, custom_final_name_mp4 if custom_final_name_mp4 else os.path.basename(original_input_path))
            else:
                target_ext = ".mp4" if custom_final_name_mp4 else input_ext
                file_base = os.path.splitext(custom_final_name_mp4)[0] if custom_final_name_mp4 else f"{input_basename_no_ext}{TRIM_SUFFIX}"
                actual_output_name = f"{file_base}{target_ext}" if custom_final_name_mp4 else f"{file_base}{target_ext}" # Ensure ext
                final_output_path_actual = os.path.join(self.output_directory, actual_output_name)
                counter = 1
                while os.path.exists(final_output_path_actual):
                    final_output_path_actual = os.path.join(self.output_directory, f"{file_base}_{counter}{target_ext}"); counter += 1
                ffmpeg_output_target = final_output_path_actual
            if final_output_path_actual is None: final_output_path_actual = ffmpeg_output_target
            start_str = format_time(self.start_time); trim_duration = max(0.1, self.end_time - self.start_time)
            command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', start_str, '-i', original_input_path,
                       '-t', str(trim_duration), '-c', 'copy', '-map', '0', '-avoid_negative_ts', 'make_zero',
                       '-y', ffmpeg_output_target]
            self.after(0, lambda: self.update_status("Processing with FFmpeg...", "blue", is_persistent_trim_status=False))
            print(f"FFmpeg: {' '.join(command)}")
            startupinfo = None
            if platform.system() == 'Windows': startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=startupinfo)
            stdout, stderr = process.communicate()
            if process.returncode == 0 and os.path.exists(ffmpeg_output_target) and os.path.getsize(ffmpeg_output_target) > 0:
                success_msg_base = f"Done! Trimmed: {os.path.basename(final_output_path_actual)}\n(in {os.path.basename(self.output_directory)})"
                if delete_original:
                    self.after(0, lambda: self.update_status("Finalizing...", "blue", is_persistent_trim_status=False)); time.sleep(0.1)
                    renamed_temp_ok = False
                    if os.path.abspath(ffmpeg_output_target) != os.path.abspath(final_output_path_actual):
                        if os.path.exists(final_output_path_actual):
                            try: os.remove(final_output_path_actual)
                            except OSError as e: print(f"Could not del existing final: {e}") # Continue, try rename
                        try: os.rename(ffmpeg_output_target, final_output_path_actual); renamed_temp_ok = True
                        except OSError as rename_err:
                            print(f"Rename error: {rename_err}"); final_output_path_actual = ffmpeg_output_target
                            success_msg_base = f"Trimmed to temp: {os.path.basename(final_output_path_actual)}\nOriginal NOT deleted (rename err)."
                            self.after(0, lambda: self.update_status(success_msg_base, "orange", True)); self.after(100, lambda p=final_output_path_actual: self.post_trim_success(p)); return
                    else: renamed_temp_ok = True # No rename needed
                    if renamed_temp_ok and ffmpeg_output_target in temp_files_to_cleanup: temp_files_to_cleanup.remove(ffmpeg_output_target)
                    if renamed_temp_ok:
            # Corrected logic:
                        if renamed_temp_ok:
                            try:
                                os.remove(original_input_path)
                                print(f"Deleted original: {original_input_path}") # Moved inside try
                                self.after(0, lambda: self.update_status(f"{success_msg_base}\nOriginal deleted.", "green", True))
                                self.after(100, lambda p=final_output_path_actual, d=original_input_path: self.post_trim_success(p, d))
                            except OSError as os_err: # This now correctly catches only errors from os.remove
                                self.after(0, lambda: self.update_status(f"Trimmed to {os.path.basename(final_output_path_actual)} BUT FAILED to delete original: {os_err}", "orange", True))
                                self.after(100, lambda p=final_output_path_actual: self.post_trim_success(p)) # Pass None for deleted_original_path
                            else: self.after(0, lambda: self.update_status(success_msg_base, "green", True)); self.after(100, lambda p=final_output_path_actual: self.post_trim_success(p))
            else:
                err_detail = stderr if stderr else stdout; err_msg = f"FFmpeg failed (code {process.returncode}):\n{err_detail[-500:] if err_detail else 'No output'}"
                if process.returncode == 0 and not (os.path.exists(ffmpeg_output_target) and os.path.getsize(ffmpeg_output_target) > 0): err_msg = "FFmpeg OK, but output missing/empty."
                print(err_msg); self.after(0, lambda: self.update_status(err_msg, "red", True))
                if ffmpeg_output_target and os.path.exists(ffmpeg_output_target):
                    try: os.remove(ffmpeg_output_target)
                    except OSError as e: print(f"Error cleaning failed output: {e}")
                    if ffmpeg_output_target in temp_files_to_cleanup: temp_files_to_cleanup.remove(ffmpeg_output_target)
                self.after(100, self.reset_ui_after_processing)
        except Exception as e:
            import traceback; detailed_error = traceback.format_exc()
            print(f"Trim error: {type(e).__name__}: {e}\n{detailed_error}")
            self.after(0, lambda: self.update_status(f"Unexpected trim error: {e}", "red", True))
            if ffmpeg_output_target and os.path.exists(ffmpeg_output_target) and ffmpeg_output_target in temp_files_to_cleanup:
                try: os.remove(ffmpeg_output_target); temp_files_to_cleanup.remove(ffmpeg_output_target)
                except Exception as clean_e: print(f"Error cleaning temp output: {clean_e}")
            self.after(100, self.reset_ui_after_processing)
        finally: self.pending_custom_filename = None


    def post_trim_success(self, output_filepath, deleted_original_path=None):
        # ... (This method seems correct, calls refresh_video_list -> disable_ui_components) ...
        print(f"Trim process ended. Final file: {output_filepath if output_filepath else 'None'}")
        self.is_processing = False
        should_preserve = True
        if deleted_original_path and self.video_path == deleted_original_path:
            self.video_path = None; should_preserve = False
        self.refresh_video_list(preserve_selection=should_preserve)
        if not self.video_path: self.disable_ui_components(True)
        else: self.disable_ui_components(False)


    def reset_ui_after_processing(self):
        # ... (This method seems correct, calls refresh_video_list -> disable_ui_components) ...
        self.is_processing = False; self.pending_custom_filename = None
        self.refresh_video_list(preserve_selection=True)
        if not self.video_path and not self.location_overlay_canvas:
            self.disable_ui_components(True)


    def update_status(self, message, color="gray", is_persistent_trim_status=False, is_temporary=False):
        # ... (This method seems correct, not re-listing) ...
        if self.status_message_clear_job: self.after_cancel(self.status_message_clear_job); self.status_message_clear_job = None
        def _update():
            if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                 self.status_label.configure(text=message, text_color=color)
        if is_persistent_trim_status:
            self.last_trim_status_message = message; self.last_trim_status_color = color
            self.temporary_status_active = False; self.after(0, _update)
        elif is_temporary:
            self.temporary_status_active = True; self.after(0, _update)
            self.status_message_clear_job = self.after(STATUS_MESSAGE_CLEAR_DELAY_MS, self._revert_to_persistent_status)
        else:
            if not self.last_trim_status_message or color == "red": self.last_trim_status_message = ""
            self.temporary_status_active = False; self.after(0, _update)


    def _revert_to_persistent_status(self):
        # ... (This method seems correct, not re-listing) ...
        self.temporary_status_active = False
        current_text = self.last_trim_status_message if self.last_trim_status_message else ""
        current_color = self.last_trim_status_color if self.last_trim_status_message else "gray"
        if not self.current_input_directory and self.location_overlay_canvas: # Overlay active
            current_text = "Please select a video directory."; current_color = "orange"
        def _update():
            if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                self.status_label.configure(text=current_text, text_color=current_color)
        self.after(0, _update); self.status_message_clear_job = None


    def show_error_and_quit(self, message):
        # ... (This method seems correct, not re-listing) ...
        print(f"FATAL ERROR: {message}"); temp_root_created = False; parent = self
        if not (hasattr(self, 'title') and self.winfo_exists()):
            try: root = tkinter.Tk(); root.withdraw(); parent = root; temp_root_created = True
            except tkinter.TclError: print("TclError: No Tk for error."); cleanup_temp_files(); sys.exit(1)
        if parent and hasattr(parent, 'winfo_exists') and parent.winfo_exists():
            tkinter.messagebox.showerror("Critical Error", message, parent=parent)
        if temp_root_created and hasattr(parent, 'destroy'): parent.destroy()
        elif hasattr(self, 'destroy') and self.winfo_exists(): self.destroy()
        cleanup_temp_files(); sys.exit(1)

    def on_closing(self):
        # ... (This method seems correct, not re-listing) ...
        print("Closing application.")
        if self.start_thumb_job: self.after_cancel(self.start_thumb_job)
        if self.end_thumb_job: self.after_cancel(self.end_thumb_job)
        if self.status_message_clear_job: self.after_cancel(self.status_message_clear_job)
        if self.is_processing: print("Warning: Closing during processing.")
        cleanup_temp_files()
        if self.winfo_exists(): self.destroy()
        sys.exit(0)


# --- Script Entry Point ---
if __name__ == "__main__":
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
        error_msg = f"ERROR: FFmpeg or ffprobe not found/executable.\nPlease ensure they are installed and in PATH.\nDetails: {e}"
        print(error_msg); root_err = tkinter.Tk(); root_err.withdraw()
        tkinter.messagebox.showerror("Startup Error", error_msg, parent=root_err)
        root_err.destroy(); sys.exit(1)
    except Exception as e:
        error_msg = f"Unexpected error checking FFmpeg/ffprobe: {e}"
        print(error_msg); root_err = tkinter.Tk(); root_err.withdraw()
        tkinter.messagebox.showerror("Startup Error", error_msg, parent=root_err)
        root_err.destroy(); sys.exit(1)

    customtkinter.set_appearance_mode("System")
    customtkinter.set_default_color_theme("blue")
    customtkinter.set_widget_scaling(1.1)
    customtkinter.set_window_scaling(1.1)

    initial_dir_for_app = load_last_directory()
    app_instance = None
    try:
        app_instance = VideoTrimmerApp(initial_input_dir=initial_dir_for_app)
        if app_instance and app_instance.winfo_exists():
            app_instance.mainloop()
        else:
            print("App window failed to init or closed prematurely."); cleanup_temp_files(); sys.exit(1)
    except Exception as e:
        print(f"Unhandled exception during app init or mainloop: {e}")
        import traceback; traceback.print_exc()
        error_message_to_show = f"App critical error:\n\n{type(e).__name__}: {e}"
        if app_instance and hasattr(app_instance, 'show_error_and_quit') and app_instance.winfo_exists():
            app_instance.show_error_and_quit(error_message_to_show)
        else:
            root_crash_err = tkinter.Tk(); root_crash_err.withdraw()
            tkinter.messagebox.showerror("Application Critical Error", error_message_to_show, parent=root_crash_err)
            if root_crash_err.winfo_exists(): root_crash_err.destroy()
        cleanup_temp_files(); sys.exit(1)
    finally:
        print("Application exited.")