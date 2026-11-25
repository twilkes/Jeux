# Moteur libre pour Vlad Tepes Dracula (1997)

Réimplémentation du moteur du jeu, qui relit les fichiers d'origine fournis par le joueur
(même approche qu'OpenRCT2 ou ScummVM). Ce dossier ne contient que notre code :
aucune donnée du jeu ne doit y être ajoutée ni distribuée.

## Démarrage rapide (il faut le CD original)

Ce dépôt ne contient aucun fichier du jeu : il faut posséder le CD de *Vlad Tepes Dracula* (1997).

1. Installer Python 3 puis `pip install pygame numpy` (ou `pygame-ce` si pygame ne s'installe pas).
2. Faire une image du CD au format BIN/CUE et la placer à côté du dossier `moteur`, par exemple
   `..\jeu-00936-dracula_guerrier_carpates-pcwin\Dracula.bin` (chemin attendu par `lancer.bat`).
3. Lancer `lancer.bat`, ou `python -m vlad "<chemin>\Dracula.bin"` depuis ce dossier.
   On peut aussi extraire les fichiers une fois (`python outils/extraire.py <image> extrait`) puis lancer
   `python -m vlad extrait\donnees` (sans la musique du CD).

## Organisation

- `outils/` : scripts Python d'analyse et d'extraction des données.
- `docs/` : notes de rétro-ingénierie (formats, structures, logique).
- `extrait/` : sortie locale des outils (ignorée par git).

## Extraire les données

```
python outils/extraire.py "..\jeu-00936-dracula_guerrier_carpates-pcwin\Dracula.bin" extrait
```

Résultat : `extrait/donnees/` (fichiers du CD) et `extrait/png/` (planches graphiques en PNG).

## Lancer le prototype (Python + pygame)

1. Installer pygame une seule fois : `pip install pygame` (dans l'invite Anaconda ou une invite de commandes).
2. Dans l'invite Anaconda : `cd /d "H:\workspace\Jeux\Vlad Tepes Dracula\moteur"` puis
   `python -m vlad "..\jeu-00936-dracula_guerrier_carpates-pcwin\Dracula.bin"` (musique du CD incluse),
   ou `python -m vlad extrait\donnees` (sans musique). Si pygame ne s'installe pas : `pip install pygame-ce`.

Commandes : clic gauche ou rectangle = sélection, clic droit = déplacer ou attaquer un ennemi, S = stop,
flèches ou bord de l'écran = défiler, F = obstacles, P = musique suivante, Tab = comté suivant, Échap = quitter.

Règles de combat et sons : tirés de DRACULA.EXE (voir `vlad/stats_unites.json` et `docs/formats.md`).

Le code du moteur est dans `vlad/` : `donnees.py` lit les fichiers d'origine, `jeu.py` contient la boucle de jeu.

## Lissage et pack HD
- Touche L : change le mode d'affichage (pixels nets, tuiles lissées, lissage EPX, pack HD). Option `--lissage <mode>`.
- `python outils\export_hd.py extrait\donnees` écrit `extrait\hd_source\tuiles.png` et `sprites.png`.
  Agrandis-les avec une IA (même modèle, x2 ou x4, mêmes noms) et range le résultat dans `extrait\hd\` :
  le moteur active alors le mode « pack HD ». Usage personnel uniquement.

## Sièges
Chaque comté charge ses bâtiments d'origine (ponts, tours de guet, forts, châteaux). La bataille devient un siège du plus grand fort :
garnison dans la cour, archers sur les tours. Sélectionne bélier, catapulte et canon puis clic droit sur un mur ou la porte.

## Partie complète (conseil)
`lancer.bat` sans option ouvre le conseil : carte de Valachie, vous tenez Fagaras. Cliquez un comté ennemi voisin pour l'assiéger ;
victoire (Entrée) = le comté devient le vôtre, Échap en bataille = retraite. Le sceau rouge passe la semaine.
`lancer.bat --comte BRASOV` lance directement une bataille.
Onglets du panneau : Entraînement (recrues), Administration (armement, architecture), Constructions :
Réparer / Améliorer / Construire, choix du bâtiment (selon le niveau d'architecture) et du modèle, puis clic sur la mini-carte
(emplacement libre, fort à améliorer ou bâtiment endommagé). Un chantier par comté ; recliquer sur son bouton l'annule.
Un fort ou un château neuf augmente la production du comté ; les dégâts des sièges restent jusqu'à réparation.
Onglet Mouvements : clic sur une unité pour la choisir (clic droit : toutes), puis clic sur un comté voisin.
Les troupes partent au prochain sceau : vers un comté à vous elles s'y installent, vers un comté ennemi elles l'assiègent
(un assaut par comté visé, enchaînés). Recliquer une unité grisée annule son ordre.
L'ennemi joue aussi : chaque comté ennemi a sa garnison (visible dans Informations), un comté frontalier reçoit des renforts
chaque semaine, et à partir de la 7e semaine l'ennemi peut attaquer vos comtés. Vous défendez alors votre fort (vos troupes dedans,
l'ennemi force la porte avec ses béliers et catapultes) ; une défaite fait perdre le comté. Au plus 40 unités par camp sur le terrain,
le reste attend en réserve. Taille des garnisons : `ennemi.echelle` dans `vlad/tables_conseil.json` (0,5 = moitié des points d'origine).

## Nouvelle partie, sauvegarde, plein écran
- Comme dans le jeu d'origine, on commence sans territoire : la mission de départ est la prise du fort de Fagaras
  avec la petite troupe de Vlad (2 fantassins, 2 archers, 1 chevalier, 2 béliers). En cas d'échec, on peut réessayer.
- Au conseil : F5 sauvegarde la partie dans `moteur\sauvegardes\partie.sav`, F9 la recharge (une seule sauvegarde pour l'instant).
- F11 (ou Alt+Entrée) bascule en plein écran, image agrandie avec lissage ; option `--plein-ecran` pour démarrer ainsi.
- Batailles : brouillard de guerre (noir = jamais vu, voilé = déjà exploré, les ennemis n'apparaissent que dans le champ de vision
  de vos troupes ; B l'enlève). Il est gardé d'une bataille à l'autre et dans la sauvegarde.
- Molette (ou + / -) : zoom de x0,5 (vue deux fois plus haute) à x2. Double-clic sur une unité : toutes celles du même type à l'écran.
- Plein écran (F11) : à la résolution du bureau ; en écran large on voit plus loin sur les côtés. La fenêtre peut aussi être redimensionnée.

## Rendu, mini-carte, curseurs et conseil (2026-11-15)
- Lissage `xbr` (défaut sans pack HD ; L pour changer) : filtre à détection de contours (algorithme xBR) appliqué deux fois (x4),
  puis réduit x2 avec sur-échantillonnage ; les bords des sprites deviennent semi-transparents. Calcul dans un fil de fond
  (vlad/filtres.py, numpy requis) : la version EPX s'affiche en attendant. Au zoom avant (ou en grand écran), le monde est
  rendu avec les images x4 au lieu de x2.
- Mini-carte en haut à gauche (M) : un pixel par tuile, couleurs de ART/MINIMAP.WG (3 index de palette par tuile :
  visible, déjà vue, inconnue ; FUN_0044ac10 / FUN_00450440). Clic ou glisser : déplacer la vue ; clic droit : y envoyer les unités.
- Curseurs du jeu (BATTLE.ART, rectangles de FUN_00452c..) : normal, choisir (unité à soi), marcher, attaquer (X rouge),
  flèches de défilement aux bords.
- Conseil : textes rendus à la résolution de l'écran (nets), cadres recalés sur l'image, police réduite si le texte ne tient
  pas ; onglet Informations : production du comté sous les icônes.
- Mode xbr, suite : les tuiles de terrain passent par un agrandissement bicubique (Catmull-Rom) au lieu de xBR, plus efficace
  sur les textures bruitées ; la mini-carte est posée dans le cadre de pierre du panneau d'origine (BATTLE.ART, (0, 0xe60), en (16, 16)).
- Mode xbr : filtre des tuiles séparé de celui des unités, touche T (nettes par défaut, EPX, bicubiques, xBR).
