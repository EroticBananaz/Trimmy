import tkinter
import tkinter.filedialog
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

VIDEO_DIRECTORY = 'C:/obs/test'
# Supported video file extensions
VIDEO_EXTENSIONS = ('*.mp4', '*.mov', '*.avi', '*.mkv', '*.wmv', '*.flv')
# --- End Configuration ---

# --- Helper Functions ---

def format_time(seconds):
    """Converts seconds to HH:MM:SS.ms format."""
    if seconds is None or seconds < 0:
        return "00:00:00.000"
    delta = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds_part = divmod(remainder, 60)
    milliseconds = int(delta.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{seconds_part:02}.{milliseconds:03}"

def get_video_metadata(file_path):
    """Gets video duration and other info using ffprobe."""
    if not file_path or not os.path.exists(file_path):
        print(f"Error: File not found - {file_path}")
        return None, None, None

    # Check if ffprobe exists
    try:
        subprocess.run(['ffprobe', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: ffprobe not found. Make sure FFmpeg (which includes ffprobe) is installed and in your system's PATH.")
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
        process = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0)
        metadata = json.loads(process.stdout)

        duration = None
        creation_time_str = None

        # Get duration from format information
        if 'format' in metadata and 'duration' in metadata['format']:
            duration = float(metadata['format']['duration'])

        # Get creation time from format tags (might not always be present)
        if 'format' in metadata and 'tags' in metadata['format'] and 'creation_time' in metadata['format']['tags']:
             creation_time_str = metadata['format']['tags']['creation_time']
        # Fallback: Get file system modification time if creation_time tag is missing
        else:
            try:
                mtime = os.path.getmtime(file_path)
                creation_time_str = datetime.datetime.fromtimestamp(mtime).isoformat() + 'Z' # Approximate using mtime
            except Exception:
                 creation_time_str = "N/A" # Could not get any time


        # Get file size
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


def find_most_recent_video(directory):
    """Finds the most recently modified video file in the specified directory."""
    if not os.path.isdir(directory):
        print(f"Error: Directory not found - {directory}")
        return None

    all_videos = []
    for ext in VIDEO_EXTENSIONS:
        all_videos.extend(glob.glob(os.path.join(directory, ext)))

    if not all_videos:
        print(f"No video files found in {directory}")
        return None

    try:
        # Find the file with the latest modification time
        latest_file = max(all_videos, key=os.path.getmtime)
        return latest_file
    except Exception as e:
        print(f"Error finding latest file: {e}")
        return None

def open_file_explorer(path):
    """Opens the file explorer to the specified path."""
    try:
        if platform.system() == "Windows":
            # Use os.startfile on Windows for better behavior
            os.startfile(os.path.normpath(path))
        elif platform.system() == "Darwin": # macOS
            subprocess.run(['open', path], check=True)
        else: # Linux and other Unix-like
            subprocess.run(['xdg-open', path], check=True)
    except FileNotFoundError:
         print(f"Error: Could not open file explorer. Command not found (is '{'explorer' if platform.system() == 'Windows' else 'open' if platform.system() == 'Darwin' else 'xdg-open'}' in PATH?).")
    except subprocess.CalledProcessError as e:
         print(f"Error opening file explorer: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while opening the file explorer: {e}")


# --- Main Application Class ---

class VideoTrimmerApp(customtkinter.CTk):
    def __init__(self, video_path):
        super().__init__()

        if not video_path:
            self.show_error_and_quit("No video file found or specified.")
            return

        self.video_path = video_path
        self.duration = None
        self.start_time = 0.0
        self.end_time = 0.0
        self.is_processing = False # Flag to prevent multiple trim actions

        # --- Get Video Info ---
        self.duration, creation_time, file_size = get_video_metadata(self.video_path)

        if self.duration is None:
             self.show_error_and_quit(f"Could not get metadata for:\n{os.path.basename(self.video_path)}\n\nCheck console for details.\nIs FFmpeg/ffprobe installed and in PATH?")
             return

        self.end_time = self.duration # Initialize end time to full duration

        # --- Configure Window ---
        self.title("Video Trimmer")
        self.geometry("600x450") # Increased height for better spacing
        self.resizable(False, False)
        # Center the window
        self.update_idletasks() # Ensure window dimensions are calculated
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        size = tuple(int(_) for _ in self.geometry().split('+')[0].split('x'))
        x = screen_width/2 - size[0]/2
        y = screen_height/2 - size[1]/2
        self.geometry("+%d+%d" % (x, y))


        # --- Create UI Elements ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1) # Allow status label row to expand if needed

        # File Info Label
        self.info_label = customtkinter.CTkLabel(self, text="File Information:", font=customtkinter.CTkFont(weight="bold"))
        self.info_label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")

        file_info_text = (
            f"File: {os.path.basename(self.video_path)}\n"
            f"Duration: {format_time(self.duration)}\n"
            f"Created: {creation_time if creation_time else 'N/A'}\n"
            f"Size: {file_size if file_size else 'N/A'}"
        )
        self.file_info_display = customtkinter.CTkLabel(self, text=file_info_text, justify=tkinter.LEFT, anchor="w")
        self.file_info_display.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")

        # Start Time Slider & Label
        self.start_time_label = customtkinter.CTkLabel(self, text=f"Start Time: {format_time(self.start_time)}")
        self.start_time_label.grid(row=2, column=0, padx=20, pady=(10, 0), sticky="w")

        self.start_slider = customtkinter.CTkSlider(self, from_=0, to=self.duration, command=self.update_start_time)
        self.start_slider.set(0)
        self.start_slider.grid(row=3, column=0, padx=20, pady=(5, 10), sticky="ew")

        # End Time Slider & Label
        self.end_time_label = customtkinter.CTkLabel(self, text=f"End Time: {format_time(self.end_time)}")
        self.end_time_label.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="w")

        self.end_slider = customtkinter.CTkSlider(self, from_=0, to=self.duration, command=self.update_end_time)
        self.end_slider.set(self.duration)
        self.end_slider.grid(row=5, column=0, padx=20, pady=(5, 20), sticky="ew")

        # Status Label
        self.status_label = customtkinter.CTkLabel(self, text="", text_color="gray")
        self.status_label.grid(row=6, column=0, padx=20, pady=5, sticky="ew")


        # Trim Button
        self.trim_button = customtkinter.CTkButton(self, text="Trim Video", command=self.start_trim_thread)
        self.trim_button.grid(row=7, column=0, padx=20, pady=(10, 20))

        # --- Protocol Handler ---
        self.protocol("WM_DELETE_WINDOW", self.on_closing) # Handle window close


    def update_start_time(self, value):
        """Callback when the start slider is moved."""
        self.start_time = float(value)
        # Ensure start time is not after end time
        if self.start_time > self.end_time:
            self.start_time = self.end_time
            self.start_slider.set(self.start_time) # Update slider position visually

        self.start_time_label.configure(text=f"Start Time: {format_time(self.start_time)}")

    def update_end_time(self, value):
        """Callback when the end slider is moved."""
        self.end_time = float(value)
        # Ensure end time is not before start time
        if self.end_time < self.start_time:
            self.end_time = self.start_time
            self.end_slider.set(self.end_time) # Update slider position visually

        self.end_time_label.configure(text=f"End Time: {format_time(self.end_time)}")

    def start_trim_thread(self):
        """Starts the trimming process in a separate thread to avoid freezing the UI."""
        if self.is_processing:
            print("Already processing.")
            return

        if abs(self.end_time - self.start_time) < 0.1: # Prevent zero-length trims
             self.update_status("Error: Start and End times are too close.", "red")
             return

        self.is_processing = True
        self.trim_button.configure(state="disabled", text="Processing...")
        self.start_slider.configure(state="disabled")
        self.end_slider.configure(state="disabled")
        self.update_status("Starting trim...", "blue")

        # Run ffmpeg in a separate thread
        thread = threading.Thread(target=self.run_ffmpeg_trim)
        thread.daemon = True # Allows closing the main app even if thread is running (though we wait)
        thread.start()

    def run_ffmpeg_trim(self):
        """Executes the ffmpeg command."""
        try:
            # Check if ffmpeg exists
            subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0)

            input_filename = self.video_path
            output_dir = os.path.dirname(input_filename)
            base, ext = os.path.splitext(os.path.basename(input_filename))
            output_filename = os.path.join(output_dir, f"{base}_trimmed{ext}")

            # Ensure output filename is unique
            counter = 1
            while os.path.exists(output_filename):
                 output_filename = os.path.join(output_dir, f"{base}_trimmed_{counter}{ext}")
                 counter += 1


            # Format times for ffmpeg (HH:MM:SS.ms)
            start_str = format_time(self.start_time)
            # Calculate duration for -t, more reliable than -to with -c copy sometimes
            trim_duration = self.end_time - self.start_time

            # FFmpeg command using -ss for start and -t for duration with stream copy
            # Using -t (duration) instead of -to (end time) is often more reliable with -c copy
            command = [
                'ffmpeg',
                '-i', input_filename,      # Input file
                '-ss', start_str,          # Start time
                '-t', str(trim_duration),  # Duration to trim
                '-c', 'copy',              # Copy streams (fast, less accurate)
                # '-avoid_negative_ts', 'make_zero', # Helps with potential timestamp issues
                '-map', '0',               # Map all streams (audio, video, subtitles)
                '-y',                      # Overwrite output without asking (we handle uniqueness)
                output_filename
            ]

            # For higher accuracy (but much slower re-encoding), remove '-c copy'
            # command = [
            #     'ffmpeg',
            #     '-i', input_filename,
            #     '-ss', start_str,
            #     '-to', format_time(self.end_time), # Use -to if re-encoding
            #     '-map', '0',
            #     '-y',
            #     output_filename
            # ]

            self.update_status("Processing with FFmpeg...", "blue")
            print(f"Running FFmpeg command: {' '.join(command)}") # Log command

            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0)

            # You could potentially read stdout/stderr here for progress if ffmpeg provides it
            stdout, stderr = process.communicate() # Wait for completion

            if process.returncode == 0:
                self.update_status("Trim successful!", "green")
                print("FFmpeg finished successfully.")
                # Schedule actions for the main thread
                self.after(100, lambda: self.post_trim_success(output_dir)) # Short delay before opening explorer/closing
            else:
                error_message = f"FFmpeg error (code {process.returncode}):\n{stderr[-500:]}" # Show last 500 chars of error
                self.update_status(error_message, "red")
                print(error_message)
                # Re-enable UI on failure
                self.after(100, self.reset_ui_after_processing)


        except FileNotFoundError:
             error_message = "Error: ffmpeg not found. Is it installed and in PATH?"
             self.update_status(error_message, "red")
             print(error_message)
             self.after(100, self.reset_ui_after_processing)
        except subprocess.CalledProcessError as e:
             error_message = f"Error checking ffmpeg version: {e}"
             self.update_status(error_message, "red")
             print(error_message)
             self.after(100, self.reset_ui_after_processing)
        except Exception as e:
            error_message = f"An unexpected error occurred during trimming: {e}"
            self.update_status(error_message, "red")
            print(error_message)
            self.after(100, self.reset_ui_after_processing)


    def post_trim_success(self, output_dir):
        """Actions to perform after successful trim (run in main thread)."""
        # 1. Show "Done!" popup (optional, status label might be enough)
        # tkinter.messagebox.showinfo("Success", "Video trimmed successfully!") # Can be annoying

        # 2. Open file explorer
        open_file_explorer(output_dir)

        # 3. Auto-exit
        self.update_status("Done! Closing...", "green")
        # Add a small delay before closing so the user sees the "Done!" message
        self.after(1500, self.on_closing) # Wait 1.5 seconds then close


    def reset_ui_after_processing(self):
        """Resets UI elements after processing (usually on failure)."""
        self.is_processing = False
        self.trim_button.configure(state="normal", text="Trim Video")
        self.start_slider.configure(state="normal")
        self.end_slider.configure(state="normal")


    def update_status(self, message, color="gray"):
        """Updates the status label text and color."""
        # Ensure this runs in the main thread
        def _update():
            self.status_label.configure(text=message, text_color=color)
        self.after(0, _update) # Schedule the update in the main event loop

    def show_error_and_quit(self, message):
        """Displays an error message box and quits the application."""
        # Ensure Tkinter root is initialized if called early
        if not hasattr(self, 'title'):
            root = tkinter.Tk()
            root.withdraw() # Hide the main window
            tkinter.messagebox.showerror("Error", message)
            root.destroy()
        else:
            tkinter.messagebox.showerror("Error", message)
            self.destroy()
        sys.exit(f"Error: {message}") # Exit script


    def on_closing(self):
        """Handles the window closing event."""
        print("Closing application.")
        self.destroy()
        sys.exit() # Ensure script terminates cleanly

