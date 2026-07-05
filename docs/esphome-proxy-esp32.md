# Proxy Bluetooth ESPHome dédié au Flipr (ESP32 générique)

Ce guide donne une configuration ESPHome de référence pour un **proxy Bluetooth dédié au Flipr**, sur un **ESP32 neuf du commerce**. Cas d'usage typique : remplacer une ancienne passerelle (Sigfox ou cloud) devenue inutile, ou rapprocher le Bluetooth de la piscine quand l'adaptateur Bluetooth de Home Assistant est trop loin du bassin.

Différence avec l'autre guide : [`esphome-proxy.md`](esphome-proxy.md) documente le **recyclage de la passerelle WiFi Flipr d'origine** (un ESP32-C6 précis, avec démontage, brochage et machine à états LED). Ici on part d'un ESP32 quelconque, config minimale.

Rappel : n'importe quelle source Bluetooth de Home Assistant convient (Bluetooth intégré, clé USB Bluetooth, proxy ESPHome). Le proxy ESPHome n'a d'intérêt que si HA est loin de la piscine.

## Ce dont le Flipr a besoin de n'importe quel proxy

1. **Connexions actives obligatoires** (`bluetooth_proxy: active: true`). L'intégration ne lit pas la mesure dans l'advertising : elle **se connecte en GATT** pour lire et écrire. Un proxy **passif** relaie les annonces mais ne peut pas faire cette lecture, donc il ne fonctionnera pas.
2. **Fenêtre de scan longue.** La sonde émet ses annonces rarement et faiblement ; une fenêtre longue maximise les chances de les capter.
3. **De la proximité.** Voir la section Placement plus bas : c'est le facteur dominant, loin devant la config.

## Configuration de référence (ESP32 classique)

À privilégier : un ESP32 **classique** (double cœur, BLE mature), idéalement une carte à **antenne externe** (connecteur U.FL/IPEX) pour la portée en extérieur.

```yaml
esphome:
  name: flipr-proxy
  friendly_name: Flipr BLE Proxy

esp32:
  board: esp32dev
  framework:
    type: esp-idf # recommandé pour bluetooth_proxy

logger:

api:
  encryption:
    key: "[TA_CLE_API_BASE64]" # openssl rand -base64 32

ota:
  - platform: esphome
    password: "[TON_MDP_OTA]"

wifi:
  ssid: "[TON_SSID]"
  password: "[TON_MDP_WIFI]"
  ap:
    ssid: "Flipr-Proxy Fallback"
    password: "[TON_MDP_AP]"

captive_portal:

# --- BLE ---
# Fenêtre longue : capte les annonces rares et faibles de la sonde Flipr.
# Sur un ESP32 classique (double cœur), window == interval (scan continu) ne pose
# pas de problème de coexistence WiFi/BLE.
esp32_ble_tracker:
  scan_parameters:
    interval: 1100ms
    window: 1100ms
    active: true

# OBLIGATOIRE : la sonde Flipr se lit via une connexion GATT active, pas dans
# l'advertising. Un proxy passif ne fonctionnera pas.
bluetooth_proxy:
  active: true
```

## Variante ESP32-C6 / mono-radio (C6, H2...)

Ces puces n'ont qu'une **seule radio 2,4 GHz** partagée WiFi/BLE. Avec `window == interval` (scan continu), la coexistence se fige au bout d'un moment et la pile BLE se bloque (`out_of_range` jusqu'au reboot). Il faut laisser un **trou par cycle** (`window < interval`) et **désactiver le modem-sleep WiFi** :

```yaml
esp32:
  board: esp32-c6-devkitc-1
  variant: esp32c6
  framework:
    type: esp-idf

wifi:
  ssid: "[TON_SSID]"
  password: "[TON_MDP_WIFI]"
  power_save_mode: none # évite que le modem-sleep prive le BLE de créneaux de coex
  ap:
    ssid: "Flipr-Proxy Fallback"
    password: "[TON_MDP_AP]"

esp32_ble_tracker:
  scan_parameters:
    interval: 1100ms
    window: 1000ms # 100 ms de trou par cycle, rend la main à la coexistence
    active: true
```

## Home Assistant 2026.7 : forcer le mode de scan sur Active

Depuis Home Assistant 2026.6, le mode de scan par défaut d'un proxy Bluetooth est **« Auto »**. En 2026.7.1 (`habluetooth 6.26.2`), ce mode Auto est cassé avec les proxies ESPHome : `ha-flipr-local` tombe en `out_of_range`, le signal passe `unavailable`, et le scanner côté HA reste bloqué en `current_mode: null` (avertissement « Bluetooth scanner has gone quiet »), alors que le proxy forwarde pourtant bien toutes les annonces BLE. C'est une régression côté Home Assistant (`habluetooth` passé de 6.8.3 à 6.26.2 dans ce patch), pas un souci de firmware.

Parade, sans downgrader Home Assistant : Paramètres → Appareils et services → intégration **ESPHome** → votre proxy → **Configurer** → **Mode de scan Bluetooth** → **Active**, puis **redémarrer le proxy** pour que le nouveau mode s'applique réellement (le mode Active seul, sans reconnexion de l'ESP, ne suffit pas). Gardez-le sur **Active** tant que HA n'a pas corrigé le mode Auto.

## Placement et portée : le facteur dominant

Aucun réglage firmware ne rattrape un signal trop faible. La radio BLE du Flipr est modeste, et la sonde flotte dans l'eau (le 2,4 GHz est fortement atténué par l'eau, et plus encore par une vitre). Retours d'utilisateurs sur les anciennes générations : lecture nickel **très près**, mais **zéro à 3-4 m derrière une vitre**.

Conséquences pratiques :

- Placer l'ESP **au plus près de la sonde**, **au bord du bassin**, **bas (niveau de l'eau)**, en **ligne de vue** directe avec la sonde.
- **Jamais derrière une vitre** (baie, fenêtre, double vitrage) : une vitre suffit à tuer la liaison.
- Antenne **externe orientée vers la sonde**, non masquée par la margelle.
- Viser un **RSSI > -80 dBm** stable. En dessous de -85 la connexion GATT devient sporadique ; vers -95 (sonde immergée et éloignée) une lecture fiable n'est pas atteignable.
- Un boîtier étanche posé au bord de l'eau, à quelques dizaines de centimètres de la sonde, est souvent la seule façon d'obtenir un lien stable sur les anciennes sondes.

Point de contexte : c'est exactement la limite que le **Sigfox masquait** sur les anciens Flipr (du LPWAN longue portée pour compenser un BLE local médiocre). En passant en 100 % local, on récupère cette contrainte de proximité, comme la propre passerelle Flipr qui devait déjà être placée près du bassin.

## Voir aussi

- [`esphome-proxy.md`](esphome-proxy.md) : recyclage de la passerelle WiFi Flipr d'origine (ESP32-C6).
- [`calibration.md`](calibration.md) : calibration pH (2 points) et température, à faire notamment sur les anciennes générations dont les coefficients de conversion diffèrent.
