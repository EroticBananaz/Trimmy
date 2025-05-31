import tkinter
import customtkinter
from . import config_settings

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
        if any(char in config_settings.FILENAME_INVALID_CHARS for char in current_text):
            self.ok_button.configure(state="disabled")
            self.error_label.configure(text=f"Invalid chars (e.g., {config_settings.FILENAME_INVALID_CHARS[0]})")
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