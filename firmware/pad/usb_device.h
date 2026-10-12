#pragma once
// The USB half of firmware/pad: give the full-speed PHY to the OTG
// controller and start TinyUSB on port 0 as a device, printing both
// results to Serial. See usb_device.cpp, which is firmware/pad-usb's
// with the P4-only PHY swap fenced off so the same file builds on an S3.
void usb_start();
