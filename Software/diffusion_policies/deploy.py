#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deploy multimodal diffusion policy with existing hardware drivers.
DemoGen policy + RealSense/ESP cameras, UR robot, and ESP32 controller.
"""

# === Stdlib imports ===
import os
import time
import socket
import threading
import sys
from pathlib import Path
from typing import Optional, Dict
import argparse

# === Numeric libs ===
import numpy as np
import torch
import torch.nn as nn

# === CV libs ===
import cv2

# === Config libs ===
import hydra
from omegaconf import OmegaConf

# === DemoGen imports ===
# ensure local import path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from diffusion_policies.policy.diffusion_unet_hybrid_image_policy import (
    DiffusionUnetHybridImagePolicy,
)
from diffusion_policies.common.pytorch_util import dict_apply
from diffusion_policies.workspace.base_workspace import BaseWorkspace

# === Hardware drivers (original API) ===
try:
    import pyrealsense2 as rs
    REALSENSE_AVAILABLE = True
    print("✅ RealSense SDK loaded")
except ImportError:
    REALSENSE_AVAILABLE = False
    print("⚠️ RealSense SDK missing, using mock data")

try:
    import rtde_control
    import rtde_receive
    UR_RTDE_AVAILABLE = True
    print("✅ UR RTDE loaded")
except ImportError:
    UR_RTDE_AVAILABLE = False
    print("⚠️ UR RTDE missing, using mock robot")

# === Logging helper (original API) ===
class Logger:
    """
    Logger matching original script
    """
    
    def __init__(self, filename="deploy_multimodal_log.txt"):
        self.terminal = sys.stdout
        self.logfile = open(filename, "w", encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.logfile.write(message)
        self.flush()

    def flush(self):
        self.terminal.flush()
        self.logfile.flush()

# === Main deployer class ===
class MultiModalRobotDeployer:
    """
    Multimodal robot deployer using DemoGen policy and legacy drivers.
    """
    
    def __init__(self):
        """
        Init deployer: pick device, init components, connect hardware,
        load model, start threads.
        """
        self.running = True
        
        # === GPU check ===
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            print(f"🔥 Found {gpu_count} GPU(s)")
            self.device = torch.device("cuda:0")
            torch.cuda.set_device(0)
            print(f"🎯 Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            self.device = torch.device("cpu")
            print("⚠️ No GPU detected, using CPU")

        # === Component init ===
        # Camera components
        self.d435_pipeline = None
        self.d435_config = None
        self.esp_socket = None
        self.d435_frame = None
        self.esp_frame = None
        self.camera_lock = threading.Lock()
        
        # Robot components
        self.robot_control = None
        self.robot_receive = None
        self.esp32_socket = None
        
        # Model components
        self.policy = None
        self.normalizer = None
        
        # Control state
        self.current_joints = np.zeros(6)
        self.current_pose = np.zeros(6)
        self.current_state = np.zeros(14)  # state dim
        
        print("🎯 Initializing hardware components...")

        # === Hardware connections ===
        self._initialize_d435_camera()
        self._initialize_esp_camera()
        self._initialize_robot()
        self._initialize_esp32_controller()
        
        print("🚀 Hardware ready, starting system...")

    def _initialize_d435_camera(self):
        """Init D435 camera (matches original API)"""
        print("🔌 Init D435 camera...")
        try:
            if not REALSENSE_AVAILABLE:
                print("   ⚠️ RealSense unavailable, using mock D435")
                self.d435_pipeline = None
                return
                
            # create pipeline
            self.d435_pipeline = rs.pipeline()
            self.d435_config = rs.config()
            
            # configure depth and color streams
            self.d435_config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
            self.d435_config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            
            # start pipeline
            profile = self.d435_pipeline.start(self.d435_config)
            
            # set camera params (match training data)
            self._setup_d435_camera_parameters()
            
            print("   ✅ D435 camera ready")
            
        except Exception as e:
            print(f"   ❌ D435 init failed: {e}")
            self.d435_pipeline = None

    def _setup_d435_camera_parameters(self):
        """Set D435 params (match training capture)"""
        if not hasattr(self, 'color_sensor') or self.color_sensor is None:
            print("   ⚠️ Color sensor unavailable, skip params")
            return
            
        try:
            # fetch color sensor
            profile = self.d435_pipeline.get_active_profile()
            color_profile = rs.video_stream_profile(profile.get_stream(rs.stream.color))
            color_intrinsics = color_profile.get_intrinsics()
            self.color_sensor = profile.get_device().first_color_sensor()
            
            # set camera params (match training)
            self.color_sensor.set_option(rs.option.enable_auto_exposure, 1)
            self.color_sensor.set_option(rs.option.enable_auto_white_balance, 1)
            print("   ✅ D435 params set")
            
        except Exception as e:
            print(f"   ⚠️ Param set failed: {e}")

    def _initialize_esp_camera(self):
        """Init ESP camera connection"""
        print("🔌 Init ESP camera link...")
        try:
            self.esp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.esp_socket.settimeout(10)
            self.esp_socket.connect(('192.168.10.53', 8000))
            print("   ✅ ESP camera connected")
            
        except Exception as e:
            print(f"   ❌ ESP camera connect failed: {e}")
            self.esp_socket = None

    def _initialize_robot(self):
        """Init robot connection"""
        print("🔌 Init robot link...")
        try:
            if not UR_RTDE_AVAILABLE:
                print("   ⚠️ UR RTDE unavailable, using mock robot")
                self.robot_control = None
                self.robot_receive = None
                return
                
            # connect control and receive interfaces
            self.robot_control = rtde_control.RTDEControlInterface("192.168.10.21")
            self.robot_receive = rtde_receive.RTDEReceiveInterface("192.168.10.21")
            
            # fetch current state
            self.current_joints = np.array(self.robot_receive.getActualQ())
            self.current_pose = np.array(self.robot_receive.getActualTCPPose())
            
            print("   ✅ Robot connected")
            print(f"   📍 Joints: {self.current_joints}")
            print(f"   📍 TCP pose: {self.current_pose}")
            
        except Exception as e:
            print(f"   ❌ Robot connect failed: {e}")
            self.robot_control = None
            self.robot_receive = None

    def _initialize_esp32_controller(self):
        """Init ESP32 controller"""
        print("🔌 Init ESP32 controller...")
        try:
            self.esp32_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.esp32_socket.settimeout(5)
            self.esp32_socket.connect(('192.168.10.22', 8080))
            print("   ✅ ESP32 controller connected")
            
        except Exception as e:
            print(f"   ❌ ESP32 controller connect failed: {e}")
            self.esp32_socket = None

    def load_model(self, checkpoint_path: str):
        """
        Load trained multimodal diffusion policy.
        
        Args:
            checkpoint_path: checkpoint path
        """
        print("🤖 Loading multimodal diffusion policy...")
        try:
            # load checkpoint
            checkpoint = torch.load(checkpoint_path, map_location=self.device)
            
            # extract model state
            if 'model' in checkpoint:
                model_state = checkpoint['model']
            elif 'state_dict' in checkpoint:
                model_state = checkpoint['state_dict']
            else:
                model_state = checkpoint
                
            # build policy (params should match training config)
            shape_meta = {
                'obs': {
                    'd435_image': {'shape': [3, 224, 224], 'type': 'rgb'},
                    'esp_a_image': {'shape': [3, 224, 224], 'type': 'rgb'}, 
                    'esp_b_image': {'shape': [3, 224, 224], 'type': 'rgb'},
                    'esp_b_tactile': {'shape': [3, 224, 224], 'type': 'rgb'},
                    'state': {'shape': [14], 'type': 'low_dim'},
                    's_prev': {'shape': [1], 'type': 'low_dim'}
                },
                'action': {'shape': [14]}  # 14-dim action incl. s_prev
            }
            
            # create noise scheduler
            from diffusers.schedulers.scheduling_ddpm import DDPMScheduler
            noise_scheduler = DDPMScheduler(
                num_train_timesteps=1000,
                beta_start=0.0001,
                beta_end=0.02,
                beta_schedule="squaredcos_cap_v2",
                variance_type="fixed_small",
                clip_sample=True,
                prediction_type="epsilon"
            )
            
            # build policy
            self.policy = DiffusionUnetHybridImagePolicy(
                shape_meta=shape_meta,
                noise_scheduler=noise_scheduler,
                horizon=16,
                obs_as_global_cond=True,
                crop_shape=None,  # no crop; inputs already 224x224
                diffusion_step_embed_dim=256,
                down_dims=[256, 512, 1024],
                kernel_size=5,
                n_groups=8,
                cond_predict_scale=True,
                n_action_steps=8,
                n_obs_steps=2,
                num_inference_steps=50
            )
            
            # load weights
            self.policy.load_state_dict(model_state, strict=False)
            self.policy.to(self.device)
            self.policy.eval()
            
            # load normalizer
            if 'normalizer' in checkpoint:
                self.policy.set_normalizer(checkpoint['normalizer'])
                
            print("   ✅ Policy loaded")
            print(f"   📊 Params: {sum(p.numel() for p in self.policy.parameters())/1e6:.1f}M")
            
        except Exception as e:
            print(f"   ❌ Policy load failed: {e}")
            raise e

    def start_camera_threads(self):
        """Start camera threads"""
        print("📷 Starting camera threads...")
        
        # start D435 thread
        if self.d435_pipeline is not None:
            d435_thread = threading.Thread(target=self._d435_camera_loop, daemon=True)
            d435_thread.start()
            print("   ✅ D435 thread running")
        else:
            print("   ⚠️ D435 unavailable, skip thread")
            
        # start ESP thread
        if self.esp_socket is not None:
            esp_thread = threading.Thread(target=self._esp_camera_loop, daemon=True)
            esp_thread.start()
            print("   ✅ ESP thread running")
        else:
            print("   ⚠️ ESP unavailable, skip thread")
            
        # warm up
        time.sleep(2)
        print("📷 Cameras warmed up")

    def _d435_camera_loop(self):
        """D435 capture loop"""
        print("📷 D435 capture loop started...")
        
        while self.running:
            try:
                frames = self.d435_pipeline.wait_for_frames(timeout_ms=1000)
                color_frame = frames.get_color_frame()
                
                if color_frame:
                    # convert to numpy
                    color_image = np.asanyarray(color_frame.get_data())
                    
                    # update shared frame
                    with self.camera_lock:
                        self.d435_frame = color_image.copy()
                        
            except Exception as e:
                if self.running:
                    print(f"D435 capture error: {e}")
                time.sleep(0.1)

    def _esp_camera_loop(self):
        """ESP capture loop"""  
        print("📷 ESP capture loop started...")
        picture_len = 0
        
        while self.running:
            try:
                if picture_len == 0:
                    # receive image size
                    len_data = self.esp_socket.recv(4)
                    if len(len_data) == 4:
                        picture_len = int.from_bytes(len_data, byteorder='little')
                    else:
                        continue
                        
                # receive image data
                picture_data = b''
                while len(picture_data) < picture_len:
                    chunk = self.esp_socket.recv(picture_len - len(picture_data))
                    if not chunk:
                        break
                    picture_data += chunk
                    
                if len(picture_data) == picture_len:
                    # decode image
                    nparr = np.frombuffer(picture_data, np.uint8)
                    esp_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if esp_image is not None:
                        # update shared frame
                        with self.camera_lock:
                            self.esp_frame = esp_image.copy()
                            
                    picture_len = 0
                    
            except Exception as e:
                if self.running:
                    print(f"ESP capture error: {e}")
                time.sleep(0.1)

    def _get_d435_image(self) -> Optional[np.ndarray]:
        """Get D435 image"""
        with self.camera_lock:
            if self.d435_frame is not None:
                return self.d435_frame.copy()
            else:
                # return mock image
                return np.zeros((480, 640, 3), dtype=np.uint8)

    def _get_esp_image(self) -> Optional[np.ndarray]:
        """Get ESP raw image"""
        with self.camera_lock:
            if self.esp_frame is not None:
                return self.esp_frame.copy()
            else:
                # return mock image
                return np.zeros((480, 640, 3), dtype=np.uint8)

    def _extract_esp_regions(self, esp_image: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Extract ESP regions (must match training)
        
        Args:
            esp_image: ESP raw image
            
        Returns:
            dict with region images
        """
        if esp_image is None:
            # return mock image
            dummy_img = np.zeros((224, 224, 3), dtype=np.uint8)
            return {
                'esp_a': dummy_img,
                'esp_b_vis': dummy_img, 
                'esp_b_tac': dummy_img
            }
            
        # TODO: match exact training-time region logic
        h, w = esp_image.shape[:2]
        
        # simple split into three regions
        region_h = h // 2
        region_w = w // 2
        
        esp_a = cv2.resize(esp_image[:region_h, :region_w], (224, 224))
        esp_b_vis = cv2.resize(esp_image[:region_h, region_w:], (224, 224))  
        esp_b_tac = cv2.resize(esp_image[region_h:, :], (224, 224))
        
        return {
            'esp_a': esp_a,
            'esp_b_vis': esp_b_vis,
            'esp_b_tac': esp_b_tac
        }

    def _get_current_state(self) -> np.ndarray:
        """
        Get current robot state
        
        Returns:
            14-dim state [6 joint + 6 pose + 2 extra]
        """
        try:
            if self.robot_receive is not None:
                joints = np.array(self.robot_receive.getActualQ())
                pose = np.array(self.robot_receive.getActualTCPPose())
                # build 14-dim vector
                state = np.concatenate([joints, pose, [0.0, 0.0]])  # extra dims adjustable
                return state.astype(np.float32)
            else:
                # return mock state
                return np.zeros(14, dtype=np.float32)
                
        except Exception as e:
            print(f"Get robot state failed: {e}")
            return np.zeros(14, dtype=np.float32)

    def _prepare_observation(self) -> Dict[str, torch.Tensor]:
        """
        Build model observation tensors.
        
        Returns:
            dict of observations matching training format
        """
        # get D435 image
        d435_image = self._get_d435_image()
        if d435_image is not None:
            d435_image = cv2.resize(d435_image, (224, 224))
            # BGR to RGB
            d435_image = cv2.cvtColor(d435_image, cv2.COLOR_BGR2RGB)
        else:
            d435_image = np.zeros((224, 224, 3), dtype=np.uint8)
            
        # get ESP image and regions
        esp_image = self._get_esp_image()
        esp_regions = self._extract_esp_regions(esp_image)
        
        # get current state
        current_state = self._get_current_state()
        
        # previous LED state
        s_prev = np.array([0.0], dtype=np.float32)  # init 0, adjust if needed
        
        # to torch with time/batch dims
        # shape: (B=1, T=2, C, H, W) images, (B=1, T=2, D) low_dim
        obs_dict = {
            'd435_image': torch.from_numpy(d435_image).permute(2, 0, 1).float().unsqueeze(0).unsqueeze(0),  # (1, 1, 3, 224, 224)
            'esp_a_image': torch.from_numpy(esp_regions['esp_a']).permute(2, 0, 1).float().unsqueeze(0).unsqueeze(0),
            'esp_b_image': torch.from_numpy(esp_regions['esp_b_vis']).permute(2, 0, 1).float().unsqueeze(0).unsqueeze(0),
            'esp_b_tactile': torch.from_numpy(esp_regions['esp_b_tac']).permute(2, 0, 1).float().unsqueeze(0).unsqueeze(0),
            'state': torch.from_numpy(current_state).float().unsqueeze(0).unsqueeze(0),  # (1, 1, 14)
            's_prev': torch.from_numpy(s_prev).float().unsqueeze(0).unsqueeze(0)  # (1, 1, 1)
        }
        
        # duplicate frame for simple 2-step history
        for key in obs_dict:
            if key.endswith('_image'):
                # (1, 1, 3, 224, 224) -> (1, 2, 3, 224, 224)
                obs_dict[key] = torch.cat([obs_dict[key], obs_dict[key]], dim=1)
            else:
                # low-dim: (1, 1, D) -> (1, 2, D) 
                obs_dict[key] = torch.cat([obs_dict[key], obs_dict[key]], dim=1)
                
        # move to device
        obs_dict = {k: v.to(self.device) for k, v in obs_dict.items()}
        
        return obs_dict

    def predict_action(self) -> Optional[np.ndarray]:
        """
        Predict action with policy.
        
        Returns:
            Predicted action vector (13) + s_prev signal
        """
        if self.policy is None:
            print("⚠️ Policy not loaded")
            return None
            
        try:
            with torch.no_grad():
                # prepare input
                obs_dict = self._prepare_observation()
                
                # predict
                result = self.policy.predict_action(obs_dict)
                action_pred = result['action']  # (1, Ta, 14)
                
                # take first step
                action = action_pred[0, 0].cpu().numpy()  # (14,)
                
                return action
                
        except Exception as e:
            print(f"❌ Action prediction failed: {e}")
            return None

    def execute_action(self, action: np.ndarray, s_prev: float = 0.0):
        """
        Execute action.
        
        Args:
            action: 14-dim vector (joint deltas + LED control)
            s_prev: LED control signal
        """
        if action is None or len(action) != 14:
            print("⚠️ Invalid action vector")
            return
            
        try:
            # robot motion
            if self.robot_control is not None:
                # assume first 6 dims are joint deltas, rest other signals
                joint_deltas = action[:6]
                current_joints = np.array(self.robot_receive.getActualQ())
                target_joints = current_joints + joint_deltas * 0.1  # scale factor tunable
                
                # move joints
                self.robot_control.moveJ(target_joints.tolist(), 0.5, 0.3)
                print(f"🤖 Moving joints: {target_joints}")
                
            # ESP32 control
            if self.esp32_socket is not None and abs(s_prev) > 0.1:
                control_signal = int(s_prev > 0.5)  # 0/1 signal
                message = f"LED:{control_signal}\\n"
                self.esp32_socket.send(message.encode())
                print(f"💡 LED control: {control_signal}")
                
        except Exception as e:
            print(f"❌ Action exec failed: {e}")

    def run_deployment_loop(self):
        """
        Run deployment loop.
        """
        print("🚀 Deployment loop started...")
        
        try:
            while self.running:
                # predict action
                action = self.predict_action()
                
                if action is not None:
                    print(f"🎯 Predicted: {action[:6]} (joints) + {action[6:]} (other)")
                    
                    # execute (s_prev could come from elsewhere)
                    s_prev = 0.0
                    self.execute_action(action, s_prev)
                    
                else:
                    print("⚠️ Prediction failed, skip")
                    
                # loop rate control
                time.sleep(0.1)  # 10 Hz
                
        except KeyboardInterrupt:
            print("\\n🛑 Stop signal, shutting down...")
            self.running = False
        except Exception as e:
            print(f"❌ Deployment loop error: {e}")
            self.running = False

    def cleanup(self):
        """Cleanup resources"""
        print("🧹 Cleaning up...")
        
        self.running = False
        
        # stop D435
        if self.d435_pipeline is not None:
            try:
                self.d435_pipeline.stop()
                print("   ✅ D435 stopped")
            except:
                pass
                
        # close ESP cam
        if self.esp_socket is not None:
            try:
                self.esp_socket.close()
                print("   ✅ ESP camera closed")
            except:
                pass
                
        # close robot
        if self.robot_control is not None:
            try:
                self.robot_control.disconnect()
                print("   ✅ Robot disconnected")
            except:
                pass
                
        # close ESP32
        if self.esp32_socket is not None:
            try:
                self.esp32_socket.close()  
                print("   ✅ ESP32 closed")
            except:
                pass
                
        print("🎉 Cleanup done")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Deploy multimodal diffusion policy')
    parser.add_argument('--checkpoint', required=True, help='model checkpoint path')
    parser.add_argument('--log', default='deploy_multimodal_log.txt', help='log filename')
    
    args = parser.parse_args()
    
    # set logger
    sys.stdout = Logger(args.log)
    
    print("="*80)
    print("🚀 Multimodal robot diffusion deploy")
    print("   DemoGen + legacy hardware drivers")
    print("="*80)
    
    deployer = None
    try:
        # create deployer
        deployer = MultiModalRobotDeployer()
        
        # load model
        deployer.load_model(args.checkpoint)
        
        # start camera threads
        deployer.start_camera_threads()
        
        # run loop
        deployer.run_deployment_loop()
        
    except Exception as e:
        print(f"❌ Deploy error: {e}")
        
    finally:
        if deployer is not None:
            deployer.cleanup()
            
    print("👋 Deploy system exited")

if __name__ == "__main__":
    main()
