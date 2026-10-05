# Prompt — Génération des thèmes de zone (lore library)

Ce prompt sert de contexte pour rédiger les textes de la bibliothèque de lore
(`tools/zones-fr/*.txt`). Chaque ligne suit le format :

    <région>/<sous-zone>/<slug>|<Titre>|<paragraphe>

Le paragraphe est une narration d'environ 50 secondes (~120 à 150 mots), en
français, lue par une voix de conteur pendant qu'un joueur survole le lieu en
monture. La génération est faite par l'agent (Cline), jamais par une API.

## Règle d'or : aucun texte banal

Un texte qui décrit un lieu doit **toujours le relier à un événement, un
personnage, une quête ou une guerre importante de World of Warcraft Classic**.
Ne jamais se contenter de décrire le paysage (« c'est une savane », « l'eau est
rare », « la vue est belle ») : cela n'apprend rien au joueur.

### Exemples à imiter
- « Bael Modan, le chantier nain » : un lieu précis (la fouille des nains de
  Ironforge), relié aux Titans, aux centaures et à l'histoire de la région.
- « La guerre du bois » : relie la zone à un conflit concret entre factions.

### Exemples à éviter
- « La vue depuis le pic » (ancienne version) : ne fait que décrire le paysage.
- « Les gardiens des hauteurs » (ancienne version) : parle de gardiens sans
  donner un seul nom ni une seule histoire.

## Sujets (quoi raconter, quoi éviter)

Ne pas multiplier les sujets génériques qui n'apprennent rien (une garnison,
une route, une forge, une auberge, un carrefour, une côte, un port, un paysage,
des sentinelles, un avant-poste…). Questionner chaque sujet : « ce thème
apprend-il quelque chose au joueur ? » Si non, le remplacer par un sujet ancré
dans le lore : un personnage nommé, une quête, un événement, une guerre, un lieu
précis. Bon test : le titre et le texte doivent contenir au moins un nom propre
de WoW.

## Contenu obligatoire (lore précis)

1. **Un ancrage lore concret** : un événement canonique (la Troisième Guerre,
   la Fracture, la chute du Puits d'éternité, l'exode de Lordaeron…), une
   faction, une guerre ou une quête.
2. **Des noms propres** : au moins un personnage ou lieu nommé avec son rôle
   (Thrall, Jaina Portvaillant, Magatha Grimtotem, le Cartel Gentepression,
   le clan Bloodfury, Windshear Crag…).
3. **L'enjeu du lieu** : pourquoi il compte (rempart militaire, route
   commerciale, sanctuaire, chantier, ligne de front).
4. **Une chute mémorable** en une phrase (constat, menace, promesse, devise).

## Règles de fidélité (ne jamais inventer)

- Rester dans le lore **Classic (vanilla)** : pas d'événements postérieurs
  (Cataclysm, etc.).
- Ne pas inventer de noms, dates ou événements : si une info n'est pas sûre,
  l'omettre ou rester général.
- Utiliser les **noms propres français officiels** de WoW quand ils existent
  (ex. « Cartel Gentepression », « Jaina Portvaillant », « Cairne Sabot-Sanglant »).

## Style

Registre soutenu mais parlé, rythme de conteur. Un seul bloc de prose fluide,
sans listes ni markdown. Finir fort.
