# 🏊‍♂️ Flipr Local for Home Assistant

A **100% local, cloud-free** integration for **Flipr AnalysR** pool probes.

After the liquidation of CTAC-TECH (Flipr), the official servers may shut down, potentially bricking the probes. This integration **rescues your hardware** by reading the probe's Bluetooth Low Energy (BLE) frames directly, without ever going through the internet.

## ✨ Highlights

* **100% local:** no cloud dependency. Works through your server's Bluetooth adapter or an ESPHome Bluetooth Proxy.
* **Active Chlorine (HOCl):** thermodynamic model (HOCl fraction from the temperature-dependent pKa) accounting for pH, temperature and stabilizer (CyA), to estimate the real disinfection power beyond a raw ORP reading.
* **On-demand analysis:** manually trigger the probe's measurement pump (wait-and-read), mirroring the official app's behavior.
* **Full metrics:** Temperature, pH, ORP (Redox), Battery, Langelier Saturation Index (LSI) and Bluetooth signal quality (RSSI).

## ⚠️ Important prerequisite

This integration needs solid Bluetooth coverage. Pools are harsh environments for radio (water absorbs the signal), so an **ESPHome Bluetooth Proxy** placed as close to the pool as possible is strongly recommended for stability.

## 📖 Documentation

* 📘 **Full guide (English):** [README.md](https://github.com/Adrien40/ha-flipr-local/blob/main/README.md)
* 🇫🇷 **Guide complet (français) :** [README.fr.md](https://github.com/Adrien40/ha-flipr-local/blob/main/README.fr.md)

---
*Developed by an enthusiast, for the community.*
