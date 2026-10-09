# Flight Narrator

**Flight Narrator** transforme chaque vol en taxi de **World of Warcraft Classic** en un voyage raconté. Le temps que le griffon t'emporte au-dessus des Tarides, d'Elwynn ou de Strangleronce, une voix grave de conteur déroule la lore de chaque région survolée : ses origines, ses guerres, ses personnages (Thrall, Jaina Portvaillant, le Cartel Gentepression…) et ces anecdotes qui transforment un simple paysage en histoire.

> ⚠️ **Pour WoW Classic uniquement** (Classic Era) — et **pour l'instant en français seulement**. Toutes les narrations sont écrites et jouées en français.

Tu cliques le maître de vol, tu décolles… et, quelques secondes plus tard, la voix s'installe. La durée du vol est découpée en tranches d'environ 75 secondes ; à chaque tranche, un clip tiré au hasard parmi les zones que tu survoles pendant cet intervalle se lance — sans jamais rejouer le même clip deux fois durant le vol, ni un clip entendu dans les cinq dernières minutes. Deux vols sur la même route ne racontent jamais la même chose, et un aller-retour non plus.

- 🎙️ **580+ clips** narrés par une voix de conteur française
- 🗺️ **40 régions** de Kalimdor et des Royaumes de l'Est
- ✈️ **des centaines de routes** Alliance et Horde couvertes
- 📖 **lore Classic fidèle** : noms propres français officiels, aucun événement d'après-Cataclysm
- 🎧 **aucun moteur requis** : les clips voyagent dans l'addon et sont joués avec `PlaySoundFile`

## Installation

Copie le dossier `FlightNarrator` dans le répertoire d'addons du client, en gardant exactement le nom `FlightNarrator` :

    World of Warcraft\_classic_era_\Interface\AddOns\FlightNarrator\

`_classic_era_` est le dossier Classic Era. Chaque autre version (Anniversary/BCC, Titan Reforged, Cata, Mists) s'installe dans son propre dossier `_classic_*`.

Ensuite `/reload`, puis coche l'addon dans la liste des AddOns.

Astuce : tape `/fn` en jeu pour activer ou désactiver le débogage (traces de détection de vol dans le chat).

## Structure de l'AddOn

