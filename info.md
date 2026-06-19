# 🏊‍♂️ Flipr Local pour Home Assistant

Bienvenue sur l'intégration locale et sans cloud pour les sondes de piscine **Flipr AnalysR**.

Suite à la liquidation de l'entreprise CTAC-TECH (Flipr), les serveurs officiels menacent de fermer, rendant les sondes potentiellement inutilisables. Cette intégration a été créée pour **sauver votre matériel** en interceptant directement les trames Bluetooth Low Energy (BLE) émises par la sonde, sans jamais passer par internet.

## ✨ Fonctionnalités
* **100% Local :** Dépendance cloud supprimée. Fonctionne via l'antenne Bluetooth de votre serveur ou via des Proxy ESPHome.
* **Chlore Actif (HOCl) :** Modèle thermodynamique (fraction HOCl calculée via le pKa dépendant de la température) tenant compte du pH, de la température et du stabilisant (CyA), pour estimer le pouvoir désinfectant réel au-delà de la simple lecture ORP.
* **Lecture Active (Pump Control) :** Déclenchement manuel de la pompe d'analyse (Wait-and-Read) reproduisant le comportement natif de l'application.
* **Métriques complètes :** Température, pH, Redox (ORP), Batterie, Indice de Langelier (ISL) et Qualité du signal Bluetooth (RSSI).

## ⚠️ Prérequis important
Cette intégration nécessite une excellente couverture Bluetooth. Les piscines étant des milieux très contraignants pour les ondes radio (l'eau absorbe les signaux), l'utilisation d'un **Proxy Bluetooth ESPHome** placé au plus près du bassin est fortement recommandée pour une stabilité optimale.

---
*Développé par un passionné, pour la communauté.*
