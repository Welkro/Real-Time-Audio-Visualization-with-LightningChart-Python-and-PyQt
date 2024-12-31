import sys
import numpy as np
import time
import pygame
from pygame import sndarray
from PyQt5.QtCore import QUrl, QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QFileDialog, QHBoxLayout, QSlider
from PyQt5.QtGui import QIcon
from PyQt5.QtWebEngineWidgets import QWebEngineView
import lightningchart as lc

# Set LightningChart Python license key
lc.set_license('LICENSE_KEY')

# Configuration constants
CHUNK_DURATION_MS = 25  # Process audio in 25 ms chunks
SAMPLE_RATE = 44100  # Standard audio sample rate

# Thread for audio playback and visualization updates
class AudioPlaybackThread(QThread):
    audio_chunk_signal = pyqtSignal(np.ndarray)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.running = True
        self.paused = False
        self.volume = 0.5  # Default volume to 50%
        self.sound = None  # Placeholder for the sound object

    def run(self):
        pygame.mixer.init()
        self.sound = pygame.mixer.Sound(self.file_path)
        self.sound.play()
        self.sound.set_volume(self.volume)  # Set initial volume based on the slider value

        audio_data = sndarray.array(self.sound).astype(np.float32)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)  # Convert to mono if stereo
        chunk_samples = int((CHUNK_DURATION_MS / 1000) * SAMPLE_RATE)

        for i in range(0, len(audio_data), chunk_samples):
            if not self.running:
                break
            while self.paused:
                time.sleep(0.1)
                if not self.running:
                    return
            chunk = audio_data[i:i + chunk_samples]
            if len(chunk) > 0:
                self.audio_chunk_signal.emit(chunk)
            time.sleep(CHUNK_DURATION_MS / 1000.0)

    def set_volume(self, volume):
        self.volume = volume
        if self.sound:  # Update volume only if the sound object is initialized
            self.sound.set_volume(self.volume)

    def stop(self):
        self.running = False
        self.paused = False  # Ensure paused state is cleared
        pygame.mixer.stop()

    def pause(self):
        if self.running:
            self.paused = True
            pygame.mixer.pause()

    def resume(self):
        if self.running and self.paused:
            self.paused = False
            pygame.mixer.unpause()


# Custom QWebEngineView to handle drag-and-drop
class CustomWebEngineView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(False)

    def dragEnterEvent(self, event):
        self.parent().dragEnterEvent(event)

    def dropEvent(self, event):
        self.parent().dropEvent(event)


