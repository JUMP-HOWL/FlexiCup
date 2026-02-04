# Diffusion Policies for Robotic Manipulation

A diffusion model-based framework for robotic manipulation policy learning, supporting multimodal perception (vision + tactile) and real-time robot control.

## Project Structure

```
diffusion_policies/
├── diffusion_policies/           # Core code package
│   ├── common/                   # Common utilities
│   ├── config/                   # Configuration files
│   │   ├── task/                # Task configurations
│   │   │   ├── slope_task.yaml  # Slope task configuration
│   │   │   └── valve_task.yaml  # Valve task configuration
│   │   ├── slope_policy.yaml    # Slope task policy configuration
│   │   └── valve_policy.yaml    # Valve task policy configuration
│   ├── dataset/                  # Dataset processing
│   │   ├── valve_task_dataset.py # Valve task dataset
│   │   └── ...                  # Other dataset implementations
│   ├── env/                      # Environment interfaces
│   ├── env_runner/              # Environment runners
│   ├── gym_util/                # Gym environment utilities
│   ├── model_dp3/               # DP3 model implementation
│   ├── model_dp_umi/            # DP-UMI model implementation
│   ├── model_idp3/              # IDP3 model implementation
│   ├── policy/                  # Policy implementations
│   │   ├── diffusion_unet_hybrid_image_policy.py  # Main policy for valve/slope tasks
│   │   └── ...                  # Other policy implementations
│   ├── workspace/               # Training workspaces
│   └── workspace_quad/          # Quadruped robot workspace
├── data_collect.py              # Data collection script
├── train.py                     # Training script
├── deploy.py                    # Deployment script
├── eval.py                      # Evaluation script
├── setup.py                     # Installation configuration
├── environment.yml              # Conda environment configuration
└── README.md                    # Project documentation
```

## Environment Setup

```bash
# Create and activate conda environment
conda env create -f environment.yml
conda activate diffusion_policies

# Install the project package
pip install -e .
```

## Hardware Requirements

### Required Hardware
- **Robot**: Universal Robots (UR5/UR10, etc.) with RTDE interface support
- **Cameras**: Intel RealSense D435 + ESP32 camera modules
- **Controller**: ESP32 development board (for valve/LED control)
- **Computing Device**: CUDA-capable GPU (RTX 3080 or higher recommended)

### Network Configuration
- Robot IP: `192.168.10.99`
- ESP32 Camera IP: `192.168.10.53:8000`
- ESP32 Controller IP: `192.168.10.4:3333`

## Data Collection

### Start Data Collection

```bash
python data_collect.py
```

### Control Instructions

| Key | Function |
|-----|----------|
| `SPACE` | Start/end trial recording |
| `↑↓←→` | Move TCP in X-Y plane |
| `W/S` | Move TCP up/down |
| `V` | Toggle valve state |
| `R` | Return to home position |
| `J` | Toggle tactile/visual mode |
| `Q` | Quit program (in display window) |

### Data Format

Collected data is saved in `dataset_continuous/session_YYYYMMDD_HHMMSS/` directory:

- `data.csv`: Robot states and sensor data
- `video.mp4`: Synchronized video recording
- `markers.json`: Trial marker information

Data contains the following fields:
- `tcp_pose_0-5`: TCP pose (position + orientation)
- `joint_angle_0-5`: Joint angles
- `valve_state`: Valve state
- `is_tactile_mode`: Tactile mode flag
- `trial_id`: Trial ID

## Model Training

### Configure Training Parameters

Edit configuration files `diffusion_policies/config/slope_policy.yaml` or `valve_policy.yaml`:

```yaml
# Data path
zarr_path: /path/to/your/dataset.zarr

# Training parameters
training:
  num_epochs: 3000
  batch_size: 16
  lr: 1.0e-4
  device: cuda:0

# Model parameters
policy:
  horizon: 48
  n_obs_steps: 8
  n_action_steps: 24
  enable_esp_cross_attention: true
```

### Start Training

