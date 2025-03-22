Features
Text-to-audio transmission using GGWave

Real-time volume meter to check microphone input level

Dark-themed UI with an intuitive layout

Automatic listening (no need to enable manually)

Half-duplex system to prevent self-echoing

Usage
Type a message and press Send – it will be transmitted as sound.

The receiver decodes the message automatically.

The volume meter helps ensure the microphone input is high enough for proper decoding.

requirements
Python 3.10
pip install numpy matplotlib pyaudio ggwave

Building an .exe
pyinstaller --onefile --windowed --icon=icon.ico ggwave-chat.py