class App(QMainWindow):
    def __init__(self, url, update_waveform, update_frequency, reset_visualization, audio_thread=None):
        super(App, self).__init__()
        self.setWindowTitle("LightningChart Python Audio Visualizer")
        self.setGeometry(100, 100, 800, 600)

        # Set the custom window icon
        self.setWindowIcon(QIcon("icons/LC-PythonLogo.png"))

        self.setAcceptDrops(True)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.web_view = CustomWebEngineView()
        self.web_view.setUrl(QUrl(url))

        self.loaded_file_label = QLabel("Loaded File: None")
        self.loaded_file_label.setWordWrap(True)
        self.loaded_file_label.setFixedHeight(20)

        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        layout.addWidget(self.web_view, stretch=8)
        layout.addWidget(self.loaded_file_label, stretch=1)

        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignLeft)  # Align all elements to the left

        # Create and add buttons
        self.load_button = QPushButton("Load File")
        self.load_button.setFixedWidth(100)

        self.play_pause_button = QPushButton()  # Single Play/Pause button
        self.play_pause_button.setFixedWidth(100)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setFixedWidth(100)

        # Set initial play icon
        self.play_icon = QIcon("icons/play-button.png")
        self.pause_icon = QIcon("icons/pause-button.png")
        self.play_pause_button.setIcon(self.play_icon)

        # Add volume slider
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.setFixedWidth(150)
        self.volume_slider.setToolTip("Adjust Volume")

        # Add widgets to the layout
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.play_pause_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.volume_slider)

        # Add the button layout to the main layout
        layout.addLayout(button_layout)

        self.audio_thread = audio_thread
        self.update_waveform = update_waveform
        self.update_frequency = update_frequency
        self.reset_visualization = reset_visualization

        # Connect buttons and slider
        self.load_button.clicked.connect(self.load_file)
        self.play_pause_button.clicked.connect(self.toggle_play_pause)  # Connect to toggle function
        self.stop_button.clicked.connect(self.stop_audio)
        self.volume_slider.valueChanged.connect(self.update_volume)

        # Set fixed sizes for buttons
        self.load_button.setFixedWidth(100)
        self.play_pause_button.setFixedWidth(100)
        self.stop_button.setFixedWidth(100)

        self.is_playing = False  # Track play/pause state


    def update_volume(self):
        if self.audio_thread:
            volume = self.volume_slider.value() / 100  # Convert slider value to [0.0, 1.0]
            self.audio_thread.set_volume(volume)

    def closeEvent(self, event):
        # Cleanup on application exit
        if self.audio_thread and self.audio_thread.isRunning():
            self.audio_thread.stop()
            self.audio_thread.wait()
        event.accept()

    def dragEnterEvent(self, event):
        # Handle drag-and-drop events
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        # Stop and clear the current thread if it exists
        if self.audio_thread:
            if self.audio_thread.isRunning():
                self.audio_thread.stop()
                self.audio_thread.wait()
            self.audio_thread = None  # Clear the thread

        # Process the dropped file
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith(('.mp3', '.wav')):
                self.loaded_file_label.setText(f"Loaded File: {file_path}")
                self.audio_thread = AudioPlaybackThread(file_path)
            else:
                self.loaded_file_label.setText("Error: Unsupported file type.")

    def load_file(self):
        # Stop and clear the current thread if it exists
        if self.audio_thread:
            if self.audio_thread.isRunning():
                self.audio_thread.stop()
                self.audio_thread.wait()
            self.audio_thread = None  # Clear the thread

        # Load the new file
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Audio File", "", "Audio Files (*.mp3 *.wav)")
        if file_path:
            self.loaded_file_label.setText(f"Loaded File: {file_path}")
            self.audio_thread = AudioPlaybackThread(file_path)
            # Apply the current volume from the slider
            volume = self.volume_slider.value() / 100  # Convert slider value to [0.0, 1.0]
            self.audio_thread.set_volume(volume)

    def toggle_play_pause(self):
        if self.audio_thread:
            if self.is_playing:
                # Pause playback
                self.audio_thread.pause()
                self.play_pause_button.setIcon(self.play_icon)  # Switch to play icon
            else:
                # Resume or start playback
                if not self.audio_thread.isRunning():
                    self.reset_visualization()
                    self.audio_thread = AudioPlaybackThread(self.loaded_file_label.text().split(": ")[1])
                    self.audio_thread.audio_chunk_signal.connect(self.update_waveform)
                    self.audio_thread.audio_chunk_signal.connect(self.update_frequency)
                    # Set the current volume before starting playback
                    volume = self.volume_slider.value() / 100  # Convert slider value to [0.0, 1.0]
                    self.audio_thread.set_volume(volume)
                    self.audio_thread.start()
                else:
                    self.audio_thread.resume()
                self.play_pause_button.setIcon(self.pause_icon)  # Switch to pause icon
            self.is_playing = not self.is_playing


    def stop_audio(self):
        if self.audio_thread and self.audio_thread.isRunning():
            self.audio_thread.stop()
            self.audio_thread.wait()
            self.reset_visualization()
            self.play_pause_button.setIcon(self.play_icon)  # Reset to play icon
            self.is_playing = False


