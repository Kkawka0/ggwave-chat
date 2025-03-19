import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import pyaudio
import ggwave
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class GGWaveChatApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("GGWave Chat + Modern Volume Meter")
        self.geometry("900x600")
        self.resizable(False, False)

        # === GGWave Chat Audio (unchanged) ===
        self.chat_sample_rate = 48000
        self.chat_chunk_size = 2048

        # === Flags & chat thread ===
        self.listening = False
        self.listen_thread = None
        self.is_sending = False  # half-duplex

        # === Volume meter audio settings ===
        self.vol_rate = 44100
        self.vol_chunk = 1024
        self.vol_format = pyaudio.paInt16
        self.vol_max = 32768  # max for int16

        # === GGWave init (for decoding) ===
        self.ggwave_instance = ggwave.init()
        # If you want to hide logs:
        # ggwave.disableLog()

        # === PyAudio main ===
        self.pa = pyaudio.PyAudio()

        # Stream for chat decoding
        try:
            self.stream_in = self.pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.chat_sample_rate,
                input=True,
                frames_per_buffer=self.chat_chunk_size
            )
        except Exception as e:
            messagebox.showerror("Microphone error", f"Could not open microphone.\n{e}")
            self.stream_in = None

        # Stream for chat playback
        try:
            self.stream_out = self.pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.chat_sample_rate,
                output=True
            )
        except Exception as e:
            messagebox.showerror("Speaker error", f"Could not open speaker output.\n{e}")
            self.stream_out = None

        # === Separate stream for volume meter ===
        try:
            self.volume_stream_in = self.pa.open(
                format=self.vol_format,
                channels=1,
                rate=self.vol_rate,
                input=True,
                frames_per_buffer=self.vol_chunk
            )
        except Exception as e:
            messagebox.showerror("Volume meter error", f"Could not open second mic stream.\n{e}")
            self.volume_stream_in = None

        # Build the dark UI
        self._build_gui()

    def _build_gui(self):
        """Dark UI with your half-duplex chat + an embedded modern volume meter."""
        style = ttk.Style(self)
        style.theme_use("clam")

        # Dark theme colors
        bg_dark = "#2b2b2b"
        bg_lighter = "#3c3f41"
        fg_text = "#ffffff"

        style.configure(".", background=bg_dark, foreground=fg_text, font=("Segoe UI", 10))
        style.configure("TFrame", background=bg_dark)
        style.configure("TLabel", background=bg_dark, foreground=fg_text)
        style.configure("TButton", background=bg_lighter, foreground=fg_text, relief="flat", padding=6)
        style.map("TButton", background=[("active", "#5f6061")])
        style.configure(
            "TEntry",
            fieldbackground=bg_lighter,
            foreground=fg_text,
            insertwidth=1,
            insertcolor=fg_text,
            insertborderwidth=1
        )

        self.configure(bg=bg_dark)

        # === Chat UI ===
        chat_frame = ttk.Frame(self, padding=10)
        chat_frame.pack(side="top", fill="x")

        self.chat_history = scrolledtext.ScrolledText(
            chat_frame,
            width=80,
            height=15,
            state="disabled",
            bg=bg_lighter,
            fg=fg_text,
            relief="flat",
            insertbackground=fg_text
        )
        self.chat_history.pack(pady=(0,10), fill="x", expand=False)

        entry_frame = ttk.Frame(chat_frame)
        entry_frame.pack(fill="x")

        self.entry_message = ttk.Entry(entry_frame)
        self.entry_message.pack(side="left", fill="x", expand=True)

        btn_send = ttk.Button(entry_frame, text="Send", command=self.send_message)
        btn_send.pack(side="left", padx=5)

        bottom_frame = ttk.Frame(chat_frame)
        bottom_frame.pack(fill="x", pady=5)

        self.mic_button = ttk.Button(bottom_frame, text="...", command=self.toggle_listening)
        self.mic_button.pack(side="left", padx=5)

        btn_quit = ttk.Button(bottom_frame, text="Quit", command=self.on_quit)
        btn_quit.pack(side="right", padx=5)

        # === Volume Meter UI below the chat ===
        meter_frame = ttk.Frame(self, padding=10)
        meter_frame.pack(side="bottom", fill="both", expand=True)

        self.fig, self.ax = plt.subplots(figsize=(6, 2))
        # Dark figure background
        self.fig.patch.set_facecolor(bg_dark)
        self.ax.set_facecolor(bg_dark)
        self.ax.set_ylim(0,1)
        self.ax.set_xlim(0,1)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for spine in self.ax.spines.values():
            spine.set_color("#ffffff")

        # Single bar
        self.bar = self.ax.bar(0.5, 0, width=0.4, color="#4CAF50", edgecolor="#ffffff", linewidth=2)
        self.canvas = FigureCanvasTkAgg(self.fig, master=meter_frame)
        self.canvas.get_tk_widget().pack(pady=5)

        self.vol_label = ttk.Label(meter_frame, text="Volume: 0%", foreground=fg_text, background=bg_dark, font=("Arial", 12, "bold"))
        self.vol_label.pack()

        # Start volume updates + listening
        self.start_listening()
        self._update_mic_button()
        self._update_volume_meter()

    def _update_volume_meter(self):
        """Updates the volume meter from the second stream, without messing up chat decoding."""
        if not self.volume_stream_in:
            return

        try:
            data = self.volume_stream_in.read(self.vol_chunk, exception_on_overflow=False)
            samples = np.frombuffer(data, dtype=np.int16)
            peak = np.max(np.abs(samples)) if samples.size > 0 else 0
            volume = peak / self.vol_max
            volume = max(0, min(volume, 1))

            # Color transitions
            if volume > 0.7:
                self.bar[0].set_color("#FF0000")   # Red
            elif volume > 0.3:
                self.bar[0].set_color("#FFA500")   # Orange
            else:
                self.bar[0].set_color("#4CAF50")   # Green

            # Update height + label
            self.bar[0].set_height(volume)
            pct = int(volume * 100)
            self.vol_label.config(text=f"Volume: {pct}%")

            self.canvas.draw()
        except Exception as e:
            print("[DEBUG] Volume meter error:", e)

        # Keep updating ~ every 50ms
        self.after(50, self._update_volume_meter)

    # === Chat Decoding Logic ===
    def toggle_listening(self):
        """Toggle the listening state for chat decoding."""
        if self.listening:
            self.stop_listening()
        else:
            self.start_listening()
        self._update_mic_button()

    def _update_mic_button(self):
        if self.listening:
            self.mic_button.config(text="Stop Listening")
        else:
            self.mic_button.config(text="Start Listening")

    def start_listening(self):
        """Start the half-duplex chat listening thread."""
        if not self.stream_in:
            messagebox.showerror("Microphone error", "Cannot listen – no input stream.")
            return

        if not self.listening:
            self.listening = True
            self.listen_thread = threading.Thread(target=self._listening_loop, daemon=True)
            self.listen_thread.start()
            self._update_mic_button()

    def stop_listening(self):
        if self.listening:
            self.listening = False
            if self.listen_thread:
                self.listen_thread.join(timeout=1)
            self.listen_thread = None
            self._update_mic_button()

    def _listening_loop(self):
        """Your original half-duplex decoding: no error lines if decode fails."""
        decoder_buffer = b""
        while self.listening:
            try:
                if self.is_sending:
                    time.sleep(0.01)
                    continue

                data = self.stream_in.read(self.chat_chunk_size, exception_on_overflow=False)
                decoder_buffer += data

                msg = ggwave.decode(self.ggwave_instance, decoder_buffer)
                if msg:
                    decoded_text = msg.decode("utf-8", errors="replace")
                    self._append_chat("Other", decoded_text)
                    decoder_buffer = b""
                else:
                    # If decode fails, do nothing, no chat error
                    decoder_buffer = b""
            except Exception as e:
                print("[DEBUG] Listening loop error:", e)
                def show_err():
                    messagebox.showerror("Listening error", f"Listening thread stopped.\n{e}")
                    self.listening = False
                    self._update_mic_button()
                self.after(0, show_err)
                break

            time.sleep(0.01)

        print("[DEBUG] Listening loop ended.")

    def send_message(self):
        """
        Send the typed message. Then do the weird wait sequence:
          0.1s -> start_listening
          0.2s -> stop_listening
          0.1s -> start_listening
        """
        text = self.entry_message.get().strip()
        self.entry_message.delete(0, tk.END)
        if not text:
            return

        self._append_chat("You", text)

        was_listening = self.listening
        if was_listening:
            self.stop_listening()

        if self.stream_out:
            try:
                self.is_sending = True
                audio_frames = ggwave.encode(text)
                self.stream_out.write(audio_frames)
            finally:
                self.is_sending = False
        else:
            messagebox.showwarning("Speaker error", "Cannot play audio – no output device.")

        # The weird wait sequence
        time.sleep(0.1)
        self.start_listening()
        time.sleep(0.2)
        self.stop_listening()
        time.sleep(0.1)
        self.start_listening()

        # if not was_listening:
        #     self.stop_listening()

    def _append_chat(self, user, message):
        """Always create a new line for each chat message."""
        self.chat_history.config(state="normal")
        self.chat_history.insert("end", f"{user}: {message}\n")
        self.chat_history.config(state="disabled")
        self.chat_history.see("end")

    def on_quit(self):
        """Safely close everything."""
        if messagebox.askyesno("Exit", "Are you sure you want to quit?"):
            self.stop_listening()

            if self.stream_in:
                self.stream_in.stop_stream()
                self.stream_in.close()
            if self.stream_out:
                self.stream_out.stop_stream()
                self.stream_out.close()
            if self.volume_stream_in:
                self.volume_stream_in.stop_stream()
                self.volume_stream_in.close()

            self.pa.terminate()
            ggwave.free(self.ggwave_instance)
            self.destroy()

def main():
    app = GGWaveChatApp()
    app.mainloop()

if __name__ == "__main__":
    main()
