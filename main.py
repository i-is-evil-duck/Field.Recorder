from flask import Flask, render_template, request, jsonify, send_from_directory, Response, abort
import os
import cv2
import random
import string
import threading
import time
from datetime import datetime
import tkinter as tk
from werkzeug.serving import make_server

app = Flask(__name__)

# Base directory to save the clips
CLIP_DIR = 'clips'

if not os.path.exists(CLIP_DIR):
    os.makedirs(CLIP_DIR)

# Function to generate a random alpha-numeric directory name
def generate_directory_name():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

# Function to generate the current date and time string for filename
def generate_timestamp():
    return datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

# Function to handle recording
def record_video(duration, folder_name, client_id):
    # Create a directory for this recording
    clip_path = os.path.join(CLIP_DIR, folder_name)
    os.makedirs(clip_path, exist_ok=True)
    
    # Set the file path
    filename = generate_timestamp() + '.mp4'
    filepath = os.path.join(clip_path, filename)

    cap = cv2.VideoCapture(0)  # camera selection
    
    width, height = 1920, 1080
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    
    fps = 30.0
    cap.set(cv2.CAP_PROP_FPS, fps)

    # codec x264 or avc1
    fourcc = cv2.VideoWriter_fourcc(*'avc1')
    out = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

    end_time = time.time() + duration  # End time(seconds)

    while time.time() < end_time:
        ret, frame = cap.read()
        if ret:
            out.write(frame)
        else:
            break

    cap.release()
    out.release()

    # Notify recording done+give link
    link = f'/clip/{folder_name}'
    app.clients[client_id]['recordings'].append(link)
    app.clients[client_id]['notify'] = link


# Generator function to stream the camera feed
def generate_feed():
    cap = cv2.VideoCapture(0)
    
    width, height = 1920, 1080
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    
    fps = 30.0
    cap.set(cv2.CAP_PROP_FPS, fps)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Encode frame as JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/live-feed')
def live_feed():
    return render_template('live_feed.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_feed(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/start-recording', methods=['POST'])
def start_recording():
    duration = int(request.json.get('duration'))
    client_id = request.json.get('client_id')
    folder_name = generate_directory_name()

    if client_id not in app.clients:
        app.clients[client_id] = {'recordings': [], 'notify': None}

    threading.Thread(target=record_video, args=(duration, folder_name, client_id)).start()
    return jsonify({"status": "Recording started", "folder": folder_name})

@app.route('/check-notification', methods=['POST'])
def check_notification():
    client_id = request.json.get('client_id')
    notify = app.clients.get(client_id, {}).get('notify')
    if notify:
        app.clients[client_id]['notify'] = None
        return jsonify({"status": "done", "link": notify})
    return jsonify({"status": "pending"})

@app.route('/my-recordings', methods=['POST'])
def my_recordings():
    client_id = request.json.get('client_id')
    recordings = app.clients.get(client_id, {}).get('recordings', [])
    return jsonify({"recordings": recordings})

@app.route('/clip/<clip_id>')
def clip_page(clip_id):
    clip_path = os.path.join(CLIP_DIR, clip_id)
    
    if not os.path.exists(clip_path):
        return abort(404)

    # Find the most recent clip in the directory
    clips = sorted(os.listdir(clip_path), reverse=True)
    if not clips:
        return abort(404)

    clip_file = clips[0]
    return render_template('clip.html', clip_file=clip_file, clip_id=clip_id)

@app.route('/clip_file/<clip_id>/<clip_file>')
def serve_clip(clip_id, clip_file):
    clip_path = os.path.join(CLIP_DIR, clip_id)
    if not os.path.exists(clip_path):
        return abort(404)
    return send_from_directory(clip_path, clip_file, mimetype='video/mp4')

# Function to display the "Starting Server" window and update to "Server is Running"
def show_status_window(shutdown_event):
    root = tk.Tk()
    root.title("Server Status")
    root.geometry("300x100")
    
    status_label = tk.Label(root, text="Starting Server", padx=20, pady=20)
    status_label.pack()
    
    # Function to update the status message
    def update_status_message(message):
        status_label.config(text=message)
        root.update_idletasks()

    # Update to "Server is Running" after 500ms
    root.after(500, lambda: update_status_message("Server is Running"))
    
    # Close event handler to set shutdown event and stop server
    def on_closing():
        shutdown_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

def run_flask_app(shutdown_event):
    def run():
        app.clients = {}
        # Run the Flask app
        server = make_server('0.0.0.0', 5000, app)
        threading.Thread(target=server.serve_forever).start()
        
        # Wait for shutdown event
        shutdown_event.wait()
        
        # Shutdown the server
        server.shutdown()
        server.server_close()

    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run)
    flask_thread.start()
    flask_thread.join()

if __name__ == '__main__':
    shutdown_event = threading.Event()

    # Start the GUI window
    window_thread = threading.Thread(target=show_status_window, args=(shutdown_event,))
    window_thread.start()
    
    # Start the Flask server
    run_flask_app(shutdown_event)

    # Ensure both threads complete
    window_thread.join()