# Main function to set up the dashboard and application
def main():
    # Create dashboard with two charts
    dashboard = lc.Dashboard(columns=1, rows=2, theme=lc.Themes.Dark)

    # Waveform chart setup
    waveform_chart = dashboard.ChartXY(column_index=0, row_index=1)
    waveform_chart.set_title("Audio Waveform")
    x_axis = waveform_chart.get_default_x_axis() 
    x_axis.set_scroll_strategy("progressive").set_interval(0, 5)
    x_axis.set_tick_strategy("Time")
    y_axis = waveform_chart.get_default_y_axis()
    y_axis.set_tick_strategy("Empty")
    waveform_series = waveform_chart.add_line_series(data_pattern='ProgressiveX')
    waveform_series.set_max_sample_count(300_000, automatic=True)
    waveform_series.set_cursor_enabled(False)
    waveform_series.set_mouse_interactions(False)

    # Frequency chart setup
    frequency_chart = dashboard.ChartXY(column_index=0, row_index=0)
    frequency_chart.set_title("Frequency Visualization")
    default_x_axis = frequency_chart.get_default_x_axis()
    default_x_axis.dispose()

    freq_x_axis = frequency_chart.add_x_axis(axis_type='logarithmic')
    freq_x_axis.set_title("Hz (Logarithmic Scale)")
    freq_y_axis = frequency_chart.get_default_y_axis()
    freq_y_axis.set_tick_strategy("Empty")
    freq_y_axis.set_interval(0, 1)

    frequency_series = frequency_chart.add_area_series(data_pattern='ProgressiveX')
    frequency_series.set_max_sample_count(1024, automatic=True)
    frequency_series.set_cursor_enabled(False)
    frequency_series.set_mouse_interactions(False)

    # Apply color palette to frequency chart
    def apply_frequency_palette(series):
        palette_steps = [
            {"value": 20, "color": lc.Color(0, 255, 0, 128)},     # Green with 50% transparency
            {"value": 200, "color": lc.Color(255, 255, 0, 128)},  # Yellow with 50% transparency
            {"value": 1000, "color": lc.Color(255, 165, 0, 128)}, # Orange with 50% transparency
            {"value": 5000, "color": lc.Color(255, 0, 0, 128)},   # Red with 50% transparency
            {"value": 20000, "color": lc.Color(128, 0, 128, 128)} # Purple with 50% transparency
        ]
        series.set_palette_area_coloring(
            steps=palette_steps, look_up_property="x", interpolate=True, percentage_values=False
        )
    apply_frequency_palette(frequency_series)

    # Track time for waveform updates
    current_time = [0.0]

    def update_waveform(audio_data):
        nonlocal current_time
        chunk_duration = len(audio_data) / SAMPLE_RATE
        x_values = np.linspace(current_time[0] * 1000, (current_time[0] + chunk_duration) * 1000, len(audio_data))
        current_time[0] += chunk_duration
        points = [{"x": float(x), "y": float(y)} for x, y in zip(x_values, audio_data)]
        waveform_series.add(points)
        x_axis.set_interval(current_time[0] * 1000 - 5000, current_time[0] * 1000)

    def update_frequency(audio_data):
        fft_result = np.fft.rfft(audio_data)
        fft_magnitude = np.abs(fft_result)
        fft_frequencies = np.fft.rfftfreq(len(audio_data), d=1 / SAMPLE_RATE)
        fft_frequencies, fft_magnitude = fft_frequencies[1:], fft_magnitude[1:]
        frequency_points = [{"x": freq, "y": mag} for freq, mag in zip(fft_frequencies, fft_magnitude)]
        frequency_series.clear()
        frequency_series.add(frequency_points)

    def reset_visualization():
        current_time[0] = 0.0
        waveform_series.clear()
        frequency_series.clear()

    # Start the application
    url = QUrl(dashboard.open_live_server())
    app = QApplication(sys.argv)
    dashboard_app = App(url, update_waveform, update_frequency, reset_visualization)
    dashboard_app.show()
    app.exec_()


if __name__ == "__main__":
    main()