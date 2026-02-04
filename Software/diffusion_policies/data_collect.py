import os
import sys
import time
import numpy as np
import cv2
import socket
import threading
import pandas as pd
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List
import rtde_control
import rtde_receive
import keyboard
import json

os.environ['OPENCV_VIDEOIO_PRIORITY_MSMF'] = '0'
os.environ['QT_LOGGING_RULES'] = '*.debug=false;qt.qpa.*=false'
cv2.setLogLevel(0)

try:
    import pyrealsense2 as rs
    REALSENSE_AVAILABLE = True
except ImportError:
    REALSENSE_AVAILABLE = False

@dataclass
class TCPConfig:
    initial_pose: List[float] = field(default_factory=lambda: [0.345, 0.166, 0.148, 2.901, -1.2, 0.003])
    return_pose: List[float] = field(default_factory=lambda: [0.345, 0.166, 0.148, 2.901, -1.2, 0.003])
    move_speed: float = 0.5
    move_accel: float = 0.5

@dataclass
class CameraInfo:
    ip: str
    port: int
    is_active: bool = True
    frame: Optional[bytes] = None
    frame_lock: threading.Lock = threading.Lock()
    picture_len: int = 0
    picture_data: bytes = b''

@dataclass
class D435CameraInfo:
    is_active: bool = False
    rgb_frame: Optional[np.ndarray] = None
    frame_lock: threading.Lock = threading.Lock()
    pipeline: Optional[object] = None
    config: Optional[object] = None

@dataclass
class TrialMarker:
    trial_id: int
    start_time: float
    end_time: Optional[float] = None
    start_frame: int = 0
    end_frame: Optional[int] = None
    task_success: Optional[int] = None

ROBOT_IP = "192.168.10.99"
CAMERA_IP = "192.168.10.53"
CAMERA_PORT = 8000
ESP32_IP = "192.168.10.4"
ESP32_PORT = 3333
ROOT_DIR = "dataset_continuous"

