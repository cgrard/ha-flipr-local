# Changelog

Tous les changements notables de ce projet sont documentés dans ce fichier.

Le format s'appuie sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet suit le [versionnage sémantique](https://semver.org/lang/fr/).

## [1.2.2] - 2026-07-12

### Corrigé

- Auto-récupération du signal Bluetooth : la disponibilité se basait en dur sur un indicateur interne piloté par les rappels Bluetooth de Home Assistant. À signal faible, cet indicateur pouvait rester bloqué sur « hors de portée » (l'événement de perte se déclenchait sans que l'événement de retour ne le réarme), figeant la sonde en `out_of_range` jusqu'à un rechargement manuel de l'intégration, alors même que des trames d'advertisement fraîches continuaient d'arriver. La disponibilité se fonde désormais sur la dernière trame réellement reçue, si bien que l'intégration se rétablit d'elle-même au cycle suivant. Test de non-régression ajouté.

## [1.2.1] - 2026-07-11

### Corrigé

- Lecture de la sonde dès son retour en portée (après un redémarrage de Home Assistant ou une perte de signal) au lieu d'attendre le cycle d'interrogation suivant, qui pouvait laisser jusqu'à une heure sans mesure fraîche.
- Le capteur RSSI temps réel repasse à `indisponible` à la perte de signal, au lieu de conserver la dernière valeur affichée.
- `lsi_status` renvoie l'état « inconnu » standard de Home Assistant quand l'indice de Langelier n'est pas calculable, au lieu d'une valeur d'énumération réservée.
- Validation des seuils ORP comparée en flottant : des bornes ORP non entières ne sont plus tronquées puis rejetées à tort.
- Robustesse : `estimate_free_chlorine` gère les entrées manquantes, le coordinator se nettoie complètement à l'arrêt (plus de fuite de timer de rafraîchissement au rechargement de l'intégration), et le dépassement de la file de notifications BLE est réellement intercepté.

### Modifié

- `bleak` et `bleak-retry-connector` retirés des `requirements` du manifest : ils sont déjà fournis et épinglés par la dépendance `bluetooth` de Home Assistant. Évite tout risque de mise à niveau de la pile Bluetooth partagée par l'ensemble de Home Assistant.
- Réorganisation interne du code : l'intégration, jusque-là concentrée dans un `__init__.py` de près de 1200 lignes, est découpée par responsabilité en modules (`coordinator`, `ble`, `parser`, `store`, `flow_schema`, `sensor_entities`, `helpers`) et la liste des capteurs devient une table déclarative. Aucun changement de comportement, meilleure lisibilité et maintenabilité.

### Ajouté

- Tests couvrant le rafraîchissement de rattrapage, la disponibilité du capteur RSSI, la table de specs des capteurs et le cycle de vie du drapeau de lecture.

## [1.2.0] - 2026-07-01

### Ajouté

- Guide proxy ESPHome : bouton `restart` exposé à Home Assistant et automation « watchdog » qui redémarre le proxy si aucune analyse ne remonte depuis 2 h, en remplacement du débranchage manuel après un gel BLE.
- Workflow d'intégration continue exécutant la suite de tests avec pytest à chaque push et pull request (`.github/workflows/test.yaml`).
- `requirements_test.txt` déclarant les dépendances de test, dont la pile Bluetooth/USB de Home Assistant tirée à l'import de l'intégration.
- `pytest.ini` avec le chemin des tests et la configuration asyncio.
- `.gitignore` couvrant les artefacts Python, pytest, ruff, virtualenv et éditeurs.
- Clé `loggers` du manifest (`bleak`, `bleak_retry_connector`) pour que l'activation des logs de debug de l'intégration couvre aussi ses dépendances Bluetooth.
- Guide matériel sur le recyclage de la passerelle WiFi Flipr obsolète en proxy Bluetooth ESPHome, lié depuis la section Sauvetage matériel du README.
- Guide de calibration sous `docs/` (jusque-là non lié), référencé depuis le README, avec un nommage de fichiers uniforme.
- Configuration `.markdownlint.jsonc` encodant le style Markdown du dépôt, et une passe corrigeant les problèmes de lint structurels (lignes vides autour des titres, listes et tableaux, espaces en fin de ligne, liens vides ou non descriptifs) pour que tous les fichiers Markdown passent le lint proprement.
- Tests unitaires pour la logique pure jusque-là non testée : validation de la calibration (`validate_calibration`, `_flatten_sections`), analyse des trames BLE (`_parse_raw_frame`), calcul de calibration du pH (`_compute_ph_calibrated`), sélection de commande (`_select_command`) et détection du modèle (`get_flipr_model`).
- Tests d'intégration mockés couvrant un cycle complet de mise à jour du coordinator (chemins connexion, écriture, notification et interrogation Start Max) de bout en bout.
- Large couverture de tests pour les plateformes d'entités, les flux de configuration et d'options, les chemins erreur/retry et sauvegarde-restauration du coordinator, et un setup/unload complet d'entrée, portant la couverture globale à environ 80 %.

### Modifié

