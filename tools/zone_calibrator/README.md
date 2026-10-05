# Calibrateur de zones

Petite WebApp (une fois / deux fois) pour recalibrer les polygones de
`zones/**/geometry.txt` contre les cartes de continents.

## Lancer

    python tools/zone_calibrator/server.py

Puis ouvrir http://127.0.0.1:8000/

## Utilisation

1. **Calibrer** : choisir un continent (les cartes `eastern_map.jpg` et
   `kalimdor_map.webp` sont chargées automatiquement). **Glisser les pastilles**
   (nœuds de trajet) sur les villes correspondantes : la carte se réaligne après
   2 pastilles, puis s'affine à chaque nouveau point. Un ajustement anisotrope
   aligné (échelle X/Y indépendante, sans rotation ni cisaillement) est
   recalculé à chaque fois ; les ancres sont persistées dans `localStorage`.
2. **Éditer les polygones** : cliquer un polygone pour l'activer, glisser un
   sommet pour le déplacer, cliquer sur un point de milieu d'arête pour insérer
   un sommet, touche `Suppr` pour supprimer le sommet sélectionné. Molette =
   zoom, glisser le fond = déplacement. Le commutateur **Général / Sous-zones**
   bascule entre régions et sous-zones (villes, donjons…). Les cases **Trajets
   Alliance / Trajets Horde** affichent ou masquent les trajets de vol (bleu =
   Alliance, rouge = Horde).
3. **Sauvegarder** : réécrit les `geometry.txt` modifiés (en-tête conservé,
   sommets réordonnés en sens horaire).

## Note

- Les cartes `eastern_map.jpg` (Royaumes de l'Est) et `kalimdor_map.webp`
  (Kalimdor) sont servies automatiquement si présentes à la racine ; sinon,
  utilisez le bouton « Image… ».
- Les coordonnées « ville » proviennent de `FlightData.lua` via
  `tools/map_transform.py` (repère continent 0-100, X est, Y sud).