class DataCollector:
    def __init__(self):
        self.session_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_dir = os.path.join(ROOT_DIR, f"session_{self.session_timestamp}")
        os.makedirs(self.session_dir, exist_ok=True)
        
        self.tcp_config = TCPConfig()
        self.sampling_rate = 30.0
        
        self.robot_control = rtde_control.RTDEControlInterface(ROBOT_IP)
        self.robot_receive = rtde_receive.RTDEReceiveInterface(ROBOT_IP)
        
        self.camera = None
        self.camera_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.camera_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.camera_sock.bind(('0.0.0.0', CAMERA_PORT))
        
        self.d435_camera = D435CameraInfo()
        self._init_d435()
        
        self.tcp_sock = None
        try:
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.connect((ESP32_IP, ESP32_PORT))
        except:
            pass
        
        self.running = True
        self.collecting = False
        self.valve_state = False
        self.is_tactile_mode = False
        
        self.frame_count = 0
        self.data_list = []
        self.trial_markers = []
        self.current_trial = None
        self.video_writer = None
        
        self._start_threads()

    def _init_d435(self):
        if not REALSENSE_AVAILABLE:
            return
        try:
            self.d435_camera.pipeline = rs.pipeline()
            self.d435_camera.config = rs.config()
            self.d435_camera.config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            self.d435_camera.pipeline.start(self.d435_camera.config)
            self.d435_camera.is_active = True
        except:
            pass

    def _start_threads(self):
        threading.Thread(target=self._camera_loop, daemon=True).start()
        threading.Thread(target=self._d435_loop, daemon=True).start()
        threading.Thread(target=self._data_loop, daemon=True).start()
        threading.Thread(target=self._display_loop, daemon=True).start()
        threading.Thread(target=self._control_loop, daemon=True).start()

    def _camera_loop(self):
        while self.running:
            try:
                data, addr = self.camera_sock.recvfrom(65535)
                self._handle_camera_data(data, addr)
            except:
                time.sleep(0.01)

    def _handle_camera_data(self, data, addr):
        if self.camera is None:
            self.camera = CameraInfo(ip=addr[0], port=addr[1])
        
        try:
            if data.startswith(b'\xff\xd8'):
                with self.camera.frame_lock:
                    self.camera.frame = data
        except:
            pass

    def _d435_loop(self):
        if not self.d435_camera.is_active:
            return
        while self.running:
            try:
                frames = self.d435_camera.pipeline.wait_for_frames(timeout_ms=100)
                color_frame = frames.get_color_frame()
                if color_frame:
                    rgb_image = np.asanyarray(color_frame.get_data())
                    with self.d435_camera.frame_lock:
                        self.d435_camera.rgb_frame = rgb_image.copy()
            except:
                time.sleep(0.01)

    def _data_loop(self):
        last_time = time.time()
        interval = 1.0 / self.sampling_rate
        
        while self.running:
            current_time = time.time()
            if self.collecting and (current_time - last_time >= interval):
                tcp_pose = self.robot_receive.getActualTCPPose()
                joint_angles = self.robot_receive.getActualQ()
                
                img = self._capture_image()
                d435_rgb = self._capture_d435()
                
                data_item = {
                    'timestamp': current_time,
                    'frame_idx': self.frame_count,
                    'tcp_pose': tcp_pose,
                    'joint_angles': joint_angles,
                    'valve_state': self.valve_state,
                    'is_tactile_mode': self.is_tactile_mode,
                    'trial_id': self.current_trial.trial_id if self.current_trial else -1
                }
                
                if img is not None:
                    if self.video_writer is not None:
                        self.video_writer.write(img)
                    self.data_list.append(data_item)
                    self.frame_count += 1
                
                last_time = current_time
            time.sleep(0.001)

    def _capture_image(self):
        if not self.camera or not self.camera.frame:
            return None
        try:
            with self.camera.frame_lock:
                nparr = np.frombuffer(self.camera.frame, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return frame
        except:
            return None

    def _capture_d435(self):
        if not self.d435_camera.is_active:
            return None
        try:
            with self.d435_camera.frame_lock:
                if self.d435_camera.rgb_frame is not None:
                    return self.d435_camera.rgb_frame.copy()
        except:
            pass
        return None

    def _display_loop(self):
        while self.running:
            try:
                img = self._capture_image()
                if img is not None:
                    cv2.putText(img, f"Collecting: {'ON' if self.collecting else 'OFF'}", 
                              (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(img, f"Trial: {self.current_trial.trial_id if self.current_trial else 'None'}", 
                              (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(img, f"Frames: {len(self.data_list)}", 
                              (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.imshow('Camera', img)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False
                    break
            except:
                time.sleep(0.01)

    def _control_loop(self):
        STEP = 0.02
        last_switch = {'space': 0, 'v': 0, 'r': 0, 'j': 0}
        
        while self.running:
            try:
                current_time = time.time()
                
                # Movement controls
                if keyboard.is_pressed('up'):
                    self._move_relative(dx=-STEP)
                if keyboard.is_pressed('down'):
                    self._move_relative(dx=STEP)
                if keyboard.is_pressed('left'):
                    self._move_relative(dy=-STEP)
                if keyboard.is_pressed('right'):
                    self._move_relative(dy=STEP)
                if keyboard.is_pressed('w'):
                    self._move_relative(dz=STEP)
                if keyboard.is_pressed('s'):
                    self._move_relative(dz=-STEP/10)
                
                # Control switches
                if keyboard.is_pressed('space') and current_time - last_switch['space'] > 0.5:
                    if not self.collecting:
                        self._start_trial()
                    else:
                        self._end_trial()
                    last_switch['space'] = current_time
                
                if keyboard.is_pressed('v') and current_time - last_switch['v'] > 0.2:
                    self._toggle_valve()
                    last_switch['v'] = current_time
                
                if keyboard.is_pressed('r') and current_time - last_switch['r'] > 0.2:
                    self._return_home()
                    last_switch['r'] = current_time
                
                if keyboard.is_pressed('j') and current_time - last_switch['j'] > 0.2:
                    self.is_tactile_mode = not self.is_tactile_mode
                    last_switch['j'] = current_time
                
                time.sleep(0.01)
            except:
                time.sleep(0.1)

    def _move_tcp(self, pose):
        try:
            self.robot_control.moveL(pose, speed=self.tcp_config.move_speed, 
                                   acceleration=self.tcp_config.move_accel)
            return True
        except:
            return False

    def _move_relative(self, dx=0, dy=0, dz=0):
        try:
            current_pose = self.robot_receive.getActualTCPPose()
            new_pose = current_pose.copy()
            new_pose[0] += dx
            new_pose[1] += dy
            new_pose[2] += dz
            self.robot_control.moveL(new_pose, speed=0.1, acceleration=0.1)
        except:
            pass

    def _toggle_valve(self):
        if self.tcp_sock is None:
            return
        try:
            command = "OFF" if self.valve_state else "ON"
            self.tcp_sock.sendall(command.encode())
            self.valve_state = not self.valve_state
        except:
            pass

    def _return_home(self):
        self._move_tcp(self.tcp_config.return_pose)
        if self.valve_state:
            self._toggle_valve()

    def _start_trial(self):
        if self.current_trial is not None:
            return
        
        trial_id = len(self.trial_markers)
        self.current_trial = TrialMarker(
            trial_id=trial_id,
            start_time=time.time(),
            start_frame=self.frame_count
        )
        
        if self.video_writer is None:
            self._init_video_writer()
        
        self.collecting = True
        print(f"Started trial {trial_id}")

    def _end_trial(self):
        if self.current_trial is None:
            return
        
        self.collecting = False
        self.current_trial.end_time = time.time()
        self.current_trial.end_frame = self.frame_count
        self.current_trial.task_success = 1
        
        self.trial_markers.append(self.current_trial)
        print(f"Ended trial {self.current_trial.trial_id}")
        
        self._save_data()
        self.current_trial = None

    def _init_video_writer(self):
        if self.camera is None or self.camera.frame is None:
            return
        try:
            img = self._capture_image()
            if img is not None:
                h, w = img.shape[:2]
                video_path = os.path.join(self.session_dir, "video.mp4")
                self.video_writer = cv2.VideoWriter(
                    video_path, cv2.VideoWriter_fourcc(*'mp4v'), self.sampling_rate, (w, h)
                )
        except:
            pass

    def _save_data(self):
        if not self.data_list:
            return
        try:
            expanded_data = []
            for item in self.data_list:
                row = {
                    'timestamp': item['timestamp'],
                    'frame_idx': item['frame_idx'],
                    'valve_state': item['valve_state'],
                    'is_tactile_mode': item['is_tactile_mode'],
                    'trial_id': item['trial_id']
                }
                
                for i, pos in enumerate(item['tcp_pose']):
                    row[f'tcp_pose_{i}'] = pos
                for i, angle in enumerate(item['joint_angles']):
                    row[f'joint_angle_{i}'] = angle
                
                expanded_data.append(row)
            
            df = pd.DataFrame(expanded_data)
            csv_path = os.path.join(self.session_dir, "data.csv")
            df.to_csv(csv_path, index=False)
            
            markers_data = []
            for marker in self.trial_markers:
                markers_data.append({
                    'trial_id': marker.trial_id,
                    'start_time': marker.start_time,
                    'end_time': marker.end_time,
                    'start_frame': marker.start_frame,
                    'end_frame': marker.end_frame,
                    'task_success': marker.task_success
                })
            
            markers_path = os.path.join(self.session_dir, "markers.json")
            with open(markers_path, 'w') as f:
                json.dump(markers_data, f, indent=2)
                
        except Exception as e:
            print(f"Save failed: {e}")

    def run(self):
        print("Data collection started")
        print("Controls:")
        print("  SPACE: Start/end trial")
        print("  Arrow keys: Move TCP in X-Y plane")
        print("  W/S: Move TCP up/down")
        print("  V: Toggle valve")
        print("  R: Return home")
        print("  J: Toggle tactile/visual mode")
        print("  Q: Quit (in display window)")
        
        self._move_tcp(self.tcp_config.initial_pose)
        
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self.running = False
        
        if self.current_trial is not None:
            self._end_trial()
        
        if self.video_writer is not None:
            self.video_writer.release()
        
        if self.d435_camera.is_active and self.d435_camera.pipeline is not None:
            try:
                self.d435_camera.pipeline.stop()
            except:
                pass
        
        if hasattr(self, 'camera_sock'):
            self.camera_sock.close()
        if self.tcp_sock is not None:
            self.tcp_sock.close()
        if hasattr(self, 'robot_control'):
            self.robot_control.disconnect()
        if hasattr(self, 'robot_receive'):
            self.robot_receive.disconnect()
        
        cv2.destroyAllWindows()
        print("Data collection stopped")

def main():
    collector = DataCollector()
    try:
        collector.run()
    except KeyboardInterrupt:
        pass
    finally:
        collector.stop()

if __name__ == "__main__":
    main()