- Documentation fournie en français uniquement.
- Note de fork ajoutée en tête du README (fork maintenu de `Adrien40/ha-flipr-local`, créditant l'auteur amont pour l'intégration d'origine).
- Retrait des appels au don (bouton Buy Me a Coffee, `.github/FUNDING.yml`) et des emoji décoratifs dans la documentation.
- Exposition d'une propriété publique `is_shutdown` du coordinator ; les entités ne lisent plus l'attribut privé.
- Traduction des derniers commentaires de code français vers l'anglais et ajout de la valeur fautive à l'erreur `get_mv_from_input` pour des logs plus clairs.
- Passage de la version de `manifest.json` à `1.2.0` (restée à `1.0.0`, jamais incrémentée pour la version 1.1.0).
- Remplacement du pourcentage de batterie linéaire par une courbe de décharge Li-SOCl2 (Saft LS26500) dans `battery.py`. L'ancien mapping linéaire 2500-3600 mV ne correspondait pas au plateau plat de cette chimie et ne donnait quasiment aucune alerte de fin de vie ; la nouvelle courbe par morceaux reste proche du plein sur tout le plateau et chute au niveau du genou, là où la tension est réellement informative.
- Nettoyage interne sans changement de comportement : correction des lints ruff étendus (`itertools.pairwise`, `ClassVar`, `raise ... from None`, `contextlib.suppress`), remontée des dictionnaires d'icônes de capteurs en constantes de module, et abaissement des logs de chimie « could not compute » d'erreur à debug pour réduire le bruit.
- Refactorisation de `config_flow.py` sans changement de comportement : pilotage de chaque champ numérique depuis une table de bornes partagée pour que les flux de configuration  et d'options ne puissent plus diverger (les sections calibration et seuils étaient entièrement dupliquées), et découpage de `validate_calibration` en helpers ciblés. De nouveaux tests verrouillent les constructeurs de schéma.
- Refactorisation des plateformes d'entités sans changement de comportement : un helper partagé `resolve_entry_context` et une constante `CONF_MODEL` suppriment le boilerplate de setup répété, et le signal du dispatcher est centralisé dans `options_updated_signal` (un émetteur, quatre récepteurs) avec un petit mixin d'entité pour le câblage de l'abonnement.
- Décomposition de `_async_update_data` (420 lignes) sans changement de comportement : extraction de helpers ciblés (sélection de commande, assemblage de trame, les deux stratégies de lecture et le bloc `_run_ble_exchange`), réduisant sa complexité de 47 à 11. L'extraction est couverte par les nouveaux tests d'intégration mockés.

### Corrigé

- Guide proxy ESPHome : correction du réglage de scan BLE qui saturait la coexistence WiFi/BLE de la radio 2,4 GHz unique de l'ESP32-C6 (`window == interval`, par exemple `1100ms / 1100ms`, scan en continu sans jamais rendre la main) et finissait par figer la pile BLE (`ha-flipr-local` bloqué en `out_of_range` pendant des jours, WiFi toujours connecté, seul un redémarrage physique du proxy le débloquant). Passage à `window: 1000ms` (trou de 100 ms par cycle pour laisser un créneau à la coexistence) et `wifi: power_save_mode: none`. Les défauts ESPHome `320ms / 30ms` sont à proscrire : ils ratent les annonces rares de la sonde et provoquent un `out_of_range` immédiat sans même tenter la connexion.
- Réparation de la suite de tests de chimie, qui référençait des fonctions supprimées lors d'un refactor antérieur (`compute_active_chlorine`, `compute_flipr_active_chlorine`, `compute_flipr_theoretical_orp`) et échouait à l'import. Les tests couvrent désormais l'API actuelle (`estimate_free_chlorine`, `compute_active_chlorine_from_fc`, `compute_isl`, `compute_ph_equilibrium`, `get_mv_from_input`).
- Dialogue d'options néerlandais et portugais brésilien : une clé `sections` en double supprimait silencieusement les sections Général et Calibration de la sonde au parsing ; fusionnées en un seul bloc pour que les deux locales soient de nouveau complètes.
- Messages d'erreur du flux d'options : ajout des clés d'erreur de calibration du pH manquantes dans chaque locale (elles apparaissaient auparavant comme des clés brutes non traduites).
- Formulation des locales : ordre du nom RSSI en tchèque, casse de phrase en polonais, terme « brut » en russe, noms composés en néerlandais et danois, terme du stabilisant en chinois.
- Flux de configuration : conservation de la calibration déjà saisie lors du choix de la saisie MAC manuelle ; définition d'un `unique_id` pour les saisies manuelles afin d'éviter de configurer deux fois le même appareil ; attribution d'une erreur de parsing du pH au champ fautif.
- Coordinator BLE : comparaison de la valeur de la commande en attente (pas seulement son type) pour ne pas perdre un changement de mode de synchronisation fait pendant une interrogation ; arrêt d'une fuite de handle de timer de sauvegarde par `_do_save` et protection du callback de debounce à l'arrêt ; annulation d'un timer de retry armé au passage hors de portée.
- Entités : application immédiate d'un nouvel intervalle de scan en reprogrammant le timer d'interrogation ; marquage d'un `last_received` naïf en UTC plutôt qu'en heure locale ; maintien du capteur RSSI disponible tant que des annonces arrivent pendant les mesures en pause.

## [1.1.0] - 2026-05-12

### Ajouté

- Matchers de découverte Bluetooth pour des noms locaux Flipr supplémentaires (`F2B*` et `F30*`-`F3F*`), élargissant la détection automatique des appareils.

### Modifié

- Refactorisation des commentaires inline et amélioration de la clarté du code.
- Mises à jour de la documentation.

## [1.0.0] - 2026-04-19

### Ajouté

- Version initiale : intégration locale (BLE) pour les analyseurs de piscine Flipr, avec température, pH, ORP, chlore libre estimé, chlore actif (HOCl), indice de saturation de Langelier, batterie et diagnostics Bluetooth.
- Calibration pH/ORP configurable, offset de température, paramètres de l'eau (TAC, TH, TDS, CyA) et seuils d'alerte via le flux d'options.
- Sélection du modèle chlore/brome, contrôle du mode de synchronisation et mode passerelle.

[1.2.1]: https://github.com/cgrard/ha-flipr-local/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/cgrard/ha-flipr-local/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/cgrard/ha-flipr-local/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/cgrard/ha-flipr-local/releases/tag/v1.0.0
