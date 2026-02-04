# FlexiCup Hardware

This directory contains all hardware-related files for the FlexiCup system, including both physical fabrication designs and embedded firmware code.

## Directory Structure

- **Fabrication/**: Physical hardware design files
  - **CAD/**: 3D mechanical designs and assemblies
  - **PCB/**: Electronic circuit designs and manufacturing files
- **Firmware/**: Embedded software for ESP32S3 controller
  - **ESPCAM/**: Camera control and wireless communication firmware

## Overview

The FlexiCup hardware consists of:

1. **Mechanical System**: Modular suction cup with dual-mode operation (vacuum/Bernoulli)
2. **Electronics**: ESP32S3-based controller with camera, LED control, and wireless capabilities
3. **Firmware**: Real-time embedded software for sensor control and data streaming

## Getting Started

### Fabrication
1. Review CAD models in `Fabrication/CAD/`
2. Fabricate PCB using files in `Fabrication/PCB/`
3. Source components according to BOM files
4. Assemble following the CAD designs

### Firmware
1. Install ESP-IDF development framework
2. Navigate to `Firmware/ESPCAM/`
3. Configure and build the firmware
4. Flash to ESP32S3 device

For detailed instructions, see the README files in each subdirectory.