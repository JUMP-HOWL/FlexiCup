# FlexiCup Hardware

This directory contains all hardware-related files for the FlexiCup system, including physical fabrication designs and embedded firmware.

## Directory Structure

- **Fabrication/**: Physical hardware design files
  - **CAD/**: 3D mechanical designs (STEP format) and BOM
  - **PCB/**: Electronic circuit schematics, layout, BOM, and Gerber files
- **Firmware/**: ESP32-S3 embedded firmware
  - **ESPCAM/**: Camera control, LED switching, and wireless communication

## Overview

The FlexiCup hardware implements a modular layered architecture:

1. **Mechanical System**: Modular suction cup with reconfigurable bottom housings supporting vacuum (sustained-contact adhesion) and Bernoulli (contactless lifting) modes. Four bottom configurations (I–IV) accommodate different membrane diameters and actuation principles.
2. **Electronics**: ESP32-S3 controller with OV5640 camera (180° fisheye), WS2812 LED arrays, wireless charging (3.7V 300mAh LiPo), streaming 640×480 @ 30 Hz over Wi-Fi.
3. **Pneumatic System**: Vacuum pump (750 W, 140 L/min, −90 kPa max) and air compressor (800 W, 65 L/min, 0.8 MPa) for the respective modes. Solenoid valves controlled wirelessly by the onboard microcontroller.

## Key Performance

- **Normal Force**: 41.5 N (mean, at −80 kPa)
- **Shear Force**: 8.34 N (mean)
- **Sensing**: Dual-zone vision-tactile (central switchable + peripheral continuous)
- **Runtime**: ~30 minutes wireless operation

## Getting Started

### Fabrication
1. Review CAD models in `Fabrication/CAD/`
2. Fabricate PCB using files in `Fabrication/PCB/`
3. Source components according to BOM files
4. Assemble following the CAD designs

### Firmware
1. Install ESP-IDF framework (v5.0.2)
2. Navigate to `Firmware/ESPCAM/`
3. Configure Wi-Fi settings and build
4. Flash to ESP32-S3 device

For detailed fabrication and assembly instructions, see `TUTORIAL.pdf` in the repository root.
