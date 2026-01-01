#!/usr/bin/env python3
"""
Audio Recorder with RX11 Integration and Input Monitoring
Full-featured recorder with arming/monitoring capability
"""

import sounddevice as sd
import soundfile as sf
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import datetime
import os
from pathlib import Path
import json
import subprocess

class AudioRecorderRX11Armed:
    def __init__(self, root):
        self.root = root
        self.root.title("Audio Recorder - Traktor Audio 6 (with Monitoring & RX11)")
        self.root.geometry("700x600")
        
        # Recording state
        self.is_recording = False
        self.is_monitoring = False
        self.is_armed = False  # Monitoring armed (input to output)
        self.audio_queue = queue.Queue()
        self.monitor_queue = queue.Queue()
        self.recorded_frames = []
        self.current_filename = None
        
        # Settings
        self.sample_rate = 44100
        self.bit_depth = 24
        self.channels = 2
        self.input_device_index = None
        self.output_device_index = None
        
        # Auto-record settings
        self.auto_mode = False
        self.silence_threshold_db = -40.0
        self.silence_duration = 2.0
        self.min_recording_duration = 1.0
        self.silence_start_time = None
        self.recording_start_time = None
        self.in_sound_segment = False
        
        # Trim settings
        self.trim_silence_start = True
        self.trim_silence_end = True
        self.trim_threshold_db = -50.0  # Threshold for detecting silence to trim
        
        # RX11 settings
        self.rx11_auto_open = False
        self.rx11_path = self.find_rx11()
        
        # Video creation settings
        self.create_video = False
        self.video_folder = r"J:\My Drive\Picsforrev"
        self.video_resolution = '1080p'
        
        # Level monitoring
        self.current_level_l = -100
        self.current_level_r = -100
        
        # Monitor volume
        self.monitor_volume = 0.7
        
        # File settings
        self.output_folder = str(Path.home() / "Recordings")
        self.file_prefix = "Recording"
        self.file_counter = 1
        
        # Streams
        self.input_stream = None
        self.output_stream = None
        
        # Load settings
        self.load_settings()
        
        # Create GUI
        self.create_gui()
        
        # Start monitoring after GUI is ready (use after_idle to ensure GUI is fully initialized)
        self.root.after_idle(self.start_input_monitoring)
        
        # Setup hotkeys
        self.setup_hotkeys()
    
    def find_rx11(self):
        """Try to find RX11 installation"""
        common_paths = [
            r"C:\Program Files\iZotope\RX 11\RX 11 Audio Editor.exe",
            r"C:\Program Files (x86)\iZotope\RX 11\RX 11 Audio Editor.exe",
            r"/Applications/iZotope RX 11.app/Contents/MacOS/RX 11 Audio Editor",
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
        return None
    
    def create_gui(self):
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self.root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        scrollable_frame = ttk.Frame(self.canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack canvas and scrollbar
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Main container (now inside scrollable frame)
        main_frame = ttk.Frame(scrollable_frame, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Input Device selection
        input_device_frame = ttk.LabelFrame(main_frame, text="Input Device", padding="5")
        input_device_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.input_device_var = tk.StringVar()
        self.input_device_combo = ttk.Combobox(input_device_frame, textvariable=self.input_device_var, width=45, state='readonly')
        self.input_device_combo.grid(row=0, column=0, padx=5, pady=5)
        self.populate_input_devices()
        self.input_device_combo.bind('<<ComboboxSelected>>', self.on_input_device_change)
        
        ttk.Button(input_device_frame, text="Refresh", command=self.populate_input_devices).grid(row=0, column=1, padx=5)
        
        # Output Device selection
        output_device_frame = ttk.LabelFrame(main_frame, text="Output Device (for monitoring)", padding="5")
        output_device_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.output_device_var = tk.StringVar()
        self.output_device_combo = ttk.Combobox(output_device_frame, textvariable=self.output_device_var, width=45, state='readonly')
        self.output_device_combo.grid(row=0, column=0, padx=5, pady=5)
        self.populate_output_devices()
        self.output_device_combo.bind('<<ComboboxSelected>>', self.on_output_device_change)
        
        ttk.Button(output_device_frame, text="Refresh", command=self.populate_output_devices).grid(row=0, column=1, padx=5)
        
        # Monitor control
        monitor_frame = ttk.Frame(output_device_frame)
        monitor_frame.grid(row=1, column=0, columnspan=2, pady=5)
        
        self.arm_var = tk.BooleanVar(value=False)
        self.arm_button = ttk.Checkbutton(monitor_frame, text="🎧 ARM (Enable Input Monitoring)", 
                                         variable=self.arm_var, command=self.toggle_arm,
                                         style='Armed.TCheckbutton')
        self.arm_button.grid(row=0, column=0, padx=5)
        
        ttk.Label(monitor_frame, text="Monitor Volume:").grid(row=0, column=1, padx=(20, 5))
        self.volume_var = tk.DoubleVar(value=self.monitor_volume)
        volume_scale = ttk.Scale(monitor_frame, from_=0.0, to=1.0, variable=self.volume_var,
                                orient=tk.HORIZONTAL, length=150, command=self.update_monitor_volume)
        volume_scale.grid(row=0, column=2, padx=5)
        self.volume_label = ttk.Label(monitor_frame, text=f"{int(self.monitor_volume*100)}%", width=5)
        self.volume_label.grid(row=0, column=3, padx=5)
        
        # Level meters
        meter_frame = ttk.LabelFrame(main_frame, text="Input Levels", padding="5")
        meter_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(meter_frame, text="Left:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.level_l_canvas = tk.Canvas(meter_frame, width=400, height=20, bg='black')
        self.level_l_canvas.grid(row=0, column=1, padx=5, pady=2)
        self.level_l_label = ttk.Label(meter_frame, text="-inf dB", width=10)
        self.level_l_label.grid(row=0, column=2, padx=5)
        
        ttk.Label(meter_frame, text="Right:").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.level_r_canvas = tk.Canvas(meter_frame, width=400, height=20, bg='black')
        self.level_r_canvas.grid(row=1, column=1, padx=5, pady=2)
        self.level_r_label = ttk.Label(meter_frame, text="-inf dB", width=10)
        self.level_r_label.grid(row=1, column=2, padx=5)
        
        # Recording status
        status_frame = ttk.LabelFrame(main_frame, text="Recording Status", padding="5")
        status_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Ready", font=('Arial', 12, 'bold'))
        self.status_label.grid(row=0, column=0, pady=5)
        
        self.filename_label = ttk.Label(status_frame, text="", foreground='blue')
        self.filename_label.grid(row=1, column=0, pady=5)
        
        self.duration_label = ttk.Label(status_frame, text="Duration: 0:00")
        self.duration_label.grid(row=2, column=0, pady=5)
        
        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        self.record_button = ttk.Button(button_frame, text="⏺ Record (F9)", command=self.start_recording, width=20)
        self.record_button.grid(row=0, column=0, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="⏹ Stop (F10)", command=self.stop_recording, state='disabled', width=20)
        self.stop_button.grid(row=0, column=1, padx=5)
        
        # Auto-record settings
        auto_frame = ttk.LabelFrame(main_frame, text="Auto-Record Settings", padding="5")
        auto_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.auto_var = tk.BooleanVar(value=self.auto_mode)
        ttk.Checkbutton(auto_frame, text="Enable Auto-Record (starts on audio after silence)", 
                       variable=self.auto_var, command=self.toggle_auto_mode).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(auto_frame, text="Silence Threshold (dB):").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.threshold_var = tk.DoubleVar(value=self.silence_threshold_db)
        threshold_frame = ttk.Frame(auto_frame)
        threshold_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Scale(threshold_frame, from_=-60, to=-10, variable=self.threshold_var, 
                 orient=tk.HORIZONTAL, length=200).grid(row=0, column=0)
        ttk.Label(threshold_frame, textvariable=self.threshold_var, width=8).grid(row=0, column=1, padx=5)
        
        ttk.Label(auto_frame, text="Silence Duration (sec):").grid(row=2, column=0, sticky=tk.W, padx=5)
        self.duration_var = tk.DoubleVar(value=self.silence_duration)
        duration_frame = ttk.Frame(auto_frame)
        duration_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Scale(duration_frame, from_=0.5, to=5.0, variable=self.duration_var,
                 orient=tk.HORIZONTAL, length=200).grid(row=0, column=0)
        ttk.Label(duration_frame, textvariable=self.duration_var, width=8).grid(row=0, column=1, padx=5)
        
        # Trim Silence settings
        trim_frame = ttk.LabelFrame(main_frame, text="Trim Silence from Recordings", padding="5")
        trim_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.trim_start_var = tk.BooleanVar(value=self.trim_silence_start)
        ttk.Checkbutton(trim_frame, text="Trim silence from beginning", 
                       variable=self.trim_start_var, command=self.toggle_trim_settings).grid(row=0, column=0, sticky=tk.W, pady=2, padx=5)
        
        self.trim_end_var = tk.BooleanVar(value=self.trim_silence_end)
        ttk.Checkbutton(trim_frame, text="Trim silence from end", 
                       variable=self.trim_end_var, command=self.toggle_trim_settings).grid(row=1, column=0, sticky=tk.W, pady=2, padx=5)
        
        ttk.Label(trim_frame, text="Trim Threshold (dB):").grid(row=2, column=0, sticky=tk.W, padx=5)
        self.trim_threshold_var = tk.DoubleVar(value=self.trim_threshold_db)
        trim_threshold_frame = ttk.Frame(trim_frame)
        trim_threshold_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Scale(trim_threshold_frame, from_=-60, to=-30, variable=self.trim_threshold_var, 
                 orient=tk.HORIZONTAL, length=200, command=self.update_trim_threshold).grid(row=0, column=0)
        ttk.Label(trim_threshold_frame, textvariable=self.trim_threshold_var, width=8).grid(row=0, column=1, padx=5)
        
        ttk.Label(trim_frame, text="(Lower = more aggressive trimming)", 
                 font=('Arial', 8), foreground='gray').grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5)
        
        # RX11 Integration
        rx11_frame = ttk.LabelFrame(main_frame, text="RX11 Integration", padding="5")
        rx11_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.rx11_var = tk.BooleanVar(value=self.rx11_auto_open)
        rx11_check = ttk.Checkbutton(rx11_frame, text="Auto-open recordings in RX11", 
                                     variable=self.rx11_var, command=self.toggle_rx11)
        rx11_check.grid(row=0, column=0, sticky=tk.W, pady=5)
        
        rx11_path_frame = ttk.Frame(rx11_frame)
        rx11_path_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(rx11_path_frame, text="RX11 Path:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.rx11_path_label = ttk.Label(rx11_path_frame, 
                                         text=self.rx11_path if self.rx11_path else "Not found",
                                         foreground='blue' if self.rx11_path else 'red',
                                         wraplength=400)
        self.rx11_path_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Button(rx11_path_frame, text="Browse...", command=self.browse_rx11).grid(row=0, column=2, padx=5)
        
        if not self.rx11_path:
            rx11_check.config(state='disabled')
        
        # Video Creation
        video_frame = ttk.LabelFrame(main_frame, text="YouTube Video Creation", padding="5")
        video_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.video_var = tk.BooleanVar(value=self.create_video)
        video_check = ttk.Checkbutton(video_frame, text="Auto-create YouTube video after recording", 
                                      variable=self.video_var, command=self.toggle_video_creation)
        video_check.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=5)
        
        ttk.Label(video_frame, text="Image/Video Folder:").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.video_folder_label = ttk.Label(video_frame, text=self.video_folder, 
                                           foreground='blue', wraplength=400)
        self.video_folder_label.grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Button(video_frame, text="Browse...", command=self.browse_video_folder).grid(row=1, column=2, padx=5)
        
        ttk.Label(video_frame, text="Video Resolution:").grid(row=2, column=0, sticky=tk.W, padx=5)
        self.video_res_var = tk.StringVar(value=self.video_resolution)
        res_combo = ttk.Combobox(video_frame, textvariable=self.video_res_var, 
                                values=['480p', '720p', '1080p'], state='readonly', width=10)
        res_combo.grid(row=2, column=1, sticky=tk.W, padx=5)
        res_combo.bind('<<ComboboxSelected>>', self.on_video_res_change)
        
        ttk.Label(video_frame, text="Tip: Click 'Browse...' to choose where your images/videos are stored", 
                 font=('Arial', 8), foreground='gray').grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=5)
        
        # File settings
        file_frame = ttk.LabelFrame(main_frame, text="File Settings", padding="5")
        file_frame.grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(file_frame, text="Output Folder:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.folder_label = ttk.Label(file_frame, text=self.output_folder, foreground='blue')
        self.folder_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Button(file_frame, text="Browse...", command=self.browse_folder).grid(row=0, column=2, padx=5)
        
        ttk.Label(file_frame, text="File Prefix:").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.prefix_var = tk.StringVar(value=self.file_prefix)
        ttk.Entry(file_frame, textvariable=self.prefix_var, width=30).grid(row=1, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(file_frame, text="File Counter:").grid(row=2, column=0, sticky=tk.W, padx=5)
        self.counter_var = tk.IntVar(value=self.file_counter)
        ttk.Spinbox(file_frame, from_=1, to=9999, textvariable=self.counter_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=5)
        
        # Format info
        info_frame = ttk.Frame(main_frame)
        info_frame.grid(row=9, column=0, columnspan=2, pady=10)
        ttk.Label(info_frame, text="Format: WAV, 44.1kHz, 24-bit, Stereo", 
                 font=('Arial', 9), foreground='gray').pack()
        
        # Configure styles
        style = ttk.Style()
        style.configure('Armed.TCheckbutton', font=('Arial', 10, 'bold'))
    
    def update_monitor_volume(self, value=None):
        """Update monitor volume"""
        self.monitor_volume = self.volume_var.get()
        self.volume_label.config(text=f"{int(self.monitor_volume*100)}%")
        self.save_settings()
    
    def toggle_trim_settings(self):
        """Toggle trim silence settings"""
        self.trim_silence_start = self.trim_start_var.get()
        self.trim_silence_end = self.trim_end_var.get()
        self.save_settings()
    
    def update_trim_threshold(self, value=None):
        """Update trim threshold"""
        self.trim_threshold_db = self.trim_threshold_var.get()
        self.save_settings()
    
    def toggle_arm(self):
        """Toggle input monitoring (arm)"""
        self.is_armed = self.arm_var.get()
        
        if self.is_armed:
            self.start_output_monitoring()
            self.status_label.config(text="ARMED - Monitoring Input", foreground='orange')
        else:
            self.stop_output_monitoring(force=False)  # Graceful stop when manually disarming
            if not self.is_recording:
                self.status_label.config(text="Ready", foreground='black')
        
        self.save_settings()
    
    def browse_rx11(self):
        """Browse for RX11 executable"""
        filetypes = [("Executable", "*.exe")] if os.name == 'nt' else [("Application", "*")]
        filepath = filedialog.askopenfilename(title="Select RX11 Audio Editor", filetypes=filetypes)
        if filepath and os.path.exists(filepath):
            self.rx11_path = filepath
            self.rx11_path_label.config(text=filepath, foreground='blue')
            self.save_settings()
    
    def toggle_rx11(self):
        """Toggle RX11 auto-open"""
        self.rx11_auto_open = self.rx11_var.get()
        self.save_settings()
    
    def toggle_video_creation(self):
        """Toggle video creation"""
        self.create_video = self.video_var.get()
        self.save_settings()
    
    def browse_video_folder(self):
        """Browse for video/image folder"""
        folder = filedialog.askdirectory(initialdir=self.video_folder)
        if folder:
            self.video_folder = folder
            self.video_folder_label.config(text=folder)
            self.save_settings()
    
    def on_video_res_change(self, event=None):
        """Handle video resolution change"""
        self.video_resolution = self.video_res_var.get()
        self.save_settings()
    
    def populate_input_devices(self):
        """Populate input device dropdown"""
        devices = sd.query_devices()
        input_devices = []
        
        for i, device in enumerate(devices):
            if device['max_input_channels'] >= 2:
                name = f"{i}: {device['name']}"
                input_devices.append(name)
                
                if 'traktor' in device['name'].lower() or 'audio 6' in device['name'].lower():
                    self.input_device_index = i
        
        self.input_device_combo['values'] = input_devices
        
        if self.input_device_index is not None:
            try:
                device_name = devices[self.input_device_index]['name']
                self.input_device_combo.set(f"{self.input_device_index}: {device_name}")
            except:
                if input_devices:
                    self.input_device_combo.current(0)
                    self.input_device_index = int(input_devices[0].split(':')[0])
        elif input_devices:
            self.input_device_combo.current(0)
            self.input_device_index = int(input_devices[0].split(':')[0])
    
    def populate_output_devices(self):
        """Populate output device dropdown"""
        devices = sd.query_devices()
        output_devices = []
        
        for i, device in enumerate(devices):
            if device['max_output_channels'] >= 2:
                name = f"{i}: {device['name']}"
                output_devices.append(name)
                
                # Try to select Traktor or default output
                if self.output_device_index is None:
                    if 'traktor' in device['name'].lower() or 'audio 6' in device['name'].lower():
                        self.output_device_index = i
                    elif device.get('default_samplerate') and 'default' in str(device).lower():
                        self.output_device_index = i
        
        self.output_device_combo['values'] = output_devices
        
        if self.output_device_index is not None:
            try:
                device_name = devices[self.output_device_index]['name']
                self.output_device_combo.set(f"{self.output_device_index}: {device_name}")
            except:
                if output_devices:
                    self.output_device_combo.current(0)
                    self.output_device_index = int(output_devices[0].split(':')[0])
        elif output_devices:
            self.output_device_combo.current(0)
            self.output_device_index = int(output_devices[0].split(':')[0])
    
    def on_input_device_change(self, event=None):
        """Handle input device selection change"""
        selection = self.input_device_var.get()
        if selection:
            self.input_device_index = int(selection.split(':')[0])
            self.save_settings()
            # Restart monitoring in a separate thread to avoid blocking GUI
            threading.Thread(target=self.restart_input_monitoring, daemon=True).start()
    
    def restart_input_monitoring(self):
        """Restart input monitoring with new device"""
        if self.is_monitoring:
            self.stop_input_monitoring(force=True)  # Force immediate shutdown for device change
            import time
            time.sleep(0.1)  # Brief pause to ensure clean shutdown
            self.start_input_monitoring()
    
    def on_output_device_change(self, event=None):
        """Handle output device selection change"""
        selection = self.output_device_var.get()
        if selection:
            self.output_device_index = int(selection.split(':')[0])
            self.save_settings()
            # Restart monitoring in a separate thread to avoid blocking GUI
            if self.is_armed:
                threading.Thread(target=self.restart_output_monitoring, daemon=True).start()
    
    def restart_output_monitoring(self):
        """Restart output monitoring with new device"""
        self.stop_output_monitoring(force=True)  # Force immediate shutdown for device change
        import time
        time.sleep(0.1)  # Brief pause to ensure clean shutdown
        self.start_output_monitoring()
    
    def browse_folder(self):
        """Browse for output folder"""
        folder = filedialog.askdirectory(initialdir=self.output_folder)
        if folder:
            self.output_folder = folder
            self.folder_label.config(text=folder)
            self.save_settings()
    
    def toggle_auto_mode(self):
        """Toggle auto-record mode"""
        self.auto_mode = self.auto_var.get()
        self.save_settings()
        if self.auto_mode and not self.is_recording:
            self.status_label.config(text="Auto-Record Enabled - Waiting for audio...")
        elif not self.is_recording and not self.is_armed:
            self.status_label.config(text="Ready")
    
    def calculate_db(self, audio_data):
        """Calculate dB level from audio data"""
        if len(audio_data) == 0:
            return -100
        
        rms = np.sqrt(np.mean(audio_data**2))
        if rms > 0:
            db = 20 * np.log10(rms)
        else:
            db = -100
        return db
    
    def update_levels(self, audio_data):
        """Update level meters with current audio data"""
        if audio_data.ndim == 2 and audio_data.shape[1] >= 2:
            left = audio_data[:, 0]
            right = audio_data[:, 1]
        else:
            left = right = audio_data
        
        self.current_level_l = self.calculate_db(left)
        self.current_level_r = self.calculate_db(right)
        
        self.root.after(0, self.draw_meters)
    
    def draw_meters(self):
        """Draw the level meters"""
        width = 400
        height = 20
        
        # Left meter
        self.level_l_canvas.delete('all')
        level_normalized_l = max(0, min(1, (self.current_level_l + 60) / 60))
        bar_width_l = int(width * level_normalized_l)
        
        color_l = 'red' if self.current_level_l > -6 else ('yellow' if self.current_level_l > -18 else 'green')
        self.level_l_canvas.create_rectangle(0, 0, bar_width_l, height, fill=color_l, outline='')
        
        # Right meter
        self.level_r_canvas.delete('all')
        level_normalized_r = max(0, min(1, (self.current_level_r + 60) / 60))
        bar_width_r = int(width * level_normalized_r)
        
        color_r = 'red' if self.current_level_r > -6 else ('yellow' if self.current_level_r > -18 else 'green')
        self.level_r_canvas.create_rectangle(0, 0, bar_width_r, height, fill=color_r, outline='')
        
        # Update labels
        self.level_l_label.config(text=f"{self.current_level_l:.1f} dB" if self.current_level_l > -100 else "-inf dB")
        self.level_r_label.config(text=f"{self.current_level_r:.1f} dB" if self.current_level_r > -100 else "-inf dB")
    
    def input_callback(self, indata, frames, time_info, status):
        """Audio callback for input stream"""
        try:
            if status:
                print(f"Input callback status: {status}")
            
            audio_copy = indata.copy()
            self.update_levels(audio_copy)
            
            # If recording, add to recording queue
            if self.is_recording:
                self.audio_queue.put(audio_copy)
            
            # If armed for monitoring, add to monitor queue
            if self.is_armed:
                self.monitor_queue.put(audio_copy)
            
            # Auto-record logic
            if self.auto_mode and not self.is_recording:
                max_level = max(self.current_level_l, self.current_level_r)
                
                if max_level > self.silence_threshold_db:
                    if not self.in_sound_segment:
                        self.in_sound_segment = True
                        self.silence_start_time = None
                        self.root.after(0, self.start_recording)
                else:
                    self.in_sound_segment = False
        
        except Exception as e:
            print(f"Error in input callback: {e}")
            import traceback
            traceback.print_exc()
    
    def output_callback(self, outdata, frames, time_info, status):
        """Audio callback for output stream (monitoring)"""
        try:
            if status:
                print(f"Output callback status: {status}")
            
            try:
                # Get audio from monitor queue
                data = self.monitor_queue.get_nowait()
                # Apply volume
                data = data * self.monitor_volume
                # Ensure correct shape
                if data.shape[0] < frames:
                    # Pad with zeros if needed
                    padding = np.zeros((frames - data.shape[0], self.channels))
                    data = np.vstack([data, padding])
                elif data.shape[0] > frames:
                    # Trim if needed
                    data = data[:frames]
                outdata[:] = data
            except queue.Empty:
                # No audio available, output silence
                outdata[:] = np.zeros((frames, self.channels))
        
        except Exception as e:
            print(f"Error in output callback: {e}")
            outdata[:] = np.zeros((frames, self.channels))
            import traceback
            traceback.print_exc()
    
    def start_input_monitoring(self):
        """Start monitoring audio input (for levels only)"""
        if self.input_device_index is None:
            print("No input device selected")
            return
        
        try:
            # Make sure any existing stream is closed first
            if self.input_stream:
                try:
                    self.input_stream.stop()
                    self.input_stream.close()
                except:
                    pass
                self.input_stream = None
            
            print(f"Starting input monitoring on device {self.input_device_index}...")
            
            self.input_stream = sd.InputStream(
                device=self.input_device_index,
                channels=self.channels,
                samplerate=self.sample_rate,
                callback=self.input_callback,
                blocksize=2048
            )
            self.input_stream.start()
            self.is_monitoring = True
            print("Input monitoring started successfully")
            
        except Exception as e:
            error_msg = f"Failed to start input monitoring: {str(e)}"
            print(error_msg)
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
    
    def stop_input_monitoring(self, force=False):
        """Stop monitoring audio input"""
        if self.input_stream:
            try:
                print("Stopping input monitoring...")
                if force:
                    # Use abort for immediate shutdown
                    self.input_stream.abort()
                else:
                    # Use stop for graceful shutdown
                    self.input_stream.stop()
                self.input_stream.close()
                print("Input monitoring stopped")
            except Exception as e:
                print(f"Error stopping input stream: {e}")
            finally:
                self.input_stream = None
                self.is_monitoring = False
    
    def start_output_monitoring(self):
        """Start output monitoring (armed - input to output)"""
        if self.output_device_index is None:
            error_msg = "No output device selected"
            print(error_msg)
            self.is_armed = False
            self.arm_var.set(False)
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
            return
        
        try:
            # Make sure any existing stream is closed first
            if self.output_stream:
                try:
                    self.output_stream.stop()
                    self.output_stream.close()
                except:
                    pass
                self.output_stream = None
            
            print(f"Starting output monitoring on device {self.output_device_index}...")
            
            self.output_stream = sd.OutputStream(
                device=self.output_device_index,
                channels=self.channels,
                samplerate=self.sample_rate,
                callback=self.output_callback,
                blocksize=2048
            )
            self.output_stream.start()
            print("Output monitoring started successfully (armed)")
            
        except Exception as e:
            error_msg = f"Failed to start output monitoring: {str(e)}"
            print(error_msg)
            self.is_armed = False
            self.arm_var.set(False)
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
    
    def stop_output_monitoring(self, force=False):
        """Stop output monitoring"""
        if self.output_stream:
            try:
                print("Stopping output monitoring...")
                if force:
                    # Use abort for immediate shutdown
                    self.output_stream.abort()
                else:
                    # Use stop for graceful shutdown
                    self.output_stream.stop()
                self.output_stream.close()
                print("Output monitoring stopped")
            except Exception as e:
                print(f"Error stopping output stream: {e}")
            finally:
                self.output_stream = None
    
    def start_recording(self):
        """Start recording audio"""
        if self.is_recording:
            return
        
        os.makedirs(self.output_folder, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = self.prefix_var.get()
        counter = self.counter_var.get()
        
        self.current_filename = os.path.join(
            self.output_folder,
            f"{prefix}_{counter:04d}_{timestamp}.wav"
        )
        
        self.recorded_frames = []
        self.is_recording = True
        self.recording_start_time = datetime.datetime.now()
        
        self.status_label.config(text="⏺ RECORDING", foreground='red')
        self.filename_label.config(text=os.path.basename(self.current_filename))
        self.record_button.config(state='disabled')
        self.stop_button.config(state='normal')
        
        self.update_duration()
        threading.Thread(target=self.recording_thread, daemon=True).start()
        
        self.counter_var.set(counter + 1)
    
    def recording_thread(self):
        """Thread to collect recorded audio"""
        silence_frames = 0
        silence_frame_threshold = int(self.silence_duration * self.sample_rate / 2048)
        
        while self.is_recording:
            try:
                data = self.audio_queue.get(timeout=0.1)
                self.recorded_frames.append(data)
                
                if self.auto_mode:
                    max_level = max(self.current_level_l, self.current_level_r)
                    
                    if max_level < self.silence_threshold_db:
                        silence_frames += 1
                        if silence_frames >= silence_frame_threshold:
                            recording_duration = (datetime.datetime.now() - self.recording_start_time).total_seconds()
                            if recording_duration >= self.min_recording_duration:
                                self.root.after(0, self.stop_recording)
                                break
                    else:
                        silence_frames = 0
                        
            except queue.Empty:
                continue
    
    def stop_recording(self):
        """Stop recording audio"""
        if not self.is_recording:
            return
        
        self.is_recording = False
        
        self.status_label.config(text="Saving...", foreground='orange')
        self.record_button.config(state='normal')
        self.stop_button.config(state='disabled')
        
        threading.Thread(target=self.save_recording, daemon=True).start()
    
    def save_recording(self):
        """Save recorded audio to file"""
        if not self.recorded_frames:
            self.root.after(0, self.update_status_after_save)
            return
        
        try:
            audio_data = np.concatenate(self.recorded_frames, axis=0)
            
            # Trim silence from beginning and/or end
            if self.trim_silence_start or self.trim_silence_end:
                audio_data = self.trim_silence(audio_data)
            
            # Check if we still have audio after trimming
            if len(audio_data) == 0:
                print("Warning: Recording was entirely silence after trimming")
                self.root.after(0, self.update_status_after_save)
                self.root.after(0, lambda: self.filename_label.config(text="Recording was empty (all silence)"))
                return
            
            sf.write(self.current_filename, audio_data, self.sample_rate, subtype='PCM_24')
            
            print(f"Saved: {self.current_filename}")
            
            # Auto-open in RX11 if enabled
            if self.rx11_auto_open and self.rx11_path:
                try:
                    subprocess.Popen([self.rx11_path, self.current_filename])
                    print(f"Opened in RX11: {self.current_filename}")
                except Exception as e:
                    print(f"Error opening in RX11: {e}")
            
            # Create video if enabled
            if self.create_video:
                self.root.after(0, lambda: self.prompt_video_creation(self.current_filename))
            
            self.root.after(0, self.update_status_after_save)
            self.root.after(0, lambda: self.filename_label.config(text=f"Saved: {os.path.basename(self.current_filename)}"))
            
        except Exception as e:
            print(f"Error saving file: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to save recording: {str(e)}"))
            self.root.after(0, lambda: self.status_label.config(text="Error", foreground='red'))
    
    def trim_silence(self, audio_data):
        """Trim silence from beginning and/or end of audio data"""
        if len(audio_data) == 0:
            return audio_data
        
        # Calculate RMS for each frame to detect silence
        frame_length = 2048  # Process in chunks
        num_frames = len(audio_data) // frame_length
        
        if num_frames == 0:
            return audio_data
        
        # Get max level (loudest channel) for each frame
        frame_levels = []
        for i in range(num_frames):
            start_idx = i * frame_length
            end_idx = start_idx + frame_length
            frame = audio_data[start_idx:end_idx]
            
            if frame.ndim == 2:
                # Stereo - take max of both channels
                level_l = self.calculate_db(frame[:, 0])
                level_r = self.calculate_db(frame[:, 1])
                level = max(level_l, level_r)
            else:
                level = self.calculate_db(frame)
            
            frame_levels.append(level)
        
        # Find first non-silent frame from start
        start_frame = 0
        if self.trim_silence_start:
            for i, level in enumerate(frame_levels):
                if level > self.trim_threshold_db:
                    start_frame = i
                    break
        
        # Find last non-silent frame from end
        end_frame = num_frames
        if self.trim_silence_end:
            for i in range(num_frames - 1, -1, -1):
                if frame_levels[i] > self.trim_threshold_db:
                    end_frame = i + 1
                    break
        
        # Make sure we have valid range
        if start_frame >= end_frame:
            return np.array([])  # All silence
        
        # Convert frame indices to sample indices
        start_sample = start_frame * frame_length
        end_sample = min(end_frame * frame_length, len(audio_data))
        
        # Trim the audio
        trimmed_audio = audio_data[start_sample:end_sample]
        
        if self.trim_silence_start or self.trim_silence_end:
            trimmed_duration = len(trimmed_audio) / self.sample_rate
            original_duration = len(audio_data) / self.sample_rate
            removed_duration = original_duration - trimmed_duration
            print(f"Trimmed {removed_duration:.2f}s of silence (original: {original_duration:.2f}s, final: {trimmed_duration:.2f}s)")
        
        return trimmed_audio
    
    def prompt_video_creation(self, audio_file):
        """Prompt user to select image or video file for YouTube video creation"""
        result = messagebox.askyesno(
            "Create YouTube Video",
            f"Recording saved: {os.path.basename(audio_file)}\n\n"
            "Would you like to create a YouTube video now?"
        )
        
        if not result:
            return
        
        # Open file dialog in the video folder
        filetypes = [
            ("Image and Video files", "*.jpg *.jpeg *.png *.gif *.bmp *.mov *.mp4 *.avi *.mkv *.wmv *.flv *.webm *.m4v *.mpg *.mpeg"),
            ("Image files", "*.jpg *.jpeg *.png *.gif *.bmp"),
            ("Video files", "*.mov *.mp4 *.avi *.mkv *.wmv *.flv *.webm *.m4v *.mpg *.mpeg"),
            ("All files", "*.*")
        ]
        
        media_file = filedialog.askopenfilename(
            title="Select Image or Video for YouTube Video",
            initialdir=self.video_folder,
            filetypes=filetypes
        )
        
        if not media_file:
            return
        
        # Ask if they want a fallback image (only if selected file is a video)
        fallback_image = None
        if self.is_video_file(media_file):
            use_fallback = messagebox.askyesno(
                "Fallback Image",
                "Do you want to select a fallback image?\n\n"
                "If the video is shorter than the audio, the fallback image will display for the remainder.\n"
                "(Select 'No' to loop the video instead)"
            )
            
            if use_fallback:
                fallback_image = filedialog.askopenfilename(
                    title="Select Fallback Image",
                    initialdir=self.video_folder,
                    filetypes=[
                        ("Image files", "*.jpg *.jpeg *.png *.gif *.bmp"),
                        ("All files", "*.*")
                    ]
                )
        
        # Create video in separate thread
        threading.Thread(
            target=self.create_youtube_video,
            args=(media_file, audio_file, fallback_image),
            daemon=True
        ).start()
    
    def is_video_file(self, file_path):
        """Check if file is a video based on extension"""
        video_extensions = {'.mov', '.mp4', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg'}
        ext = Path(file_path).suffix.lower()
        return ext in video_extensions
    
    def get_media_duration(self, file_path):
        """Get duration of a media file in seconds"""
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                 '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
                capture_output=True,
                text=True,
                check=True
            )
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            return None
    
    def create_youtube_video(self, media_file, audio_file, fallback_image=None):
        """Create YouTube-ready video from media file and audio"""
        try:
            # Update status
            self.root.after(0, lambda: self.status_label.config(text="Creating video...", foreground='blue'))
            
            # Generate output filename
            audio_name = Path(audio_file).stem
            output_path = os.path.join(self.output_folder, f"{audio_name}_youtube.mp4")
            
            # Resolution mapping
            resolutions = {
                '720p': '1280:720',
                '1080p': '1920:1080',
                '480p': '854:480'
            }
            scale = resolutions.get(self.video_resolution, '1920:1080')
            
            is_video = self.is_video_file(media_file)
            
            print(f"\nCreating YouTube video...")
            print(f"Media: {media_file}")
            print(f"Audio: {audio_file}")
            print(f"Resolution: {self.video_resolution} ({scale})")
            
            if is_video and fallback_image:
                # Complex mode: video then fallback image
                video_duration = self.get_media_duration(media_file)
                audio_duration = self.get_media_duration(audio_file)
                
                if video_duration is None or audio_duration is None:
                    raise RuntimeError("Could not determine media durations")
                
                if audio_duration <= video_duration:
                    # Audio is shorter, just use video
                    command = [
                        'ffmpeg',
                        '-i', media_file,
                        '-i', audio_file,
                        '-map', '0:v:0',
                        '-map', '1:a:0',
                        '-vf', f'scale={scale}:force_original_aspect_ratio=decrease,pad={scale}:(ow-iw)/2:(oh-ih)/2',
                        '-c:v', 'libx264',
                        '-preset', 'medium',
                        '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac',
                        '-b:a', '192k',
                        '-shortest',
                        '-movflags', '+faststart',
                        '-y',
                        output_path
                    ]
                else:
                    # Need fallback image
                    image_duration = audio_duration - video_duration
                    command = [
                        'ffmpeg',
                        '-i', media_file,
                        '-loop', '1',
                        '-t', str(image_duration),
                        '-i', fallback_image,
                        '-i', audio_file,
                        '-filter_complex',
                        f'[0:v]scale={scale}:force_original_aspect_ratio=decrease,pad={scale}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];'
                        f'[1:v]scale={scale}:force_original_aspect_ratio=decrease,pad={scale}:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];'
                        f'[v0][v1]concat=n=2:v=1:a=0[outv]',
                        '-map', '[outv]',
                        '-map', '2:a',
                        '-c:v', 'libx264',
                        '-preset', 'medium',
                        '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac',
                        '-b:a', '192k',
                        '-movflags', '+faststart',
                        '-y',
                        output_path
                    ]
            
            elif is_video:
                # Video file - loop to match audio
                command = [
                    'ffmpeg',
                    '-stream_loop', '-1',
                    '-i', media_file,
                    '-i', audio_file,
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                    '-vf', f'scale={scale}:force_original_aspect_ratio=decrease,pad={scale}:(ow-iw)/2:(oh-ih)/2',
                    '-c:v', 'libx264',
                    '-preset', 'medium',
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-shortest',
                    '-movflags', '+faststart',
                    '-y',
                    output_path
                ]
            
            else:
                # Image file - loop to match audio
                command = [
                    'ffmpeg',
                    '-loop', '1',
                    '-i', media_file,
                    '-i', audio_file,
                    '-vf', f'scale={scale}:force_original_aspect_ratio=decrease,pad={scale}:(ow-iw)/2:(oh-ih)/2',
                    '-c:v', 'libx264',
                    '-preset', 'medium',
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-shortest',
                    '-movflags', '+faststart',
                    '-y',
                    output_path
                ]
            
            # Run ffmpeg
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
            )
            
            print(f"\n✓ Video created: {output_path}")
            
            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                print(f"  File size: {size_mb:.2f} MB")
            
            # Update GUI
            self.root.after(0, lambda: messagebox.showinfo(
                "Video Created",
                f"YouTube video created successfully!\n\n{output_path}\n\nSize: {size_mb:.2f} MB"
            ))
            self.root.after(0, self.update_status_after_save)
            
        except subprocess.CalledProcessError as e:
            error_msg = f"ffmpeg error:\n{e.stderr}"
            print(f"\n✗ Error creating video: {error_msg}")
            self.root.after(0, lambda: messagebox.showerror("Video Creation Failed", error_msg))
            self.root.after(0, self.update_status_after_save)
        
        except Exception as e:
            error_msg = str(e)
            print(f"\n✗ Error: {error_msg}")
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
            self.root.after(0, self.update_status_after_save)
    
    def update_status_after_save(self):
        """Update status label after save"""
        if self.is_armed:
            self.status_label.config(text="ARMED - Monitoring Input", foreground='orange')
        elif self.auto_mode:
            self.status_label.config(text="Auto-Record Enabled - Waiting for audio...", foreground='black')
        else:
            self.status_label.config(text="Ready", foreground='black')
    
    def update_duration(self):
        """Update recording duration display"""
        if self.is_recording and self.recording_start_time:
            duration = (datetime.datetime.now() - self.recording_start_time).total_seconds()
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            self.duration_label.config(text=f"Duration: {minutes}:{seconds:02d}")
            self.root.after(100, self.update_duration)
        else:
            self.duration_label.config(text="Duration: 0:00")
    
    def setup_hotkeys(self):
        """Setup global hotkeys"""
        try:
            import keyboard
            keyboard.add_hotkey('f9', self.start_recording)
            keyboard.add_hotkey('f10', self.stop_recording)
            print("Hotkeys registered: F9 = Start, F10 = Stop")
        except ImportError:
            print("keyboard module not available, hotkeys disabled")
        except Exception as e:
            print(f"Hotkey setup error: {e}")
    
    def save_settings(self):
        """Save settings to file"""
        settings = {
            'output_folder': self.output_folder,
            'file_prefix': self.prefix_var.get(),
            'file_counter': self.counter_var.get(),
            'input_device_index': self.input_device_index,
            'output_device_index': self.output_device_index,
            'auto_mode': self.auto_mode,
            'silence_threshold_db': self.threshold_var.get(),
            'silence_duration': self.duration_var.get(),
            'rx11_auto_open': self.rx11_auto_open,
            'rx11_path': self.rx11_path,
            'monitor_volume': self.monitor_volume,
            'is_armed': self.is_armed,
            'trim_silence_start': self.trim_silence_start,
            'trim_silence_end': self.trim_silence_end,
            'trim_threshold_db': self.trim_threshold_db,
            'create_video': self.create_video,
            'video_folder': self.video_folder,
            'video_resolution': self.video_resolution
        }
        
        try:
            with open(os.path.expanduser('~/.audio_recorder_settings.json'), 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def load_settings(self):
        """Load settings from file"""
        try:
            with open(os.path.expanduser('~/.audio_recorder_settings.json'), 'r') as f:
                settings = json.load(f)
                self.output_folder = settings.get('output_folder', self.output_folder)
                self.file_prefix = settings.get('file_prefix', self.file_prefix)
                self.file_counter = settings.get('file_counter', self.file_counter)
                self.input_device_index = settings.get('input_device_index', self.input_device_index)
                self.output_device_index = settings.get('output_device_index', self.output_device_index)
                self.auto_mode = settings.get('auto_mode', self.auto_mode)
                self.silence_threshold_db = settings.get('silence_threshold_db', self.silence_threshold_db)
                self.silence_duration = settings.get('silence_duration', self.silence_duration)
                self.rx11_auto_open = settings.get('rx11_auto_open', self.rx11_auto_open)
                if settings.get('rx11_path'):
                    self.rx11_path = settings.get('rx11_path')
                self.monitor_volume = settings.get('monitor_volume', self.monitor_volume)
                self.trim_silence_start = settings.get('trim_silence_start', self.trim_silence_start)
                self.trim_silence_end = settings.get('trim_silence_end', self.trim_silence_end)
                self.trim_threshold_db = settings.get('trim_threshold_db', self.trim_threshold_db)
                self.create_video = settings.get('create_video', self.create_video)
                self.video_folder = settings.get('video_folder', self.video_folder)
                self.video_resolution = settings.get('video_resolution', self.video_resolution)
                # Don't restore armed state on startup for safety
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def on_closing(self):
        """Handle window closing"""
        print("Closing application...")
        
        # Save settings first
        try:
            self.save_settings()
        except Exception as e:
            print(f"Error saving settings: {e}")
        
        # Stop recording if active
        if self.is_recording:
            self.is_recording = False
        
        # Unbind mousewheel
        if hasattr(self, 'canvas'):
            try:
                self.canvas.unbind_all("<MouseWheel>")
            except:
                pass
        
        # Force close audio streams in a thread with timeout
        def force_close_streams():
            try:
                # Stop output monitoring
                if self.output_stream:
                    try:
                        self.output_stream.abort()  # Use abort instead of stop for faster shutdown
                        self.output_stream.close()
                    except:
                        pass
                
                # Stop input monitoring
                if self.input_stream:
                    try:
                        self.input_stream.abort()  # Use abort instead of stop for faster shutdown
                        self.input_stream.close()
                    except:
                        pass
                
                print("Streams closed")
            except Exception as e:
                print(f"Error closing streams: {e}")
        
        # Run in thread
        close_thread = threading.Thread(target=force_close_streams, daemon=True)
        close_thread.start()
        
        # Wait a maximum of 1 second for streams to close
        close_thread.join(timeout=1.0)
        
        # Destroy the window regardless
        print("Destroying window...")
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
        
        # Force exit
        import sys
        sys.exit(0)

def main():
    import signal
    
    root = tk.Tk()
    app = AudioRecorderRX11Armed(root)
    
    # Handle Ctrl+C and other signals
    def signal_handler(sig, frame):
        print("\nReceived shutdown signal, closing...")
        app.on_closing()
    
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    # Set close handler
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Run the app
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, closing...")
        app.on_closing()
    except Exception as e:
        print(f"Error in main loop: {e}")
        import traceback
        traceback.print_exc()
        app.on_closing()

if __name__ == '__main__':
    main()