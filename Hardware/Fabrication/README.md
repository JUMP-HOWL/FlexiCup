# FlexiCup Fabrication Design

This directory contains the fabrication design files for the FlexiCup system.

## Directory Structure

- **CAD/**: 3D CAD models and mechanical design files (STEP format)
- **PCB/**: PCB schematics, layout, BOM, and Gerber manufacturing files

## CAD Files

The CAD directory contains STEP files for:
- `FlexiCup_Vacuum.STEP`: Complete vacuum mode assembly
- `FlexiCup_Bernoulli.STEP`: Complete Bernoulli mode assembly
- `suction cup top.STEP`: Top housing with camera and electronics
- `suction cup bottom I–IV.STEP`: Four interchangeable bottom configurations
  - I & II: Vacuum mode (varying membrane diameters for deformable objects and tactile sensitivity)
  - III & IV: Bernoulli mode
- `FlexiCup_CAD_BOM.xlsx`: Complete mechanical Bill of Materials

## PCB Design

The PCB directory includes:
- `FlexiCup_Schematic.pdf`: Circuit schematic (ESP32-S3, OV5640 interface, WS2812 LED driver, power management, wireless charging)
- `FlexiCup_PCB.pdf`: PCB layout
- `FlexiCup_PCB_BOM.xlsx`: Electronic components BOM
- `Gerber_PCB.zip`: Gerber files for direct PCB manufacturing

## Manufacturing

All design files are ready for manufacturing. The top housing can be 3D printed (PLA, FDM, 0.2 mm layer height, 20–30% infill). The PDMS membrane requires a dual-layer fabrication process (30:1 PDMS base + Ag:PDMS 100:1 reflective layer). See `TUTORIAL.pdf` in the repository root for detailed fabrication instructions.

**Note**: Large CAD files (*.STEP) are managed with Git LFS.
