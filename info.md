# Flipr Local pour Home Assistant

Intégration **100 % locale, sans cloud** pour les sondes de piscine **Flipr AnalysR**.

Le fabricant CTAC Tech (Flipr) a été placé en liquidation et la marque reprise par une nouvelle société (Yotilus) ; dans cette transition, la continuité des serveurs cloud n'est pas garantie. Cette intégration **sauve votre matériel** en lisant directement les trames Bluetooth Low Energy (BLE) de la sonde, sans jamais passer par Internet.

## Points forts

* **100 % local :** aucune dépendance au cloud. Fonctionne via l'adaptateur Bluetooth de votre serveur ou un proxy Bluetooth ESPHome.
* **Chlore Actif (HOCl) :** modèle thermodynamique (fraction de HOCl à partir du pKa dépendant de la température) tenant compte du pH, de la température et du stabilisant (CyA), pour estimer le vrai pouvoir désinfectant au-delà d'une simple mesure ORP.
* **Analyse à la demande :** déclenchez manuellement la pompe de mesure de la sonde (attente puis lecture), comme le fait l'application officielle.
* **Métriques complètes :** Température, pH, ORP (Redox), Batterie, Indice de saturation de Langelier (LSI) et qualité du signal Bluetooth (RSSI).

## Prérequis important

Cette intégration a besoin d'une bonne couverture Bluetooth. Les piscines sont des environnements hostiles pour la radio (l'eau absorbe le signal), donc un **proxy Bluetooth ESPHome** placé au plus près du bassin est fortement recommandé pour la stabilité.

## Documentation

* **Guide complet :** [README.md](README.md)
* **Recycler la passerelle WiFi Flipr en proxy Bluetooth ESPHome :** [docs/esphome-proxy.md](docs/esphome-proxy.md)

---
*Développé par un passionné, pour la communauté.*
