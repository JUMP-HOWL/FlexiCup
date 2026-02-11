# FlexiCup Tutorial

## Hardware Fabrication

The hardware of this project is fully open-source. All materials can be directly purchased or easily fabricated from existing components.

### Bill of Materials

`FlexiCup_website/Hardware/Fabrication/CAD/FlexiCup_CAD_BOM.xlsx` provides all mechanical component models and sourcing information.

### PDMS and Sensing Layer

PDMS can be replaced with cheaper silicone alternatives (e.g., Smooth-On's Ecoflex series). The mixing ratio of silver powder and PDMS for the semi-transparent sensing layer has been extensively tested and optimized. An important detail: this layer needs to be spin-coated onto the PDMS substrate at a relatively high speed, such as 1000 rpm.

### Sealing Skirt

The sealing skirt is an inconspicuous but critical component, as it determines whether the suction cup can achieve proper sealing. In this project, I used commercial silicone suction cups and cut along the edges using a laser cutter. You need to increase the laser cutter's power and ensure proper ventilation and heat dissipation. **This process can be hazardous—please take safety precautions.** I look forward to future work on fully flexible, integrated visuotactile suction cups, which I believe would enable even more applications.

### Light Diffuser

The light diffuser was selected after multiple trials. It has sufficient rigidity to resist deformation under airflow. Essentially, it's just a plastic sheet, so alternative materials can be substituted.

### Camera

Remember to purchase a fisheye camera—180-degree FOV works best, though 160-degree is also acceptable. Note that the OV5640 is an outdated camera model with issues including low resolution, instability, and heat generation. Successfully adapting a newer, better camera and debugging the ESP32 low-level drivers would be an excellent practical exercise.

### Suction Cup Top

The material for the suction cup top is flexible—standard PLA from common 3D printers works fine.

### Battery

Any 3.7V battery will work. Battery capacity is only limited by the internal volume of the suction cup.

### O-Ring

The O-ring is another critical component affecting airtightness. While theoretically custom parameters would optimize performance, in practice, any O-ring that fits the groove in the suction cup top will work.

### Wireless Charging

The wireless charging coil and circuitry are based on mature open-source solutions available online, so I won't elaborate further here.

### PCB and Power Supply

Although the system includes wireless charging functionality, considering the need to use the suction cup for robot learning tasks requiring long-duration data collection, the limited volume and capacity of a 3.7V battery can be challenging. Therefore, a wired power supply option is also provided—please refer to the PCB schematic for details.

The PCB antenna design is currently very stable. For specific design considerations, please refer to hardware community forums regarding ESP32-S3 antenna layout requirements.

### LED Light Source

The LED light source uses WS2812, which can actually produce color or dynamically changing illumination—this might enable additional visuotactile functionalities.

### Assembly Notes

For assembly, I used M2.5 screws to secure the PCB to the suction cup top. The battery and antenna are sandwiched in the space between the PCB and suction cup top, while the light diffuser is held in place by friction at the outlet of the suction cup top.

Although this may seem somewhat improvised, I discovered an interesting phenomenon in practice: the light diffuser actually enhances suction force. I hypothesize this may be due to the Bernoulli effect (yes, the same Bernoulli principle mentioned in my paper). As airflow passes through the gaps between the light diffuser and suction cup top, as well as between the PCB and suction cup top, the airflow accelerates, thereby reducing pressure. Interestingly, this phenomenon only appears in the vacuum suction cup, not in the Bernoulli suction cup. It's somewhat similar to the Venturi effect in a Venturi tube, but lacking a fluid mechanics background, I cannot provide a detailed theoretical analysis. I'll leave this phenomenon and hypothesis for interested readers to explore.

## Firmware

The firmware is developed using ESP-IDF 5.0.2. The complete source code is available at `FlexiCup_website/Hardware/Firmware`.

### Configuration

You need to modify the WiFi name and password, as well as the UDP communication IP address in the code. You can also further customize camera model, resolution, and other parameters.

### Flashing

After successful compilation, use a USB-to-TTL module for flashing. You need to connect four wires (solder pads are reserved on the back of the PCB—apologies for not providing more convenient connectors due to space constraints): TX, RX, RST, and BOOT0. 

**Flashing procedure:**
1. Connect BOOT0 pin to ground
2. Connect RST to ground
3. Release RST
4. ESP32 enters flashing mode and firmware can be uploaded

## Learning Pipeline

The complete learning pipeline is provided, and I hope it will be helpful. However, I don't think keyboard teleoperation for data collection is ideal, as it resulted in very jerky trained motions. This is also related to the movement step size I initially set during data collection. 

I recommend trying **GELLO** (an excellent IROS teleoperation device work) for control. Although GELLO doesn't natively support UR3, following its calibration pipeline for data collection control should work.

---

Thank you for reading this far. I look forward to seeing you use FlexiCup!
