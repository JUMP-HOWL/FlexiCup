# FlexiCup Software

This directory contains the high-level software components for the FlexiCup system, focusing on machine learning algorithms and control policies.

## Directory Structure

- **diffusion_policies/**: Complete diffusion policy implementation
  - Data collection pipeline
  - Training scripts and configurations
  - Evaluation and testing tools
  - Real-time deployment code

## Overview

The FlexiCup software stack provides:

1. **Multimodal Learning**: Integration of vision and tactile sensing data
2. **Diffusion Policies**: Advanced policy learning for contact-aware manipulation
3. **Real-time Control**: Low-latency inference for robot control
4. **Data Pipeline**: Automated data collection and preprocessing

## Key Features

- **Contact-Aware Manipulation**: Specialized algorithms for suction-based grasping
- **Dual-Zone Sensing**: Support for peripheral vision and central tactile feedback
- **Modular Architecture**: Easy integration with different robot platforms
- **Comprehensive Evaluation**: Built-in metrics and visualization tools

## Getting Started

### Environment Setup
```bash
cd diffusion_policies
conda env create -f environment.yml
conda activate flexicup
```

### Basic Usage
1. **Data Collection**: Use `data_collect.py` to gather demonstration data
2. **Training**: Run `train.py` with appropriate configuration files
3. **Evaluation**: Test trained models using `eval.py`
4. **Deployment**: Deploy to real robot using `deploy.py`

### Configuration
All algorithms can be configured through YAML files in the `configs/` directory. Key parameters include:
- Network architecture settings
- Training hyperparameters
- Data preprocessing options
- Deployment configurations

For detailed documentation, see the README in the `diffusion_policies/` subdirectory.