# --- Script Entry Point ---
if __name__ == "__main__":
    customtkinter.set_appearance_mode("System") # Modes: "System" (default), "Dark", "Light"
    customtkinter.set_default_color_theme("blue") # Themes: "blue" (default), "green", "dark-blue"

    # --- Validate Configuration ---
    if VIDEO_DIRECTORY == 'path/to/your/video/clips':
         root = tkinter.Tk()
         root.withdraw() # Hide the main window
         tkinter.messagebox.showerror("Configuration Needed", "Please edit the script and set the 'VIDEO_DIRECTORY' variable to your actual video clips folder.")
         root.destroy()
         sys.exit("Configuration Error: VIDEO_DIRECTORY not set.")

    if not os.path.isdir(VIDEO_DIRECTORY):
         root = tkinter.Tk()
         root.withdraw() # Hide the main window
         tkinter.messagebox.showerror("Error", f"The specified VIDEO_DIRECTORY does not exist:\n{VIDEO_DIRECTORY}")
         root.destroy()
         sys.exit(f"Directory not found: {VIDEO_DIRECTORY}")


    # --- Find Video and Launch App ---
    latest_video = find_most_recent_video(VIDEO_DIRECTORY)

    if latest_video:
        print(f"Found latest video: {latest_video}")
        app = VideoTrimmerApp(latest_video)
        if app.winfo_exists(): # Check if window was created successfully
             app.mainloop()
        else:
             print("Application failed to initialize.")
             # Error message should have been shown by show_error_and_quit
    else:
        # Handle case where no video is found after directory validation
        root = tkinter.Tk()
        root.withdraw() # Hide the main window
        tkinter.messagebox.showinfo("No Videos", f"No video files ({', '.join(VIDEO_EXTENSIONS)}) found in the directory:\n{VIDEO_DIRECTORY}")
        root.destroy()
        sys.exit(f"No videos found in {VIDEO_DIRECTORY}")
