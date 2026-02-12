# FlexiCup Software

This directory contains the high-level software components for the FlexiCup system, focusing on diffusion-based policy learning for contact-aware manipulation.

## Directory Structure

- **diffusion_policies/**: Complete diffusion policy implementation
  - Data collection pipeline (keyboard teleoperation)
  - Training scripts and Hydra configurations
  - Evaluation and deployment code

## Overview

The FlexiCup software stack provides:

1. **Multimodal Observation Encoding**: Workspace camera (D435), dual-zone suction camera (peripheral + central), and robot state processed through parallel ResNet-18 encoders
2. **Multi-Head Attention Fusion**: 8-head, 512-d attention coordinating central and peripheral features during vision-tactile transitions
3. **Diffusion Policy**: DDPM-based action generation with action chunking (8-step history, 48-step horizon), outputting robot joints, illumination switching, and valve state
4. **Training**: AdamW optimizer with cosine annealing, 500 epochs, batch size 16 on RTX 4090

## Experimental Results

- **Inclined Transport**: 73.3% success rate (150 demos, 30 eval trials)
- **Orange Extraction**: 66.7% success rate (100 demos, 30 eval trials)
- **Multi-head attention improvement**: +13% over baseline without attention
- **BC-RNN baseline**: 0% success on both tasks

## Getting Started

### Environment Setup
```bash
cd diffusion_policies
conda env create -f environment.yml
conda activate diffusion_policies
pip install -e .
```

### Basic Usage
1. **Data Collection**: Use `data_collect.py` to gather demonstration data via kinesthetic teaching (30 Hz, downsampled to 10 Hz)
2. **Training**: Run `train.py` with appropriate configuration files
3. **Evaluation**: Test trained models using `eval.py`
4. **Deployment**: Deploy to real robot using `deploy.py`

For detailed documentation, see the README in the `diffusion_policies/` subdirectory.
