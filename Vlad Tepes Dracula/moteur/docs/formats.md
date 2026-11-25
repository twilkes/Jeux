# Vlad Tepes Dracula : inventaire et formats (étapes 1-2)

Source : `Dracula.bin/.cue` (image CD, piste 1 MODE1/2352 = données ISO9660, pistes 2 à 8 = musique CD audio).
Volume `DRACULA`, gravé le 1997-11-11 (CeQuadrat). Éditeur : ComputerHouse (Suède). 534 fichiers, dont ~430 de DirectX 3 (ignorés).

## Formats identifiés

| Fichiers | Format réel | Statut |
|---|---|---|
| `ART/*.ART` (5) | **PCX** 8 bits RLE + palette 256 couleurs en fin de fichier. Planches 640 px de large : BATTLE 640x9367, COUNCIL 640x3594, MENU 640x1951, CREDITS 640x524, LOADING 640x480 | Décodé à 100 % |
| `AUDIO/**/*.WG` (104) | **WAV RIFF** PCM 16 bits mono, 22050 Hz (bataille, extras) ou 16000 Hz (conseil, voix) | Lisible tel quel |
| `ART/MINIMAP.WG` | Pas un son : table de couleurs RGB 3 octets (1632 entrées) pour la minicarte | À confirmer |
| `CINEMA/*.CIN` (7) | **Smacker v2** (SMK2), 640x240 (lignes doublées à l'affichage), son 22050 Hz | Lisible par ffmpeg / libsmacker |
| `COUNTIES/*.MAP` (13) | Terrain 128x128 tuiles de 40x40 px + grille de passage 256x256 (voir plus bas) | Décodé, `outils/carte.py` |
| Pistes CD 2-8 | Musique Red Book, jouée via MCI (`play cdaudio from N to N+1`) | Extractible en WAV |
| `FILES.BIN` | Liste texte des fichiers à installer (`[MIN,3,0]`, `[TYP,129,21]`…) | Installeur |
| `ART/ANTQUA.TTF` | Police TrueType Antiqua | Standard |
| Sauvegardes | `Saves\*.c`, compressées très probablement avec **zlib 1.0.4** (intégré à l'exe) | À voir avec une sauvegarde |

## Exécutable `DRACULA.EXE` (617 Ko)

- PE32 Win32 GUI, compilé le 1997-11-10 avec **MSVC 5** (linker 5.2). Non compressé, non protégé : idéal pour Ghidra.
- Imports : DirectDraw (`DirectDrawCreate`), DirectSound, WinMM (MCI cdaudio + mmio pour les WAV), GDI (texte avec la police Antiqua), `smackw32.dll` (8 fonctions par ordinal).
- Bibliothèques reconnues : **RAD Smacker**, **zlib 1.0.4**, CRT Microsoft. Pas de moteur maison connu ni de Miles.
- Section `.data` de 3,3 Mo en mémoire (seulement 177 Ko sur disque) : gros tableaux statiques (cartes, unités).
- Remerciements trouvés : Microsoft (DirectX), RAD Game Tools (Smacker), Cubic Team (Cubic Player).
- Chaînes du jeu en français dans l'exe (version FR), noms de fichiers codés en dur.

## Ce que ça implique pour le nouveau moteur

- Graphismes, sons, vidéos : formats standards, quasiment rien à rétro-ingénierer. SDL2 + libsmacker (ou ffmpeg) suffisent.
- Le vrai travail : (1) découpage des planches de sprites (coordonnées probablement dans l'exe), (2) format exact des `.MAP`, (3) logique du jeu dans Ghidra.
- Couleur de transparence des sprites : cyan (visible sur BATTLE.ART).

## Format des cartes `COUNTIES/*.MAP`

Fichier de 327 680 octets = 81 920 entiers 32 bits little-endian, en deux blocs :

1. **Terrain** : 128 x 128 entiers (65 536 octets), ligne par ligne. Valeur = numéro de tuile dans
   `BATTLE.ART`, où les tuiles font **40 x 40 px**, 16 par ligne :
   `x = (n % 16) * 40`, `y = (n // 16) * 40`. Numéros observés : 0 à 1471.
   Une carte fait donc 5120 x 5120 px.
2. **Passage** : 256 x 256 entiers (262 144 octets), une case = 20 x 20 px (demi-tuile).
   `0` = libre, `0x40000` = bloqué (falaises, forêts, eau : vérifié visuellement sur Brasov).
   Valeur `0x1000000` rare (12 à 209 cases selon la carte) : sens inconnu, peut-être des points spéciaux.

## `BUILDING.MAP` : catalogue des fortifications

983 040 octets = **3 couches de tuiles 128x128** puis **3 grilles 256x256** (même codage que les comtés).
Ce n'est pas une carte jouable mais une planche de **modèles** : villages, bastions, forteresses et châteaux
de tailles croissantes, posés côte à côte sur de l'herbe. Le jeu les « tamponne » probablement sur la carte du comté.

- Couche 0 : sol. Couche 1 : murs et bâtiments. Couche 2 : toits (tuiles avec index 218 = transparent).
- Grille 0 : zones fonctionnelles. Valeurs vues : 0x40000, 0x80000, 0xC0000 (enceinte), 0x100000 (rempart extérieur),
  0x200000 et 0x800000 (emprises des bâtiments), 0x1000000 (douves / bord extérieur), 0x400000 (rare).
- Grille 1 : passage (0x40000 = bloqué) + 0x800000 sur les bâtiments.
- Grille 2 : contours extérieurs seulement (0x40000), surtout pour les grandes forteresses.
Sens exact de chaque drapeau : à confirmer dans Ghidra.

## Sprites de `BATTLE.ART`

- Lignes 0 à ~3707 : tuiles de terrain 40x40 (16 par ligne).
- À partir de y = 3708 : sprites posés sur fond cyan (index 218), sans table de coordonnées évidente dans l'exe
  (ni valeurs y, ni offsets y*640 cohérents). `outils/sprites.py` les détecte automatiquement : **1421 sprites**.
- Organisation visible : une ligne = une direction, une colonne = une image d'animation. Fantassins ~16x28,
  cavaliers et canons ~35-60 px, blocs de piquiers en formation, grands éléments (bâtiments ?) vers y 4643 et 7744.

### Animations des unités (retrouvées dans le code)

Décompilation Ghidra de DRACULA.EXE (copie locale : `extrait/dracula_decompile.c`, à ne pas distribuer).
- `FUN_00455220` remplit les tables au démarrage, `FUN_00455740` dessine une unité (BltFast avec couleur clé).
- Champs de l'unité (structure de 400 octets) : `+0x10` camp, `+0x20` animation, `+0x24` image, `+0x28` direction,
  `+0x188` type, `+0x180/+0x184` case (20 px), `+0x18/+0x1C` décalage fin.
- Rectangle source : `S = taille[type]`, `i = (3*type + anim)*3 + camp`,
  `x = X[i] + S*image`, `y = Y[i] + S*direction`, carré S x S (32 ou 64 px). Ancrage = `ancrage[type]`.
- Organisation : 8 lignes = 8 directions (N, NE, E, SE, S, SO, O, NO), colonnes = images. Anim 0 = déplacement,
  1 = attaque, 2 = mort/destruction. Camp 0 = joueur (bleu), 1 = ennemi (rouge), 2 = commun.
- Tables dans `outils/tables_unites.json`, export par `outils/unites.py` vers `extrait/unites/`.
- 12 types (0 à 11). Noms déduits des images, à confirmer : 0 archer, 1 fantassin, 3-4 chevaliers, 5 bélier,
  6 catapulte, 7 canon, 9 projectiles/effets, 10-11 variantes de bélier. Le jeu cite Archers, Chevaliers, Béliers,
  Catapultes, Canons.
- Anomalies : le type 4 camp 1 pointe hors de la planche (y = 9408 et 9920), et le type 4 anim 0 camp 0 ainsi que
  le type 5 anim 0 camp 2 tombent sur des images sans rapport. Probablement des entrées inutilisées.

## Règles de combat (tables de DRACULA.EXE)

Tables de 9 types x 2 niveaux, index `type*2 + niveau` (niveau = `DAT_007a24b0[type]`, 0 au départ).
Copie lisible : `vlad/stats_unites.json`. Types : 0 fantassin, 1 archer, 3 chevalier, 5 bélier, 6 catapulte, 7 canon
(confirmé par les tables : seuls 1, 6 et 7 ont une recharge et une précision de tir).

| Table | Adresse | Rôle |
|---|---|---|
| PV max | 0x493308 | 22/17/26/100/200/270 (type 0/1/3/5/6/7), régénération lente |
| Dégâts | 0x493230 | dégât = base + aléa(1..10), moins l'armure de la cible |
| Armure | 0x4932c0 | -2 dans l'état `+0x14 == 2` |
| Précision | 0x493278 | % de toucher la case visée, sinon ±1 case |
| Vitesse | 0x493350 | pixels par tick, -1 si PV bas (sauf catapulte et canon) |
| Portée | 0x493398 | x2 = cases de 20 px (corps à corps = 2 cases) |
| Vue | 0x4933e0 | x2+2 cases, x2+6 depuis une case de tour (drapeau 0x100000) |
| Recharge | 0x493428 | x8 ticks |
| Coûts | 0x493470, 0x4934b8 | comparés aux ressources du joueur |

Sons (tableau de 93 sons chargé par `FUN_00424850`, joués par `FUN_00425000`/`FUN_004250f0(id, x, y)`) :
tir par défaut Battle_05, canon Battle_02 (explose 1 fois sur 1000 : Battle_35), catapulte Battle_29, bélier Battle_37,
impact Battle_18. Voix quand on donne un ordre (`FUN_0045a190`) : fantassin 41/42/44/46, archer 39/40/43/45,
chevalier 27/30-34, bélier 38, catapulte 01, canon 04. Musique : pistes audio 2 à 8 du CD (MCI `play cdaudio`).

Hypothèse du prototype : 20 ticks par seconde (à vérifier contre l'original).

## Correction : ordre des cases des .MAP
Les grilles (tuiles 128x128 et drapeaux 256x256) sont rangées par colonnes : indice = x * côté + y
(confirmé dans DRACULA.EXE, fonction de dessin des unités : `DAT_00590b60[(cx/2)*0x80 + cy/2]`).
Lues dans ce sens, les transitions herbe/roche s'enchaînent correctement.

## Bâtiments (BUILDING.MAP + tables de DRACULA.EXE)
- BUILDING.MAP : 3 couches de tuiles + 3 grilles de drapeaux = **intact / endommagé / détruit** (pas sol/murs/toits).
- Gabarits 0x46b1a0..0x46b398 [cat*42+modèle] = x1,y1,x2,y2 en tuiles. Catégories : 0 pont/route, 1 tour de guet, 2 fort, 3 château.
- Positions 0x471958 / 0x480598 [comté*5040 + cat*1260 + modèle*30 + site]. Bâtiments de départ : FUN_00414790.
- Points de structure par tuile : 255 si une case porte 0x40000 (ou 0x100000 = tour) ; < 181 → couche 1, < 1 → couche 2 (FUN_00412110).
- Dégâts (FUN_00410eb0) : rand(1..6) + dégâts de l'unité, seulement bélier/catapulte/canon ; une tuile détruite tue les unités dessus
  (666 pts) et abîme ses voisines (180) ; sons Battle_18 (coup) et Battle_51 (effondrement).
- Drapeau 0x1000000 de la couche → 0x1040000 sur la carte ; 0x100000 = poste sur tour/rempart (vue x2+6).
- Portes 3x2 tuiles : FUN_0040f1b0 champs 0x9d0/0x9d1 (et 0x9d3/0x9d4 pour la 2e porte des châteaux).

## Conseil (COUNCIL.ART, couleur transparente 0,252,192)
- Écran 640x480 : parchemin (0,0,640,480) ; panneau à onglets en (15,30) : Entraînement, Mouvements, Constructions, Informations, Administration.
- 12 pièces de carte (FUN_004220b0), dessinées en (x+0x10e, y+0x20) ; 4 colonnes : joueur 0, ennemi 0x89, joueur survolé 0x112, ennemi survolé 0x19b.
- Frontières (matrice 12x12) et flèches de mouvement (position + direction 0-7) : FUN_00431d73. Comtés dans l'ordre alphabétique.
- Nouvelle partie (FUN_00416e10, FUN_00415320) : tous les comtés ennemis sauf Fagaras (n°3), an 1456 semaine 1,
  ressources 50/10/20/50/0, armée de départ à Fagaras : 2 fantassins, 2 archers, 1 chevalier, 2 unités de type 5.
- Propriétaire d'un comté : champ 0x006f204c (pas 0x7d7c octets) ; 0 = joueur, 1 = ennemi. Police : ART/ANTQUA.TTF.

## Économie (fin de semaine FUN_0043f401)
- Ressources (DAT_005e95e0, paires joueur/revenu) : or, bois, vivres, paysans, soldats.
- Production par comté possédé : or 0x470840, bois 0x470870, vivres 0x4708d0, paysans 0x4708a0 (12 entiers chacun).
- Recrutement FUN_00433821 : une recrue par type et par comté ; coût or 0x493470 + paysans 0x4934b8, durée 0x4931e8 semaines
  (indice type*2+niveau). Types proposés selon le niveau d'armement : 1 → 0,1,5 ; 2 → +3,8 ; 3 → +6 ; 4 → +7.
- Entretien : 1 vivre (types 0,1,8) ou 2 (3,5,6,7) par soldat ; vivres à 0 → 50 % de chances qu'un soldat déserte.
- Soins : +10 % des PV max par semaine. Améliorations : armement 0x48f318 (coût) / 0x48f330 (durée), architecture 0x48f348 / 0x48f358.

## Constructions (FUN_00437c8d, FUN_004255f9, FUN_0042f8d8, fin de chantier dans FUN_0043f401)
- Coûts par bâtiment [cat*42+modèle] : or 0x751fd8, bois 0x6f1d88, semaines 0x7509f0 (remplis par FUN_00432651).
  Ponts 5/2/1, 10/5/2 ou 20/8/3 selon le gabarit ; tours 50/10/4 ; forts 250/50/8, 500/100/10, 750/150/12 ;
  châteaux 1000/250/15, 1500/330/20, 2100/480/25, 1300/270/17, 1700/255/22, 2500/500/27.
- Niveau d'architecture N : catégories 0..N-1 ; ponts : 1 type au niveau 1, 3 ensuite ; tours 1 modèle, forts 3, châteaux 6.
- Emplacements : nombre 0x471178[comté*168+cat*42+modèle], positions 0x471958/0x480598 (en tuiles = pixels de la mini-carte).
  Forts et châteaux partagent leurs numéros d'emplacement ; tours : un numéro pris l'est pour tous les modèles ; ponts : position libre.
- Amélioration : fort -> château ou modèle supérieur au même emplacement ; prix = 1,25 x (différence d'or, de bois, de semaines).
- Réparation : prix = dégâts / structure totale (0x48f208) x coût x 1,1, au moins 1.
- Fin de construction d'un fort (x1,05 / 1,07 / 1,10) ou d'un château (x1,2 / 1,32 / 1,4 / 1,25 / 1,35 / 1,45) :
  les 4 productions du comté sont multipliées.
- Planche : mini-cartes 128x128 (0x751aa0), repères 0x752278 (existants) / 0x750868 (disponibles), aperçus 0x6f1908.

## Mouvements (FUN_00437650 affichage, FUN_00435302 clics, FUN_0044090d ordre, FUN_00440ca1 fin de semaine)
- Unités du comté : types 0x6f20b0, états 0x6f3050 (0 au repos, 1 choisie, 2 en route), destination 0x6f3ff0, origine 0x6f4f90.
- Grille de 4 colonnes en (0x3a + 0x2a*col, 0x54 + 0x1c*ligne), défilement au-delà de 9 lignes.
- Icônes : choisie (0x205, 0x6a8 + 0x1c*type), repos (0x217, 0x332 + 0x1c*type), en route (0x22b, 0xa6a + 0x1c*type), 0x2a x 0x1c.
- Destination valide seulement si voisine (0x752720[origine*12+dest]) ; flèche sur la carte tant que l'ordre tient.

## Tour de l'ennemi (FUN_0043efed attaques, FUN_0043ea67 composition, FUN_0043ed9d renforts)
- Garnison cible par comté en points 0x48f3d8 : 300,130,70,180,220,300,400,300,1500,90,250,200 ;
  points par unité (FUN_0041a6d0) : fantassin, archer, canon 5 ; chevalier 3 ; bélier 2 ; catapulte 4.
- Renforts : chaque semaine (après la semaine 3 de 1456), un comté (tour à tour) ennemi et frontalier est complété et ses bâtiments réparés.
- Attaque, à partir de la semaine 7 de 1456, pour chaque comté ennemi frontalier (ordre aléatoire) contre un comté voisin du joueur :
  force = somme des poids (fantassin/archer 1, chevalier 3, catapulte 4, canon 5, autres 2) ; 20 % de chances d'être « agressif » (ratio 1) ;
  sinon ratio = 0,75 F / (0,75 F + défense). Probabilité % = max(5, 5 x ratio + compteur), compteur +1 par semaine, remis à 0 à chaque attaque.
  Budget = F x (3..7) / 10, attaque seulement si > 15, plafonné à 15 avant la semaine 20 de 1456 puis 40 en 1456 ; un comté visé une fois par tour.
- Composition : tirage 25 % fantassin (coût 5), 25 % archer (5), 20 % chevalier (3), 10 % bélier (2), 10 % canon (5), 10 % catapulte (4) ; au moins un bélier.
- Agents (type 8) : un agent du joueur dans un comté ennemi devient espion (0x6f20a4) ; non repris dans le moteur.

## ART/MINIMAP.WG (mini-carte de bataille)
4896 octets = 1632 tuiles x 3 index de la palette de BATTLE.ART : couleur si la tuile est visible, déjà explorée, inconnue (0 = noir).
Lu par FUN_0044ac10 ; FUN_00450440 dessine 128x128 pixels (un par tuile) en (16, 16) selon le brouillard, puis le cadre de la vue.

## Curseurs de bataille (BATTLE.ART, FUN_00452c.. en fin de dessin)
- normal (masse) : (0xf0, 0xe60) 39x39 ; choisir (cadre pointillé) : (0xf0, 0xfcd) 24x24, centré
- marcher (flèche grise) : (0xf0 ou 0x10b, 0xf8f) 27x27 ; attaquer (X rouge) : (0xf0 ou 0x10f, 0xfaa) 31x35, centré
- défilement : 8 flèches en x 0xf0, y = 0xe87 N, 0xead NE, 0xecc E, 0xeec SE, 0xf0b S, 0xf31 SO, 0xf50 O, 0xf70 NO