L'addon est un **pipeline hors-ligne** : des données brutes (durées de vol, positions des nœuds) et des textes sont transformés en clips MP3 et en un unique fichier de données Lua (`TravelData.lua`), que le client lit simplement à l'exécution.

    DataFlights.lua ──► DataFlights-frFR.lua ─┐
    (durées EN)         (noms FR)             │
                                              ▼
    FlightData.lua ──► map_transform.py ──► zones/**/geometry.txt
    (positions monde)                         │
                                              ▼
    tools/zones-fr/*.txt ──► zones/**/*.txt ──► ElevenLabs ──► zones/**/*.mp3
    (narrations sources)      (narrations)                      (clips)
                                              │
    travels/**  ◄── generate_travel_zones.py  │
    (durées+escales) ◄────────────────────────┘
                                              ▼
                     generate_travel_data.py ──► TravelData.lua ──► FlightNarrator.lua
                                                                    (à l'exécution)

### 1. Les zones — `zones/`

L'arborescence `zones/` est le cœur du contenu. Une région = un dossier ; une ville, un donjon, un raid ou une sous-région = un sous-dossier ; un dossier spécial `Général` porte les clips valables pour toute la région.

    zones/
      Les Tarides/
        Général/            centaures.txt  centaures.mp3  geometry.txt  ...
        Ratchet/            ...
        Nord/  Sud/  Est/  Ouest/
        Cavernes des lamentations/
      ...

Chaque sous-dossier contient trois choses :

- `*.txt` — une narration (titre, paragraphe, pied de page « Durée / Clé lore ») ;
- le `*.mp3` correspondant, du même nom ;
- `geometry.txt` — le polygone de la zone sur la carte continent (voir § 5).

L'arborescence est générée et tenue à jour par `tools/generate_zones.py`, qui déduit les villes des noms officiels frFR de `DataFlights-frFR.lua` et ajoute donjons/sous-régions curés. Un `.gitkeep` garde les dossiers vides versionnables.

### 2. Les textes générés

Les narrations sont d'abord rédigées comme des **lignes sources** dans `tools/zones-fr/*.txt` :

    <région>/<sous-zone>/<slug>|<Titre>|<paragraphe>

Puis `tools/generate_zone_themes.py` écrit un fichier par thème sous `zones/<région>/<sous-zone>/<slug>.txt` (titre souligné, paragraphe, pied de page). Les règles de ton et de qualité (lore Classic exact, au moins un nom propre par texte, chute mémorable, pas de description de paysage banale) sont décrites dans :

- `prompts/zone-themes.md` — pour les textes de la bibliothèque de lore (`tools/zones-fr/`) ;
- `prompts/narration.md` — pour les narrations complètes par destination.

    python tools/generate_zone_themes.py

### 3. La conversion audio (ElevenLabs)

Un addon WoW ne peut pas synthétiser de voix : le seul moyen de faire parler une voix est d'**expédier des fichiers son**. Les clips sont donc rendus hors-ligne avec **ElevenLabs**, voix grave de conteur français « Martin Dupont » (`a5n9pJUnAhX4fn7lx3uo`), modèle `eleven_v4`, chaque texte préfixé de `[lentement]` et encodé en petit mono `mp3_22050_32`.

- `tools/text_to_mp3.py` — rend un texte isolé (`ELEVENLABS_API_KEY`, à mettre dans `.env`).
- `tools/render_zone_audio.py` — rend toutes les narrations d'une zone (`ZONE` en tête de fichier).
- `tools/render_waves.py` — rend l'ensemble des zones **par vagues prioritaires** (d'abord un clip par `Général`, puis par sous-zone, puis les deuxièmes, etc.), reprenable, avec backoff sur erreur 429 et arrêt propre quand les crédits sont épuisés (402).
- `tools/render_one_per_general.py` — garantit au moins un clip par zone.

    python tools/text_to_mp3.py "Vous quittez Stormwind, cap au nord vers Elwynn."
    python tools/render_waves.py --dry-run    # liste le plan sans appeler l'API
    python tools/render_waves.py              # rend et s'arrête au mur de crédits

> Après un rendu, fais `/reload` : le client ne voit que les fichiers son présents au chargement.

### 4. Les trajets — `travels/`

Les routes sont réparties par faction (Horde et Alliance gardés séparés, car leurs trajets diffèrent) :

    travels/<faction>/<source>/<destination>/
      duration.txt   # durée du vol, en secondes
      steps.txt      # escales + destination (1 ligne = route directe)
      zones.txt      # timeline de zones (routes directes uniquement)

- `tools/generate_travels.py` reconstruit l'arbre à partir de la section `CLASSIC` de `DataFlights.lua`.
- `tools/generate_travel_zones.py` échantillonne le segment de vol seconde par seconde, le croise avec les polygones (`zones/**/geometry.txt`) et écrit le `zones.txt` des routes directes : une suite d'intervalles `start;stop;région;sous-zone`.
- Les routes à plusieurs escales n'ont **pas** de `zones.txt` : leur timeline est reconstruite à la génération en concaténant le `zones.txt` de chaque tronçon.
- `routes.txt` et `connexions-absentes-de-travels.txt` sont des rapports (liste des routes multi-escales ; liaisons présentes dans les données DBC mais absentes des travel data).

### 5. Les polygones et le système de cartographie

Chaque zone porte un `geometry.txt` : un polygone **en coordonnées carte continent (0–100, X vers l'est, Y vers le sud)**, sommets listés dans le sens horaire, un par ligne `X;Y`.

C'est ce maillage qui permet de savoir *quelles zones on survole à chaque instant*. L'outillage associé :

- `FlightData.lua` — positions des nœuds de vol en yards (repère monde) ;
- `tools/map_transform.py` — ajuste une transformation affine par continent (moindres carrés sur des ancres relevées en jeu) pour passer des yards monde aux coordonnées carte 0–100 ;
- `tools/init_geometry.py` — sème un `geometry.txt` par dossier (rectangle région enveloppant, carré autour des villes) ;
- `tools/set_region_polygons.py` / `tools/set_subzone_polygons.py` — écrivent les polygones de région (`Général`) et de sous-zones, avec auto-contrôle « chaque nœud tombe dans sa région » ;
- `tools/zone_calibrator/` — **WebApp de calibration** : on charge la carte du continent, on fait glisser les pastilles (nœuds) sur les vraies villes pour réaligner la carte, puis on édite les polygones à la souris (déplacer / insérer / supprimer des sommets) ; « Sauvegarder » réécrit les `geometry.txt` ;
- `tools/plot_geometry.py` / `tools/render_map_png.py` — produisent les visualisations `geometry_map.svg` / `geometry_map.png` (régions colorées + nœuds) ;
- `tools/validate_geometry.py`, `tools/validate_zones.py`, `tools/check_timeline_coverage.py` — contrôles de cohérence (polygones valides, pas de trou de timeline, pas de zone hors arborescence).

    python tools/zone_calibrator/server.py     # http://127.0.0.1:8000/
    python tools/plot_geometry.py              # régénère geometry_map.svg

### 6. Le runtime — `FlightNarrator.lua` & `TravelData.lua`

Le client ne charge que trois fichiers (listés dans `FlightNarrator.toc`) :

- `TravelData.lua` — **généré** par `tools/generate_travel_data.py` (ne pas éditer à la main) : la liste de tous les clips (`Audio`), la table de traduction des noms de nœuds EN → FR (`NodeNames`) et les timelines par route (`Travels`).
- `FlightNarrator.lua` — la logique de jeu : détection du décollage, recherche de la route, découpage en tranches et lecture des clips.
- `FlightNarrator.toc` — manifeste (Interface `11509`, version, ordre de chargement).

Comme WoW ne peut ni lister de fichiers ni lire des `.txt` à l'exécution, **tout est figé dans `TravelData.lua`** : ajouter un clip ou une route se fait en régénérant ce fichier.

    python tools/generate_travel_data.py       # à relancer après tout ajout de clip/route

Détails d'exécution notables :

- La voix démarre **3 secondes après le décollage**, le temps que le griffon s'arrache, puis la durée est découpée en `floor(durée / 75)` tranches égales ; chaque tranche tire un clip au hasard parmi toutes les zones qui la chevauchent, **sans jamais rejouer deux fois le même clip** au cours d'un vol (une tranche reste vide si tous les clips qu'elle peut atteindre ont déjà été joués).
- Un clip déjà entendu **moins de 5 minutes** plus tôt n'est pas reproposé, même sur un autre vol : enchaîner un aller-retour ne rejoue pas les mêmes narrations. Cette mémoire ne dure que le temps de la session (elle se réinitialise au `/reload`).
- La détection du vol **interroge `UnitOnTaxi`** en boucle (aucun événement Classic Era ne se déclenche au décollage) ; `TakeTaxiNode` est hooké pour capter la destination, et les noms de nœuds sont mis en cache à l'ouverture de la carte de taxi.
- Un jeton invalide les timers en attente dès que le vol se termine ou qu'un nouveau planning remplace l'ancien.

## Contribuer

Le projet est **grand ouvert aux contributions** — c'est même le meilleur moyen de faire grandir la couverture (plus de zones, plus de clips, plus de langues).

### Ce sur quoi on a besoin d'aide

- **Textes / narration** : écrire ou améliorer les narrations (lore Classic fidèle). C'est le goulot d'étranglement du projet.
- **Couverture audio** : rendre de nouveaux clips (crédits ElevenLabs) via `render_waves.py`.
- **Zones & sous-zones** : ajouter des villes, donjons, sous-régions et leurs polygones.
- **Cartographie** : affiner les polygones et les ancres avec le calibrateur.
- **Trajets** : compléter les routes manquantes (voir `connexions-absentes-de-travels.txt`).
- **Nouvelles langues** : les clips sont indexés par `région/sous-zone`, donc une traduction = de nouveaux textes + clips + une table de noms. Il faudra aussi ouvrir le runtime au multilangue.
- **Code / outillage** : corrections de bugs, tests, documentation.

### Règles de qualité (importantes)

- **Lore Classic uniquement** : pas d'événements d'après-Cataclysm, pas de noms ni de dates inventés.
- **Noms propres français officiels** (ex. « Baie-du-Butin », « Cartel Gentepression », « Jaina Portvaillant »).
- Un texte ne décrit pas un paysage : il raconte un lieu, un personnage, un événement, avec au moins un nom propre, et finit sur une chute mémorable.
- Respecter le format des lignes sources (`région/sous-zone/slug|Titre|paragraphe`) et les consignes de `prompts/`.

### Workflow

1. Fork + branche.
2. Éditer les **sources** (textes dans `tools/zones-fr/`, polygones via le calibrateur ou les scripts).
3. **Régénérer** les fichiers dérivés — jamais à la main :
   - `python tools/generate_zone_themes.py`
   - `python tools/generate_travel_zones.py`
   - `python tools/generate_travel_data.py`
4. Rendre les nouveaux clips (`python tools/render_waves.py`).
5. Vérifier : `python tools/validate_zones.py` et `python tools/check_timeline_coverage.py`.
6. Ouvrir une Pull Request.

### Fichiers générés (ne pas éditer à la main)

`TravelData.lua`, `DataFlights-frFR.lua` et les narrations `zones/**/*.txt` sont produits par les scripts ; les `geometry.txt` s'éditent via le calibrateur.

## Licence

Aucun fichier de licence n'est fourni : aucun droit n'est accordé par défaut. Demande à l'auteur avant toute réutilisation ou redistribution.
