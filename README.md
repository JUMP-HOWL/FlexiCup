# FlexiCup: Wireless Multimodal Suction Cup with Dual-Zone Vision-Tactile Sensing

This repository contains the complete project files for FlexiCup, including hardware designs, firmware code, software algorithms, and project documentation.

## 📁 Repository Structure

```
FlexiCup/
├── Hardware/              # Hardware design and firmware
│   ├── Fabrication/       # Physical hardware design files
│   │   ├── CAD/          # 3D CAD models and mechanical designs
│   │   │   ├── FlexiCup_Vacuum.STEP          # Vacuum mode assembly (109MB)
│   │   │   ├── FlexiCup_Bernoulli.STEP       # Bernoulli mode assembly (109MB)
│   │   │   ├── suction cup bottom I.STEP     # Bottom configuration I
│   │   │   ├── suction cup bottom II.STEP    # Bottom configuration II
│   │   │   ├── suction cup bottom III.STEP   # Bottom configuration III
│   │   │   ├── suction cup bottom IV.STEP    # Bottom configuration IV
│   │   │   ├── suction cup top.STEP          # Top assembly
│   │   │   └── FlexiCup_CAD_BOM.xlsx        # CAD Bill of Materials
│   │   │
│   │   └── PCB/          # PCB design files
│   │       ├── FlexiCup_Schematic.pdf        # Circuit schematic
│   │       ├── FlexiCup_PCB.pdf              # PCB layout
│   │       ├── FlexiCup_PCB_BOM.xlsx         # PCB Bill of Materials
│   │       └── Gerber_PCB.zip                # Manufacturing files
│   │
│   └── Firmware/          # Embedded firmware code
│       └── ESPCAM/       # ESP32S3 camera firmware
│           ├── main/     # Main application code
│           │   ├── inc/  # Header files
│           │   │   ├── camera.h
│           │   │   ├── httpServer.h
│           │   │   ├── led.h
│           │   │   └── wifiConnect.h
│           │   ├── src/  # Source files
│           │   │   ├── camera.c
│           │   │   ├── httpServer.c
│           │   │   ├── led.c
│           │   │   └── wifiConnect.c
│           │   ├── html/ # Web interface
│           │   └── main.c # Main entry point
│           │
│           ├── managed_components/  # ESP32-Camera library
│           ├── CMakeLists.txt
│           ├── sdkconfig
│           └── README.md
│
├── Software/              # High-level software and algorithms
│   └── diffusion_policies/ # Diffusion policy implementation
│       ├── data_collect.py  # Data collection pipeline
│       ├── train.py        # Training script
│       ├── deploy.py       # Deployment script
│       ├── environment.yml # Conda environment
│       └── README.md       # Software documentation
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

## 🔧 Hardware Files

### Fabrication Design Files
All mechanical and electronic designs are provided for complete system reproduction:

**CAD Models (STEP Format)**
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

**PCB Design Files**
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

### Firmware Code

**ESP32S3 Camera Firmware**
Located in `Hardware/Firmware/ESPCAM/`, built with ESP-IDF framework.

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

**Building the Firmware**
```bash
cd Hardware/Firmware/ESPCAM
idf.py build
idf.py flash
```

## 💻 Software

### Diffusion Policy Implementation
Located in `Software/diffusion_policies/`, this contains the complete machine learning pipeline for contact-aware manipulation.

**Main Components**:
- **Data Collection** (`data_collect.py`): Automated data collection pipeline for demonstration gathering
- **Training** (`train.py`): Diffusion policy training with multimodal observations
- **Deployment** (`deploy.py`): Real-time deployment for robot control
- **Environment** (`environment.yml`): Conda environment with all dependencies

**Key Features**:
- Multimodal fusion of vision and tactile data
- Diffusion-based policy learning
- Real-time inference for robot control
- Support for dual-zone sensing integration
- Contact-aware manipulation capabilities

**Setup and Usage**
```bash
cd Software/diffusion_policies
conda env create -f environment.yml
conda activate flexicup
python train.py --config configs/flexicup_config.yaml
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
- **Tutorial**: `TUTORIAL.md` - Complete fabrication and setup guide
- **Project Website**: `index.html` (view at https://jump-howl.github.io/FlexiCup/)
- **Hardware README**: `Hardware/README.md`
- **Software README**: `Software/diffusion_policies/README.md`

## 🎥 Video Demonstrations

Optimized videos are available in `static/video/optimized/`:
- `overview.mp4` (6.2MB): System overview
- `integrated_show.mp4` (1.7MB): Hardware integration
- `multimodal_performance.mp4` (1.4MB): Sensing performance
- `modular_task.mp4` (970KB): Modular grasping tasks
- `dptask1.mp4` (1.2MB): Inclined transport task
- `dptask2.mp4` (759KB): Orange extraction task

## 🚀 Getting Started

### Hardware Assembly
1. Review CAD models in `Hardware/Fabrication/CAD/`
2. Fabricate PCB using files in `Hardware/Fabrication/PCB/`
3. Follow BOM files for component sourcing
4. Assemble according to CAD models

### Firmware Setup
1. Install ESP-IDF framework
2. Navigate to `Hardware/Firmware/ESPCAM/`
3. Configure Wi-Fi settings in `main/src/wifiConnect.c`
4. Build and flash firmware

### Software Setup
1. Set up the diffusion policy environment:
   ```bash
   cd Software/diffusion_policies
   conda env create -f environment.yml
   conda activate flexicup
   ```
2. Collect training data or use provided datasets
3. Train the diffusion policy model
4. Deploy for real-time robot control

### Testing
1. Power on the device
2. Connect to FlexiCup Wi-Fi network
3. Access web interface via browser
4. Test vision and tactile sensing modes
5. Run software algorithms for manipulation tasks

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