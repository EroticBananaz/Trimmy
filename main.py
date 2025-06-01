import sys
import tkinter
import subprocess
import platform
import customtkinter
from utils import load_last_directory
from app import VideoTrimmerApp
from ffmpeg_utils import cleanup_temp_files

if __name__ == "__main__":
    try:
        si_check = None
        if platform.system() == 'Windows': si_check = subprocess.STARTUPINFO(); si_check.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si_check.wShowWindow = subprocess.SW_HIDE
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si_check)
        subprocess.run(['ffprobe', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si_check)
        print("FFmpeg and ffprobe found.")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        err_msg = f"ERROR: FFmpeg/ffprobe not found/executable.\nEnsure installed and in PATH.\nDetails: {e}"
        print(err_msg); r_err = tkinter.Tk(); r_err.withdraw(); tkinter.messagebox.showerror("Startup Error", err_msg, parent=r_err); r_err.destroy(); sys.exit(1)
    except Exception as e:
        err_msg = f"Unexpected error checking FFmpeg/ffprobe: {e}"
        print(err_msg); r_err = tkinter.Tk(); r_err.withdraw(); tkinter.messagebox.showerror("Startup Error", err_msg, parent=r_err); r_err.destroy(); sys.exit(1)

    customtkinter.set_appearance_mode("System"); customtkinter.set_default_color_theme("blue")
    customtkinter.set_widget_scaling(1.0); customtkinter.set_window_scaling(1.0)

    init_dir_app = load_last_directory()
    app = None
    try:
        app = VideoTrimmerApp(initial_input_dir=init_dir_app)
        if app and app.winfo_exists(): app.mainloop()
        else: print("App window failed/closed prematurely."); cleanup_temp_files(); sys.exit(1)
    except Exception as e:
        print(f"Unhandled exception in app init/mainloop: {e}"); import traceback; traceback.print_exc()
        err_to_show = f"App critical error:\n\n{type(e).__name__}: {e}"
        if app and hasattr(app, 'show_error_and_quit') and app.winfo_exists(): app.show_error_and_quit(err_to_show)
        else:
            rc_err = tkinter.Tk(); rc_err.withdraw(); tkinter.messagebox.showerror("Application Critical Error", err_to_show, parent=rc_err)
            if rc_err.winfo_exists(): rc_err.destroy()
        cleanup_temp_files(); sys.exit(1)
    finally:
        print("Application exited.")