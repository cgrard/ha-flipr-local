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

## Home Assistant ne lit plus la sonde alors que le proxy va bien (bug HA, corrigé)

Symptôme : `ha-flipr-local` tombe en `out_of_range`, le signal passe `unavailable`, le scanner côté HA reste `current_mode: null` / `discovered_devices: []` (« Bluetooth scanner has gone quiet »), alors que le proxy scanne et **forwarde pourtant bien toutes ses annonces BLE**. C'est HA qui ne les consomme plus.

C'était un bug HA, **corrigé en amont** (correctif vérifié sur HA Core 2026.7.2) : [home-assistant/core#175664](https://github.com/home-assistant/core/issues/175664). Cause racine : une **souscription d'annonces périmée côté proxy**. À une reconnexion (ou un redémarrage / une mise à jour de HA), le proxy gardait la souscription de l'ancienne connexion et **rejetait le nouveau demandeur** ; l'ESP émettait alors vers une souscription morte et le scanner reconnecté ne recevait plus rien, la connexion API restant pourtant saine. D'où le symptôme « proxy actif mais plus rien, débloqué seulement en redémarrant l'ESP ».

Le correctif est côté HA (`bleak-esphome` 3.9.7, livré dans **Home Assistant Core 2026.7.2**) et côté firmware (**ESPHome 2026.7.0**, [#17423](https://github.com/esphome/esphome/pull/17423)). **Il suffit de mettre Home Assistant à jour en 2026.7.2 ou plus récent** (sans reflasher le proxy) ; le reflash en ESPHome 2026.7.0 est un renfort optionnel (pas sur la ligne 2026.6.x, 2026.6.5 compris). Un downgrade de HA ne protège pas.

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
