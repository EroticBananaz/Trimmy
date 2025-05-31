from . import config_settings
from . import utils
from .ui_dialogs import CustomFilenameDialog


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

        self.title("Trimmy")
        self.geometry("700x900")
        self.resizable(False, False)

        self.placeholder_pil_image = Image.new('RGB', (config_settings.THUMBNAIL_WIDTH, config_settings.THUMBNAIL_HEIGHT), color='gray')
        self.placeholder_ctk_image = customtkinter.CTkImage(light_image=self.placeholder_pil_image,
                                                             dark_image=self.placeholder_pil_image,
                                                             size=(config_settings.THUMBNAIL_WIDTH, config_settings.THUMBNAIL_HEIGHT))
        self.current_start_thumb_ctk = self.placeholder_ctk_image
        self.current_end_thumb_ctk = self.placeholder_ctk_image

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_columnconfigure(3, weight=0)

        self.location_label = customtkinter.CTkLabel(self, text="Location:")
        self.location_label.grid(row=0, column=0, columnspan=4, padx=20, pady=(20, 5), sticky="w")
        self.location_combobox = customtkinter.CTkComboBox(self, values=[], command=self.on_location_selected)
        self.location_combobox.grid(row=1, column=0, columnspan=3, padx=(20,5), pady=(0, 15), sticky="ew")

        self.up_directory_button = customtkinter.CTkButton(self, text=u"\u25B2", width=40,
                                                           command=self.on_up_directory_clicked)
        self.up_directory_button.grid(row=1, column=3, padx=(0, 20), pady=(0,15), sticky="e")
        
        self.location_overlay_canvas = None
        if not self.current_input_directory:
            self.location_combobox.configure(state="disabled")
            try:
                combobox_bg_color = self._apply_appearance_mode(customtkinter.ThemeManager.theme["CTkComboBox"]["fg_color"])
                combobox_border_color = self._apply_appearance_mode(customtkinter.ThemeManager.theme["CTkComboBox"]["border_color"])
                combobox_text_color = self._apply_appearance_mode(customtkinter.ThemeManager.theme["CTkLabel"]["text_color"])
                combobox_button_color = self._apply_appearance_mode(customtkinter.ThemeManager.theme["CTkComboBox"]["button_color"])
            except KeyError: 
                combobox_bg_color = "gray16" if customtkinter.get_appearance_mode().lower() == "dark" else "gray86"
                combobox_border_color = "gray40" if customtkinter.get_appearance_mode().lower() == "dark" else "gray60"
                combobox_text_color = "white" if customtkinter.get_appearance_mode().lower() == "dark" else "black"
                combobox_button_color = "gray25" if customtkinter.get_appearance_mode().lower() == "dark" else "gray75"

            self.location_overlay_canvas = tkinter.Canvas(self,
                                                        background=combobox_bg_color,
                                                        highlightthickness=customtkinter.ThemeManager.theme["CTkComboBox"]["border_width"],
                                                        highlightbackground=combobox_border_color,
                                                        bd=0,
                                                        insertbackground=combobox_text_color)
            self.location_overlay_canvas.place(in_=self.location_combobox, relx=0, rely=0, relwidth=1, relheight=1)
            self.location_overlay_canvas.bind("<Button-1>", self.on_location_combobox_clicked)

            def draw_overlay_elements(event=None):
                if not self.location_overlay_canvas or not self.location_overlay_canvas.winfo_exists(): return
                self.location_overlay_canvas.delete("all")
                width = self.location_overlay_canvas.winfo_width(); height = self.location_overlay_canvas.winfo_height()
                if width <=1 or height <=1: self.after(50, draw_overlay_elements); return
                arrow_box_width = height - 4; arrow_box_x1 = width - arrow_box_width - 2
                arrow_box_y1 = 2; arrow_box_x2 = width - 2; arrow_box_y2 = height - 2
                self.location_overlay_canvas.create_rectangle(arrow_box_x1, arrow_box_y1, arrow_box_x2, arrow_box_y2, fill=combobox_button_color, outline=combobox_border_color, width=0)
                arrow_size = 6; arrow_center_x = arrow_box_x1 + (arrow_box_width / 2); arrow_center_y = arrow_box_y1 + (height / 2) -2
                arrow_points = [arrow_center_x - arrow_size, arrow_center_y - arrow_size / 2, arrow_center_x + arrow_size, arrow_center_y - arrow_size / 2, arrow_center_x, arrow_center_y + arrow_size / 2]
                self.location_overlay_canvas.create_polygon(arrow_points, fill=combobox_text_color, outline="")
                text_x = 10; text_y = height / 2
                try: font_details = customtkinter.ThemeManager.theme["CTkFont"]; overlay_font = (font_details["family"], font_details["size"])
                except: overlay_font = ("sans-serif", 12)
                self.location_overlay_canvas.create_text(text_x, text_y, text=config_settings.INITIAL_LOCATION_PROMPT, anchor="w", fill=combobox_text_color, font=overlay_font)
            self.after(100, draw_overlay_elements)
        else:
            self.location_combobox.configure(state="readonly")

        self.video_select_label = customtkinter.CTkLabel(self, text="Select Video:")
        self.video_select_label.grid(row=2, column=0, columnspan=2, padx=20, pady=(5, 5), sticky="w")
        self.video_combobox = customtkinter.CTkComboBox(self, values=["Initializing..."], command=self.on_video_selected)
        self.video_combobox.set("Initializing...")
        self.video_combobox.grid(row=3, column=0, columnspan=3, padx=(20,5), pady=(0, 15), sticky="ew")
        self.refresh_button = customtkinter.CTkButton(self, text="Refresh", width=80, command=self.on_refresh_clicked)
        self.refresh_button.grid(row=3, column=3, padx=(0, 20), pady=(0,15), sticky="e")

        self.info_frame = customtkinter.CTkFrame(self)
        self.info_frame.grid(row=4, column=0, columnspan=4, padx=20, pady=(0, 15), sticky="ew")
        self.info_frame.grid_columnconfigure(0, weight=1)
        self.file_info_display = customtkinter.CTkLabel(self.info_frame, text="Select a video", justify=tkinter.LEFT, anchor="nw")
        self.file_info_display.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        self.start_time_label = customtkinter.CTkLabel(self, text=f"Start Time: {utils.format_time(self.start_time)}")
        self.start_time_label.grid(row=5, column=0, columnspan=4, padx=20, pady=(10, 0), sticky="w")
        self.start_scrub_left_button = customtkinter.CTkButton(self, text="<", width=40, command=self.scrub_start_left)
        self.start_scrub_left_button.grid(row=6, column=0, padx=(20, 5), pady=(5, 10), sticky="w")
        self.start_slider = customtkinter.CTkSlider(self, from_=0, to=1.0, command=self.update_start_time)
        self.start_slider.grid(row=6, column=1, columnspan=2, padx=5, pady=(5, 10), sticky="ew")
        self.start_scrub_right_button = customtkinter.CTkButton(self, text=">", width=40, command=self.scrub_start_right)
        self.start_scrub_right_button.grid(row=6, column=3, padx=(5, 20), pady=(5, 10), sticky="e")
        self.end_time_label = customtkinter.CTkLabel(self, text=f"End Time: {utils.format_time(self.end_time)}")
        self.end_time_label.grid(row=7, column=0, columnspan=4, padx=20, pady=(10, 0), sticky="w")
        self.end_scrub_left_button = customtkinter.CTkButton(self, text="<", width=40, command=self.scrub_end_left)
        self.end_scrub_left_button.grid(row=8, column=0, padx=(20, 5), pady=(5, 20), sticky="w")
        self.end_slider = customtkinter.CTkSlider(self, from_=0, to=1.0, command=self.update_end_time)
        self.end_slider.grid(row=8, column=1, columnspan=2, padx=5, pady=(5, 20), sticky="ew")
        self.end_scrub_right_button = customtkinter.CTkButton(self, text=">", width=40, command=self.scrub_end_right)
        self.end_scrub_right_button.grid(row=8, column=3, padx=(5, 20), pady=(5, 20), sticky="e")
        self.start_slider.set(0); self.end_slider.set(1.0)

        self.thumb_frame = customtkinter.CTkFrame(self)
        self.thumb_frame.grid(row=9, column=0, columnspan=4, padx=20, pady=10, sticky="ew")
        self.thumb_frame.grid_columnconfigure(0, weight=1); self.thumb_frame.grid_columnconfigure(1, weight=1)
        self.start_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="Start Frame"); self.start_thumb_label_text.grid(row=0, column=0, pady=(5,2))
        self.start_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=self.current_start_thumb_ctk); self.start_thumb_label.grid(row=1, column=0, padx=10, pady=(0,10))
        self.end_thumb_label_text = customtkinter.CTkLabel(self.thumb_frame, text="End Frame"); self.end_thumb_label_text.grid(row=0, column=1, pady=(5,2))
        self.end_thumb_label = customtkinter.CTkLabel(self.thumb_frame, text="", image=self.current_end_thumb_ctk); self.end_thumb_label.grid(row=1, column=1, padx=10, pady=(0,10))

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
        self.button_frame.grid_columnconfigure(0, weight=1); self.button_frame.grid_columnconfigure(1, weight=0)
        self.button_frame.grid_columnconfigure(2, weight=0); self.button_frame.grid_columnconfigure(3, weight=0)
        self.button_frame.grid_columnconfigure(4, weight=1)
        self.trim_button = customtkinter.CTkButton(self.button_frame, text="Trim", command=lambda: self.start_trim_thread(delete_original=False))
        self.trim_button.grid(row=0, column=1, padx=10, pady=5)
        self.trim_delete_button = customtkinter.CTkButton(self.button_frame, text="Trim & Delete", command=lambda: self.start_trim_thread(delete_original=True), fg_color="#D32F2F", hover_color="#B71C1C")
        self.trim_delete_button.grid(row=0, column=3, padx=10, pady=5)

        self.populate_location_dropdown()
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

    def _is_root_directory(self, path_to_check):
        if not path_to_check or not os.path.isdir(path_to_check): return True
        norm_path = os.path.normpath(path_to_check)
        parent_path = os.path.dirname(norm_path)
        return norm_path == parent_path

    def _update_up_button_state(self):
        if not hasattr(self, 'up_directory_button') or not self.up_directory_button: return
        if self.is_processing or not self.current_input_directory or self._is_root_directory(self.current_input_directory) or self.location_overlay_canvas is not None:
            self.up_directory_button.configure(state="disabled")
        else:
            self.up_directory_button.configure(state="normal")

    def on_up_directory_clicked(self, event=None):
        if self.is_processing or not self.current_input_directory or self.location_overlay_canvas: return
        current_path = os.path.normpath(self.current_input_directory); parent_dir = os.path.dirname(current_path)
        if parent_dir == current_path or not os.path.isdir(parent_dir):
            self.update_status("Already at the top level.", "orange", is_temporary=True); self._update_up_button_state(); return
        self.current_input_directory = parent_dir; print(f"Moved up to: {self.current_input_directory}")
        self.add_recent_directory(self.current_input_directory); self.populate_location_dropdown()
        self.update_destination_dropdown(); self.video_path = None; self.refresh_video_list()
        self.update_status(f"Moved to: {os.path.basename(self.current_input_directory)}", "green", is_temporary=True)

    def on_location_combobox_clicked(self, event=None):
        initial_dir_for_browse = self.current_input_directory if self.current_input_directory else os.getcwd()
        new_dir = tkinter.filedialog.askdirectory(initialdir=initial_dir_for_browse, title="Select Video Directory")
        if new_dir and os.path.isdir(new_dir):
            self.current_input_directory = os.path.normpath(new_dir)
            if self.location_overlay_canvas: self.location_overlay_canvas.destroy(); self.location_overlay_canvas = None
            self.location_combobox.configure(state="readonly")
            self.add_recent_directory(new_dir); self.populate_location_dropdown()
            self.update_destination_dropdown(); self.refresh_video_list()
            self.update_status(f"Directory set to: {os.path.basename(self.current_input_directory)}", "green", is_temporary=True)
        else:
            if self.location_overlay_canvas: self.update_status("No directory selected.", "orange")
            self._update_up_button_state()

    def add_recent_directory(self, new_path):
        config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), config_settings.CONFIG_FILENAME)
        config = {}; 
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f: config = json.load(f)
        except (json.JSONDecodeError, IOError) as e: print(f"Warning: Could not load config: {e}")
        recent = config.get("recent_input_directories", []); new_path_norm = os.path.normpath(new_path)
        recent = [os.path.normpath(p) for p in recent if os.path.isdir(p) and os.path.normpath(p) != new_path_norm]
        recent.insert(0, new_path_norm); config["recent_input_directories"] = recent[:
        config_settings.RECENT_FILES_COUNT]
        config["last_input_directory"] = new_path_norm
        try:
            with open(config_path, 'w') as f: json.dump(config, f, indent=4)
            print(f"Updated config with last/recent directory: {new_path_norm}")
        except Exception as e: print(f"Failed to update config file: {e}")

    def center_window(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        ww, wh = self.winfo_width(), self.winfo_height()
        x, y = int((sw / 2) - (ww / 2)), int((sh / 2) - (wh / 2) - 30)
        self.geometry(f"{ww}x{wh}+{x}+{y}")

    def disable_ui_components(self, disable=True):
        state = "disabled" if disable else "normal"; refresh_s = "disabled" if self.is_processing else state
        widgets = [self.start_slider, self.end_slider, self.start_scrub_left_button, self.start_scrub_right_button,
                   self.end_scrub_left_button, self.end_scrub_right_button, self.trim_button, self.trim_delete_button,
                   self.destination_combobox, self.rename_checkbox]
        if self.refresh_button: self.refresh_button.configure(state=refresh_s)
        if self.is_processing: state = "disabled"
        for widget in widgets:
            if widget: widget.configure(state=state)
        if self.video_combobox:
            if self.is_processing: self.video_combobox.configure(state="disabled")
            elif disable:
                current_text = self.video_combobox.get()
                if not self.video_filenames or current_text == "Initializing...": self.video_combobox.configure(values=[]); self.video_combobox.set("No videos found")
                self.video_combobox.configure(state="disabled")
            else:
                if self.video_filenames: self.video_combobox.configure(state="normal")
                else: self.video_combobox.configure(values=[]); self.video_combobox.set("No videos found"); self.video_combobox.configure(state="disabled")
        if not self.location_overlay_canvas and self.location_combobox: self.location_combobox.configure(state="disabled" if self.is_processing else "readonly")
        self._update_up_button_state()
        if disable and not self.is_processing and not self.video_path:
            self.display_placeholder_thumbnails(); self.file_info_display.configure(text="Select a video")
            self.start_time_label.configure(text="Start Time: --:--:--"); self.end_time_label.configure(text="End Time: --:--:--")
            if self.start_slider: self.start_slider.set(0)
            if self.end_slider: self.end_slider.set(1.0)

    def refresh_video_list(self, preserve_selection=False):
        if self.location_overlay_canvas:
            self.video_combobox.set("No videos found"); self.video_combobox.configure(state="disabled"); self.disable_ui_components(True); return
        if not self.current_input_directory:
            self.video_combobox.set("No videos found"); self.video_combobox.configure(state="disabled"); self.disable_ui_components(True)
            self.update_status("Cannot refresh: No directory selected.", "orange", is_temporary=True); return
        prev_selection = os.path.basename(self.video_path) if preserve_selection and self.video_path else None
        self.recent_videos = find_recent_videos(self.current_input_directory, config_settings.RECENT_FILES_COUNT)
        self.video_filenames = [os.path.basename(p) for p in self.recent_videos]
        if self.video_filenames:
            self.video_combobox.configure(values=self.video_filenames, state="normal")
            target_sel = None; new_sel_made = False
            if prev_selection and prev_selection in self.video_filenames: target_sel = prev_selection
            elif self.video_filenames: target_sel = self.video_filenames[0]; new_sel_made = True
            if target_sel:
                self.video_combobox.set(target_sel)
                if new_sel_made or not self.video_path: self.after(10, lambda: self.on_video_selected(target_sel))
                else: self.disable_ui_components(disable=False)
            else: self.video_combobox.set("Select video"); self.disable_ui_components(disable=True)
        else:
            self.video_path = None; self.video_combobox.configure(values=[]); self.video_combobox.set("No videos found")
            self.video_combobox.configure(state="disabled"); self.disable_ui_components(disable=True)
            dir_label = os.path.basename(self.current_input_directory) if self.current_input_directory else "selected location"
            self.update_status(f"No videos found in {dir_label}", "orange", is_temporary=True)
        if not self.is_processing and self.refresh_button: self.refresh_button.configure(state="normal" if self.current_input_directory else "disabled")
        self._update_up_button_state()

    def display_placeholder_thumbnails(self):
        self.current_start_thumb_ctk = self.placeholder_ctk_image; self.current_end_thumb_ctk = self.placeholder_ctk_image
        if self.start_thumb_label and self.start_thumb_label.winfo_exists(): self.start_thumb_label.configure(image=self.current_start_thumb_ctk)
        if self.end_thumb_label and self.end_thumb_label.winfo_exists(): self.end_thumb_label.configure(image=self.current_end_thumb_ctk)

    def schedule_thumbnail_update(self, time_seconds, for_start_thumb):
        if not self.video_path: self.display_placeholder_thumbnails(); return
        job_attr = 'start_thumb_job' if for_start_thumb else 'end_thumb_job'
        if getattr(self, job_attr): self.after_cancel(getattr(self, job_attr))
        label = self.start_thumb_label if for_start_thumb else self.end_thumb_label
        if label and label.winfo_exists(): label.configure(image=self.placeholder_ctk_image)
        new_job = self.after(config_settings.THUMBNAIL_UPDATE_DELAY_MS, lambda t=time_seconds, fst=for_start_thumb: self.generate_and_display_thumbnail(t, fst))
        setattr(self, job_attr, new_job)

    def generate_and_display_thumbnail(self, time_seconds, for_start_thumb):
        if not self.video_path or not os.path.exists(self.video_path): self.display_placeholder_thumbnails(); return
        temp_dir = tempfile.gettempdir(); thumb_file = f"trimmy_thumb_{uuid.uuid4().hex}.jpg"; thumb_path = os.path.join(temp_dir, thumb_file)
        threading.Thread(target=self._run_thumbnail_extraction, args=(self.video_path, time_seconds, thumb_path, for_start_thumb), daemon=True).start()

    def _run_thumbnail_extraction(self, video_path, time_seconds, thumb_path, for_start_thumb):
        success = utils.extract_thumbnail(video_path, time_seconds, thumb_path)
        self.after(0, self._update_thumbnail_label, thumb_path, for_start_thumb, success)

    def _update_thumbnail_label(self, thumb_path, for_start_thumb, success):
        label = self.start_thumb_label if for_start_thumb else self.end_thumb_label
        if not (label and label.winfo_exists()): return
        new_img = self.placeholder_ctk_image
        if success and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            try:
                pil = Image.open(thumb_path); ctk_img = customtkinter.CTkImage(light_image=pil, dark_image=pil, size=(config_settings.THUMBNAIL_WIDTH, config_settings.THUMBNAIL_HEIGHT)); new_img = ctk_img
            except Exception as e: print(f"Error loading thumbnail: {e}")
            if os.path.exists(thumb_path) and thumb_path in temp_files_to_cleanup:
                try: temp_files_to_cleanup.remove(thumb_path); os.remove(thumb_path)
                except: pass
        else:
            if os.path.exists(thumb_path) and thumb_path in temp_files_to_cleanup:
                try: temp_files_to_cleanup.remove(thumb_path); os.remove(thumb_path)
                except: pass
        if for_start_thumb: self.current_start_thumb_ctk = new_img
        else: self.current_end_thumb_ctk = new_img
        label.configure(image=new_img)

    def on_refresh_clicked(self):
        if self.is_processing: self.update_status("Cannot refresh during processing.", "orange", True); return
        if self.location_overlay_canvas: self.update_status("Select directory first.", "orange", True); return
        self.update_status("Refreshing video list...", "blue", True); self.refresh_video_list(True)

    def on_location_selected(self, selected_path):
        if self.location_overlay_canvas: return
        if selected_path == config_settings.INITIAL_LOCATION_PROMPT: return
        if selected_path == config_settings.BROWSE_OPTION:
            new_dir = tkinter.filedialog.askdirectory(initialdir=self.current_input_directory or os.getcwd(), title="Select Video Directory")
            if new_dir and os.path.isdir(new_dir): self.current_input_directory = os.path.normpath(new_dir)
            else:
                if self.current_input_directory: self.location_combobox.set(self.current_input_directory)
                else: self.location_combobox.set(BROWSE_OPTION)
                self._update_up_button_state(); return
        else: self.current_input_directory = os.path.normpath(selected_path)
        self.add_recent_directory(self.current_input_directory); self.populate_location_dropdown()
        self.update_destination_dropdown(); self.video_path = None; self.refresh_video_list()
        if not self.video_filenames:
            self.update_info_display(); self.display_placeholder_thumbnails()
            self.update_status(f"No videos in {os.path.basename(self.current_input_directory)}.", "orange", True)
        else: self.update_status(f"Directory: {os.path.basename(self.current_input_directory)}", "green", True)

    def populate_location_dropdown(self):
        recent_dirs = []; config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), config_settings.CONFIG_FILENAME)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f: config = json.load(f)
                loaded_recents = config.get("recent_input_directories", [])
                recent_dirs = [os.path.normpath(p) for p in loaded_recents if os.path.isdir(p)]
            except Exception as e: print(f"Error loading recents: {e}")
        dropdown_items = [config_settings.BROWSE_OPTION]; current_norm = os.path.normpath(self.current_input_directory) if self.current_input_directory and os.path.isdir(self.current_input_directory) else None
        for r_dir in recent_dirs:
            if r_dir != current_norm and r_dir not in dropdown_items: dropdown_items.append(r_dir)
        self.location_options = dropdown_items; self.location_combobox.configure(values=self.location_options)
        display_text = config_settings.BROWSE_OPTION
        if current_norm: display_text = current_norm
        elif self.location_overlay_canvas is not None: display_text = config_settings.INITIAL_LOCATION_PROMPT
        self.location_combobox.set(display_text)

    def update_destination_dropdown(self):
        if not self.output_directory or not os.path.isdir(self.output_directory):
            self.output_directory = self.current_input_directory if self.current_input_directory and os.path.isdir(self.current_input_directory) else os.getcwd()
        parents = utils.get_parent_directories(self.output_directory); dest_set = {config_settings.BROWSE_OPTION}
        if self.output_directory: dest_set.add(self.output_directory)
        if self.current_input_directory: dest_set.add(self.current_input_directory)
        for p in parents: dest_set.add(p)
        ordered_opts = [config_settings.BROWSE_OPTION]
        if self.output_directory and self.output_directory != config_settings.BROWSE_OPTION: ordered_opts.append(self.output_directory)
        if self.current_input_directory and self.current_input_directory not in ordered_opts: ordered_opts.append(self.current_input_directory)
        for p in parents:
            if p not in ordered_opts: ordered_opts.append(p)
        for p in dest_set:
            if p not in ordered_opts: ordered_opts.append(p)
        self.destination_options = ordered_opts; self.destination_combobox.configure(values=self.destination_options)
        if self.output_directory in self.destination_options: self.destination_combobox.set(self.output_directory)
        elif self.destination_options: self.destination_combobox.set(self.destination_options[0])
        else: self.destination_combobox.set("")

    def on_destination_selected(self, selected_path):
        if selected_path == config_settings.BROWSE_OPTION:
            new_dir = tkinter.filedialog.askdirectory(initialdir=self.output_directory or os.getcwd(), title="Select Output Directory")
            if new_dir and os.path.isdir(new_dir): self.output_directory = os.path.normpath(new_dir)
        else: self.output_directory = os.path.normpath(selected_path)
        self.update_destination_dropdown()

    def on_video_selected(self, selected_filename):
        if self.is_processing: return
        if not selected_filename or selected_filename in ["No videos found", "Initializing...", config_settings.INITIAL_LOCATION_PROMPT]:
            self.video_path = None; self.disable_ui_components(True); self.update_info_display(); self.display_placeholder_thumbnails(); return
        if not self.current_input_directory:
            self.update_status("Error: Input directory not set.", "red", True); self.video_path = None; self.refresh_video_list(); return
        self.video_path = os.path.join(self.current_input_directory, selected_filename)
        if not os.path.exists(self.video_path):
            self.update_status(f"Error: {selected_filename} not found.", "red", True); self.video_path = None; self.refresh_video_list(False); return
        self.load_video_data()

    def load_video_data(self):
        if not self.video_path: self.disable_ui_components(True); self.update_info_display(); self.display_placeholder_thumbnails(); return
        self.update_status(f"Loading {os.path.basename(self.video_path)}...", "blue", True)
        duration_s, ctime, size_s, size_b = utils.get_video_metadata(self.video_path)
        if duration_s is None:
            self.update_status(f"Error loading metadata for {os.path.basename(self.video_path)}.", "red", True); self.video_path = None; self.refresh_video_list(False)
            if not self.video_path: self.disable_ui_components(True); self.update_info_display(); self.display_placeholder_thumbnails()
            return
        self.duration = duration_s; self.original_size_bytes = size_b; self.current_filename = os.path.basename(self.video_path)
        self.current_creation_time = ctime; self.current_size_str = size_s; self.current_duration_str = utils.format_time(self.duration)
        self.start_time = 0.0; self.end_time = self.duration if self.duration > 0 else 1.0
        slider_max = self.duration if self.duration > 0 else 1.0
        self.start_slider.configure(to=slider_max); self.end_slider.configure(to=slider_max)
        self.start_slider.set(self.start_time); self.end_slider.set(self.end_time)
        self.update_start_time(self.start_time); self.update_end_time(self.end_time)
        self.update_info_display(); self.disable_ui_components(False)
        self.update_status(f"Loaded: {self.current_filename}", "green", True); self.rename_checkbox.deselect(); self.pending_custom_filename = None

    def update_info_display(self):
        if not self.video_path : self.file_info_display.configure(text="Select a video to see details."); return
        info = (f"File: {self.current_filename}\nDuration: {self.current_duration_str}\n"
                f"Created: {self.current_creation_time}\nSize: {self.current_size_str}")
        self.file_info_display.configure(text=info)

    def update_start_time(self, val_str_float):
        try: val = float(val_str_float)
        except ValueError: return
        if self.is_processing: return
        if val >= self.end_time - 0.01: val = max(0, self.end_time - 0.05)
        self.start_time = max(0, val); self.start_time_label.configure(text=f"Start Time: {utils.format_time(self.start_time)}")
        self.schedule_thumbnail_update(self.start_time, True)

    def update_end_time(self, val_str_float):
        try: val = float(val_str_float)
        except ValueError: return
        if self.is_processing: return
        if val <= self.start_time + 0.01: val = min(self.duration, self.start_time + 0.05)
        self.end_time = min(self.duration, val); self.end_time_label.configure(text=f"End Time: {utils.format_time(self.end_time)}")
        self.schedule_thumbnail_update(self.end_time, False)

    def scrub_start_left(self):
        if not self.video_path or self.is_processing: return
        new_time = max(0, self.start_time - config_settings.SCRUB_INCREMENT)
        self.start_slider.set(new_time)
        self.update_start_time(new_time) 

    def scrub_start_right(self):
        if not self.video_path or self.is_processing: return
        new_time = min(self.end_time - 0.05, self.start_time + config_settings.SCRUB_INCREMENT)
        new_time = max(0, new_time) 
        self.start_slider.set(new_time)
        self.update_start_time(new_time)

    def scrub_end_left(self):
        if not self.video_path or self.is_processing: return
        new_time = max(self.start_time + 0.05, self.end_time - config_settings.SCRUB_INCREMENT)
        new_time = min(self.duration, new_time)
        self.end_slider.set(new_time)
        self.update_end_time(new_time)

    def scrub_end_right(self):
        if not self.video_path or self.is_processing:return
        new_time = min(self.duration, self.end_time + config_settings.SCRUB_INCREMENT)
        self.end_slider.set(new_time)
        self.update_end_time(new_time)

    def start_trim_thread(self, delete_original=False):
        self.pending_custom_filename = None
        if self.is_processing: return
        if not self.video_path: self.update_status("No video selected.", "red", True); return
        if not self.output_directory or not os.path.isdir(self.output_directory):
            self.update_status("Invalid output directory.", "red", True); self.on_destination_selected(config_settings.BROWSE_OPTION)
            if not self.output_directory or not os.path.isdir(self.output_directory): self.update_status("Output dir still not set.", "red", True); return
            self.update_status("Output dir selected. Try again.", "orange", True); return
        if abs(self.end_time - self.start_time) < 0.1: self.update_status("Trim duration too short.", "red", True); return
        if self.rename_checkbox.get() == 1:
            dialog = ui_dialogs.CustomFilenameDialog(self, title="Set Output Filename"); custom_base = dialog.get_input()
            if custom_base is None: self.rename_checkbox.deselect(); self.update_status("Rename cancelled.", "orange", True)
            elif not custom_base.strip(): self.rename_checkbox.deselect(); self.update_status("Empty name. Defaulting.", "orange", True)
            else: self.pending_custom_filename = custom_base.strip() + ".mp4"
        if delete_original:
            msg = f"Permanently delete original?\n\n{os.path.basename(self.video_path)}\n\nThis cannot be undone."
            if self.pending_custom_filename: msg += f"\n\nTrimmed clip: {self.pending_custom_filename}"
            if not tkinter.messagebox.askyesno("Confirm Delete", msg, icon='warning', parent=self):
                self.update_status("Trim & Delete cancelled.", "orange", True); self.pending_custom_filename = None; return
        self.is_processing = True; self.disable_ui_components(True); self.update_status("Starting trim...", "blue", False)
        temp_out_del = None
        if delete_original:
            try: base, ext = os.path.splitext(os.path.basename(self.video_path)); temp_out_del = os.path.join(self.output_directory, f"{base}_temp_trim_{uuid.uuid4().hex}{ext}")
            except Exception as e: print(f"Error gen temp name: {e}"); self.update_status("Error prepping temp file.", "red", True); self.reset_ui_after_processing(); return
        threading.Thread(target=self.run_ffmpeg_trim, args=(delete_original, temp_out_del, self.pending_custom_filename), daemon=True).start()

    def run_ffmpeg_trim(self, delete_original, temp_path_for_delete_op, custom_final_name_mp4):
        global temp_files_to_cleanup; final_out_actual = None; ffmpeg_target = None; original_in = self.video_path
        try:
            if not original_in or not os.path.exists(original_in): raise ValueError("Original video path invalid.")
            in_base, in_ext = os.path.splitext(os.path.basename(original_in))
            if delete_original:
                ffmpeg_target = temp_path_for_delete_op;
                if not ffmpeg_target: raise ValueError("Temp output path missing for delete.")
                if ffmpeg_target not in temp_files_to_cleanup: temp_files_to_cleanup.append(ffmpeg_target)
                final_out_actual = os.path.join(self.output_directory, custom_final_name_mp4 if custom_final_name_mp4 else os.path.basename(original_in))
            else:
                target_ext = ".mp4" if custom_final_name_mp4 else in_ext
                file_base = os.path.splitext(custom_final_name_mp4)[0] if custom_final_name_mp4 else f"{in_base}{config_settings.TRIM_SUFFIX}"
                out_name = f"{file_base}{target_ext}" if custom_final_name_mp4 else f"{file_base}{target_ext}"
                final_out_actual = os.path.join(self.output_directory, out_name); counter = 1
                while os.path.exists(final_out_actual): final_out_actual = os.path.join(self.output_directory, f"{file_base}_{counter}{target_ext}"); counter += 1
                ffmpeg_target = final_out_actual
            if final_out_actual is None: final_out_actual = ffmpeg_target
            start_s = utils.format_time(self.start_time); trim_dur = max(0.1, self.end_time - self.start_time)
            cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', start_s, '-i', original_in, '-t', str(trim_dur), '-c', 'copy', '-map', '0', '-avoid_negative_ts', 'make_zero', '-y', ffmpeg_target]
            self.after(0, lambda: self.update_status("Processing...", "blue", False)); print(f"FFmpeg: {' '.join(cmd)}")
            si = None; 
            if platform.system() == 'Windows': si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW; si.wShowWindow = subprocess.SW_HIDE
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', startupinfo=si)
            _, stderr = proc.communicate()
            if proc.returncode == 0 and os.path.exists(ffmpeg_target) and os.path.getsize(ffmpeg_target) > 0:
                msg_base = f"Done! Trimmed: {os.path.basename(final_out_actual)}\n(in {os.path.basename(self.output_directory)})"
                if delete_original:
                    self.after(0, lambda: self.update_status("Finalizing...", "blue", False)); time.sleep(0.1)
                    renamed_ok = False
                    if os.path.abspath(ffmpeg_target) != os.path.abspath(final_out_actual):
                        if os.path.exists(final_out_actual):
                            try: os.remove(final_out_actual)
                            except OSError as e: print(f"Could not del existing: {e}")
                        try: os.rename(ffmpeg_target, final_out_actual); renamed_ok = True
                        except OSError as re: print(f"Rename error: {re}"); final_out_actual = ffmpeg_target; msg_base = f"Trimmed to temp: {os.path.basename(final_out_actual)}\nOriginal NOT deleted."; self.after(0, lambda: self.update_status(msg_base, "orange", True)); self.after(100, lambda p=final_out_actual: self.post_trim_success(p)); return
                    else: renamed_ok = True
                    if renamed_ok and ffmpeg_target in temp_files_to_cleanup: temp_files_to_cleanup.remove(ffmpeg_target)
                    if renamed_ok:
                        try: os.remove(original_in); print(f"Deleted original: {original_in}"); self.after(0, lambda: self.update_status(f"{msg_base}\nOriginal deleted.", "green", True)); self.after(100, lambda p=final_out_actual, d=original_in: self.post_trim_success(p, d))
                        except OSError as oe: self.after(0, lambda: self.update_status(f"Trimmed to {os.path.basename(final_out_actual)} BUT FAILED to delete original: {oe}", "orange", True)); self.after(100, lambda p=final_out_actual: self.post_trim_success(p))
                else: self.after(0, lambda: self.update_status(msg_base, "green", True)); self.after(100, lambda p=final_out_actual: self.post_trim_success(p))
            else:
                err_det = stderr if stderr else "No stderr"; err_m = f"FFmpeg failed (code {proc.returncode}):\n{err_det[-500:]}"
                if proc.returncode==0 and not(os.path.exists(ffmpeg_target) and os.path.getsize(ffmpeg_target)>0): err_m="FFmpeg OK, but output missing/empty."
                print(err_m); self.after(0, lambda: self.update_status(err_m, "red", True))
                if ffmpeg_target and os.path.exists(ffmpeg_target):
                    try: os.remove(ffmpeg_target)
                    except OSError as e: print(f"Error cleaning failed output: {e}")
                    if ffmpeg_target in temp_files_to_cleanup: temp_files_to_cleanup.remove(ffmpeg_target)
                self.after(100, self.reset_ui_after_processing)
        except Exception as e:
            import traceback; det_err = traceback.format_exc(); print(f"Trim error: {type(e).__name__}: {e}\n{det_err}")
            self.after(0, lambda: self.update_status(f"Unexpected trim error: {e}", "red", True))
            if ffmpeg_target and os.path.exists(ffmpeg_target) and ffmpeg_target in temp_files_to_cleanup:
                try: os.remove(ffmpeg_target); temp_files_to_cleanup.remove(ffmpeg_target)
                except Exception as ce: print(f"Error cleaning temp output: {ce}")
            self.after(100, self.reset_ui_after_processing)
        finally: self.pending_custom_filename = None

    def post_trim_success(self, output_filepath, deleted_original_path=None):
        print(f"Trim ended. Final file: {output_filepath or 'None'}"); self.is_processing = False
        should_preserve = True
        if deleted_original_path and self.video_path == deleted_original_path: self.video_path = None; should_preserve = False
        self.refresh_video_list(preserve_selection=should_preserve)
        if not self.video_path: self.disable_ui_components(True)
        else: self.disable_ui_components(False)

    def reset_ui_after_processing(self):
        self.is_processing = False; self.pending_custom_filename = None; self.refresh_video_list(True)
        if not self.video_path and not self.location_overlay_canvas: self.disable_ui_components(True)

    def update_status(self, message, color="gray", is_persistent_trim_status=False, is_temporary=False):
        if self.status_message_clear_job: self.after_cancel(self.status_message_clear_job); self.status_message_clear_job = None
        def _upd():
            if hasattr(self, 'status_label') and self.status_label.winfo_exists(): self.status_label.configure(text=message, text_color=color)
        if is_persistent_trim_status: self.last_trim_status_message = message; self.last_trim_status_color = color; self.temporary_status_active = False; self.after(0, _upd)
        elif is_temporary: self.temporary_status_active = True; self.after(0, _upd); self.status_message_clear_job = self.after(config_settings.STATUS_MESSAGE_CLEAR_DELAY_MS, self._revert_to_persistent_status)
        else:
            if not self.last_trim_status_message or color=="red": self.last_trim_status_message = ""
            self.temporary_status_active = False; self.after(0, _upd)

    def _revert_to_persistent_status(self):
        self.temporary_status_active = False
        txt = self.last_trim_status_message or ""; col = self.last_trim_status_color or "gray"
        if not self.current_input_directory and self.location_overlay_canvas: txt = "Select video directory."; col = "orange"
        def _upd():
            if hasattr(self, 'status_label') and self.status_label.winfo_exists(): self.status_label.configure(text=txt, text_color=col)
        self.after(0, _upd); self.status_message_clear_job = None

    def show_error_and_quit(self, message):
        print(f"FATAL: {message}"); temp_root = False; parent_win = self
        if not (hasattr(self, 'title') and self.winfo_exists()):
            try: r = tkinter.Tk(); r.withdraw(); parent_win = r; temp_root = True
            except tkinter.TclError: print("TclError: No Tk for error."); cleanup_temp_files(); sys.exit(1)
        if parent_win and hasattr(parent_win, 'winfo_exists') and parent_win.winfo_exists(): tkinter.messagebox.showerror("Critical Error", message, parent=parent_win)
        if temp_root and hasattr(parent_win, 'destroy'): parent_win.destroy()
        elif hasattr(self, 'destroy') and self.winfo_exists(): self.destroy()
        cleanup_temp_files(); sys.exit(1)

    def on_closing(self):
        print("Closing application.")
        if self.start_thumb_job: self.after_cancel(self.start_thumb_job)
        if self.end_thumb_job: self.after_cancel(self.end_thumb_job)
        if self.status_message_clear_job: self.after_cancel(self.status_message_clear_job)
        if self.is_processing: print("Warning: Closing during processing.")
        utils.cleanup_temp_files(); 
        if self.winfo_exists(): self.destroy()
        sys.exit(0)