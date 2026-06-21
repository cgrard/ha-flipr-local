[![Français](https://img.shields.io/badge/Langue-Fran%C3%A7ais-blue)](calibration.fr.md) [![English](https://img.shields.io/badge/Language-English-red)](calibration.en.md)

# 🎛️ Calibration Guide - Flipr Local

This document explains how to set up and fine-tune your Flipr probe calibration directly from the Home Assistant interface. 💡

---

## 1. ⚙️ Understanding the calibration options

The **Flipr Local** integration is designed to be flexible and adapt to your technical comfort level. In the Configuration window (gear icon ⚙️), you have two methods to fill in the **pH 7 value** and **pH 4 value** fields:

### 📱 Method A: The official app's values

If you don't have your raw data, simply open the official Flipr app, go to **Menu > Expert Mode > Expert View** 🔍 and read the displayed pH values (e.g. `8.40` and `6.02`). Enter these values directly into Home Assistant.

<img src="screenshots/flipr_calibration.png" width="400" alt="Flipr calibration">

### ⚡ Method B: The raw values in millivolts (Advanced)

The integration exposes a `sensor.*_raw_ph_mv` entity showing your pH probe's raw voltage in mV 📉. Read the value once the Flipr is immersed and stabilized in the calibration solution (e.g. `1600` or `1900`), then enter these values directly in the configuration via the gear icon.

![Raw pH (mV)](screenshots/raw_ph_values_mv.png)

---

## 2. 🌡️ Adjusting the solution "Target" (Temperature)

Water chemistry is very sensitive to heat ☀️. In a pool protected by an enclosure, the water heats up quickly, and this physical rule also applies to your calibration solutions!

The pH of a buffer solution varies slightly with its temperature at the moment you dip the probe into it 💧.

* 📦 Look on the back of your calibration sachet or bottle (for example, for pH 7.00).
* 📊 You'll find a table giving the exact value depending on the liquid's temperature.
* 🎯 **Example:** At 20°C, a pH 7 solution is actually worth **7.02**.

<img src="screenshots/ph_calibration_targets.png" width="500" alt="pH solution target">

This is the very precise value you should enter into the **Solution target** fields. ✅

---

## 3. 🚨 Configuring the alert thresholds

The integration automatically creates binary status sensors (pH Status, Chlorine / Redox Status, Temperature Status). You can define your own limits in the configuration:

* ⚖️ **pH Min / Max:** (Default: 6.90 - 7.50)
* 🛡️ **Redox Min:** (Default: 650 mV)
* ❄️ **Temperature Min:** Useful to anticipate the risk of freezing in winter (Default: 6.0°C)
* 🥵 **Temperature Max:** Handy to prevent the water from going off if it gets too hot (Default: 32.0°C)

If one of the measurements crosses these thresholds, the sensor switches to the "Problem" state ⚠️, which is ideal for triggering your automations (notifications 📱, starting the filtration 🔄, etc.).

<img src="screenshots/alert_thresholds.png" width="500" alt="Thresholds">
