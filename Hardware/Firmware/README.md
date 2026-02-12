# FlexiCup Firmware

This directory contains the ESP32-S3 firmware for the FlexiCup system, built with the ESP-IDF framework (v5.0.2).

## Components

- **Camera Module** (`camera.c/h`): OV5640 camera configuration and 640×480 @ 30 Hz image capture
- **LED Control** (`led.c/h`): WS2812 addressable RGB LED illumination switching for vision-tactile modality control
- **HTTP Server** (`httpServer.c/h`): Web interface and real-time video streaming
- **Wi-Fi** (`wifiConnect.c/h`): Wireless communication and UDP image streaming

## Key Specifications

- **Resolution**: 640×480 @ 30 Hz
- **Streaming**: Real-time video over Wi-Fi (UDP)
- **Power**: 3.7V 300mAh LiPo battery (~30 min runtime)
- **Charging**: Wireless charging at 200 mA (12.5 μH coil)

## Building and Flashing

```bash
cd Hardware/Firmware/ESPCAM
idf.py build
idf.py -p /dev/ttyUSB0 flash
```

See `TUTORIAL.pdf` in the repository root for detailed flashing procedures including boot mode selection and USB-to-TTL connections.