```bash
# Train slope task
python train.py --config-name=slope_policy

# Train valve task
python train.py --config-name=valve_policy

# Specify GPU
CUDA_VISIBLE_DEVICES=0 python train.py --config-name=slope_policy
```

### Training Monitoring

- Training logs saved in `data/outputs/` directory
- Supports Weights & Biases monitoring
- Automatic best model checkpoint saving

## Model Deployment

### Start Deployment

```bash
python deploy.py --checkpoint /path/to/model.ckpt
```

### Deployment Features

- **Multimodal Perception**: Fuses D435 depth camera and ESP32 camera data
- **Real-time Inference**: Supports 10Hz control frequency
- **Safety Mechanisms**: Anomaly detection and emergency stop
- **State Monitoring**: Real-time display of robot state and prediction results

### Deployment Configuration

The deployment script automatically:
1. Connects all hardware devices
2. Loads the trained model
3. Starts camera capture threads
4. Begins real-time control loop

## Model Evaluation

```bash
# Evaluate model performance
python eval.py --checkpoint /path/to/model.ckpt --config-name=slope_policy

# Generate evaluation report
python eval.py --checkpoint /path/to/model.ckpt --output-dir ./eval_results
```

## Supported Tasks

### 1. Slope Task
- **Objective**: Robot performs precise operations on sloped surfaces
- **Sensors**: D435 camera + state feedback
- **Configuration**: `slope_policy.yaml`
- **Key Features**: 
  - Cross-attention mechanism for ESP camera fusion
  - 48-step action horizon with 8 observation steps
  - Specialized for surface manipulation tasks

### 2. Valve Task
- **Objective**: Robot operates valve switches
- **Sensors**: Multi-camera vision + tactile feedback
- **Configuration**: `valve_policy.yaml`
- **Key Features**:
  - Multimodal sensor fusion (visual + tactile)
  - ESP32-based tactile sensing integration
  - Real-time valve state control

## Model Architecture

### Core Features
- **Diffusion Policy**: DDPM-based action generation
- **Multimodal Fusion**: Vision + tactile + state information
- **Cross Attention**: Feature interaction between ESP cameras
- **Temporal Modeling**: Supports historical observations and future action prediction

### Network Structure
- **Observation Encoder**: ResNet/ViT visual encoders
- **Diffusion Network**: 1D U-Net conditional generation network
- **Action Decoder**: Fully connected output layers

## Development Guide

### Adding New Tasks

1. Create task configuration file `config/task/new_task.yaml`
2. Implement dataset class `dataset/new_task_dataset.py`
3. Create policy configuration `config/new_task_policy.yaml`
4. Run training and evaluation

### Custom Models

1. Inherit from `BaseImagePolicy` or `BasePointCloudPolicy`
2. Implement `predict_action()` method
3. Specify new model class in configuration file

### Hardware Integration

1. Implement hardware driver interfaces
2. Modify hardware initialization code in `deploy.py`
3. Update data collection scripts

## Troubleshooting

### Common Issues

1. **CUDA Out of Memory**
   ```bash
   # Reduce batch size
   python train.py dataloader.batch_size=8
   ```

2. **Camera Connection Failed**
   ```bash
   # Check device connection
   lsusb | grep Intel
   # Restart RealSense service
   sudo systemctl restart realsense
   ```

3. **Robot Connection Timeout**
   ```bash
   # Check network connection
   ping 192.168.10.99
   # Check RTDE service status
   ```

4. **Slow Training Convergence**
   - Check data quality and annotations
   - Adjust learning rate and batch size
   - Use pre-trained weights

### Log Analysis

- Training logs: `data/outputs/*/train.log`
- Deployment logs: `deploy_multimodal_log.txt`
- Error logs: Check terminal output and exception stack traces

## Performance Optimization

### Training Optimization
- Use mixed precision training: `training.use_amp=true`
- Data parallelism: `CUDA_VISIBLE_DEVICES=0,1 python train.py`
- Gradient accumulation: `training.gradient_accumulate_every=2`

### Inference Optimization
- Model quantization: Use TensorRT or ONNX
- Batch inference: Process multiple observations simultaneously
- Asynchronous processing: Separate perception and control threads
