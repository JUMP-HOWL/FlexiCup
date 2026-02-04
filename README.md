# FlexiCup: Wireless Multimodal Suction Cup with Dual-Zone Vision-Tactile Sensing

This repository contains the complete project files for FlexiCup, including fabrication designs, firmware code, and project documentation.

## 📁 Repository Structure

```
FlexiCup/
├── Fabrication/           # Fabrication design files
│   ├── CAD/              # 3D CAD models and mechanical designs
│   │   ├── FlexiCup_Vacuum.STEP          # Vacuum mode assembly (109MB)
│   │   ├── FlexiCup_Bernoulli.STEP       # Bernoulli mode assembly (109MB)
│   │   ├── suction cup bottom I.STEP     # Bottom configuration I
│   │   ├── suction cup bottom II.STEP    # Bottom configuration II
│   │   ├── suction cup bottom III.STEP   # Bottom configuration III
│   │   ├── suction cup bottom IV.STEP    # Bottom configuration IV
│   │   ├── suction cup top.STEP          # Top assembly
│   │   └── FlexiCup_CAD_BOM.xlsx        # CAD Bill of Materials
│   │
│   └── PCB/              # PCB design files
│       ├── FlexiCup_Schematic.pdf        # Circuit schematic
│       ├── FlexiCup_PCB.pdf              # PCB layout
│       ├── FlexiCup_PCB_BOM.xlsx         # PCB Bill of Materials
│       └── Gerber_PCB.zip                # Manufacturing files
│
├── Firmware/              # Firmware source code
│   └── ESPCAM/           # ESP32S3 camera firmware
│       ├── main/         # Main application code
│       │   ├── inc/      # Header files
│       │   │   ├── camera.h
│       │   │   ├── httpServer.h
│       │   │   ├── led.h
│       │   │   └── wifiConnect.h
│       │   ├── src/      # Source files
│       │   │   ├── camera.c
│       │   │   ├── httpServer.c
│       │   │   ├── led.c
│       │   │   └── wifiConnect.c
│       │   ├── html/     # Web interface
│       │   └── main.c    # Main entry point
│       │
│       ├── managed_components/  # ESP32-Camera library
│       ├── CMakeLists.txt
│       ├── sdkconfig
│       └── README.md
│
├── PDF/                   # Documentation
│   └── paper.pdf         # Research paper
│
├── static/               # Website assets
│   ├── css/             # Stylesheets
│   ├── js/              # JavaScript files
│   ├── images/          # Images and figures
│   └── video/           # Video demonstrations
│       ├── optimized/   # Optimized videos for web (12.2MB total)
│       └── websitevideo/# Original high-quality videos
│
└── index.html           # Project website

```

## 🔧 Fabrication Files

### CAD Models (STEP Format)
All mechanical designs are provided in STEP format for maximum compatibility:

- **Main Assemblies**:
  - `FlexiCup_Vacuum.STEP` (109MB): Complete vacuum suction mode assembly
  - `FlexiCup_Bernoulli.STEP` (109MB): Complete Bernoulli suction mode assembly

- **Modular Components**:
  - `suction cup top.STEP`: Top housing with camera and electronics
  - `suction cup bottom I-IV.STEP`: Four interchangeable bottom configurations
    - I & II: For vacuum mode operation
    - III & IV: For Bernoulli mode operation

- **Bill of Materials**:
  - `FlexiCup_CAD_BOM.xlsx`: Complete list of mechanical components

### PCB Design Files
Complete electronics design for the FlexiCup controller:

- **Schematic**: `FlexiCup_Schematic.pdf` - Circuit diagram
- **Layout**: `FlexiCup_PCB.pdf` - PCB layout design
- **BOM**: `FlexiCup_PCB_BOM.xlsx` - Electronic components list
- **Manufacturing**: `Gerber_PCB.zip` - Gerber files for PCB fabrication

**Key Components**:
- ESP32S3 microcontroller with Wi-Fi
- OV5640 camera interface
- LED driver circuits
- Power management (3.7V LiPo battery)
- Wireless charging circuit

## 💻 Firmware Code

### ESP32S3 Camera Firmware
Located in `Firmware/ESPCAM/`, built with ESP-IDF framework.

**Main Features**:
- **Camera Control** (`camera.c/h`): OV5640 camera configuration and image capture
- **LED Control** (`led.c/h`): Illumination switching for vision-tactile sensing
- **HTTP Server** (`httpServer.c/h`): Web interface and video streaming
- **Wi-Fi** (`wifiConnect.c/h`): Wireless communication

**Key Specifications**:
- Image Resolution: 1024×768 @ 30Hz
- Streaming: Real-time video over Wi-Fi
- Tactile Resolution: 60,248 pixels·cm⁻²
- Power: 3.7V 300mAh LiPo battery

### Building the Firmware
```bash
cd Firmware/ESPCAM
idf.py build
idf.py flash
```

## 📊 System Specifications

### Mechanical
- **Suction Force**: Up to 34.3N (vacuum mode)
- **Modes**: Vacuum and Bernoulli suction
- **Configurations**: 4 modular bottom designs
- **Material**: PDMS membrane with reflective coating

### Electronics
- **Controller**: ESP32S3
- **Camera**: OV5640 with 180° fisheye lens
- **Connectivity**: Wi-Fi 802.11 b/g/n
- **Power**: Wireless charging capable
- **Battery Life**: Standalone operation supported

### Sensing
- **Vision**: 1024×768 resolution
- **Tactile**: 60,248 pixels·cm⁻²
- **Dual-Zone**: Central (switchable) + Peripheral (continuous)
- **Frame Rate**: 30 Hz

## 📄 Documentation

- **Research Paper**: `PDF/paper.pdf`
- **Project Website**: `index.html` (view at https://jump-howl.github.io/FlexiCup/)
- **Fabrication README**: `Fabrication/README.md`
- **Firmware README**: `Firmware/README.md`

## 🎥 Video Demonstrations

Optimized videos are available in `static/video/optimized/`:
- `overview.mp4` (6.2MB): System overview
- `integrated_show.mp4` (1.7MB): Hardware integration
- `multimodal_performance.mp4` (1.4MB): Sensing performance
- `modular_task.mp4` (970KB): Modular grasping tasks
- `dptask1.mp4` (1.2MB): Inclined transport task
- `dptask2.mp4` (759KB): Orange extraction task

## 🚀 Getting Started

### Fabrication Assembly
1. Review CAD models in `Fabrication/CAD/`
2. Fabricate PCB using files in `Fabrication/PCB/`
3. Follow BOM files for component sourcing
4. Assemble according to CAD models

### Firmware Setup
1. Install ESP-IDF framework
2. Navigate to `Firmware/ESPCAM/`
3. Configure Wi-Fi settings in `main/src/wifiConnect.c`
4. Build and flash firmware

### Testing
1. Power on the device
2. Connect to FlexiCup Wi-Fi network
3. Access web interface via browser
4. Test vision and tactile sensing modes

## 📝 Citation

If you use this work in your research, please cite:

```bibtex
@article{flexicup2024,
  title={FlexiCup: Wireless Multimodal Suction Cup with Dual-Zone Vision-Tactile Sensing},
  author={Anonymous},
  journal={Under Review},
  year={2024}
}
```

## 📧 Contact

For questions or collaboration inquiries, please refer to the paper for contact information.

## 📜 License

This project is licensed under Creative Commons Attribution-ShareAlike 4.0 International License.

---

**Note**: Large CAD files (*.STEP) are managed with Git LFS. Clone with `git lfs clone` to download all files.