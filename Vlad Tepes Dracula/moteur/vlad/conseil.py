"""Écran du conseil : la carte de Valachie et ses 12 comtés (couche stratégique), d'après DRACULA.EXE.

Mise en page, pièces de carte, frontières et flèches : voir tables_conseil.json.
Gère la conquête, l'économie, l'entraînement, l'administration et les constructions (constructions.py).
"""
import copy, io, json, os, pickle, random
import pygame
from . import batiments, donnees
from .constructions import Chantiers

ICI = os.path.dirname(os.path.abspath(__file__))
CLE = (0, 252, 192)  # couleur transparente du conseil (FUN_0041b890(0, 0xfc, 0xc0))
ENCRE = (70, 35, 15)
NOMS_RESSOURCES = ['Or', 'Bois', 'Vivres', 'Paysans', 'Soldats']  # d'après les icônes et l'usage dans le code
NOMS_TYPES = {0: 'fantassin', 1: 'archer', 3: 'chevalier', 5: 'bélier', 6: 'catapulte', 7: 'canon', 8: 'unité 8'}
JOUABLES = (0, 1, 3, 5, 6, 7)  # le type 8 n'a ni sprites ni caractéristiques de combat


class Police:
    """Police mesurée en unités de l'écran d'origine (640x480) mais rendue à la résolution de l'écran :
    le texte reste net au lieu d'être agrandi avec l'image du conseil."""
    _cache = {}

    def __init__(self, ttf, taille):
        self.ttf, self.taille = ttf, taille
        self.f = self.rendu(2)

    def rendu(self, s):
        cle = (self.ttf is not None, self.taille, round(s, 2))
        if cle not in Police._cache:
            px = max(6, int(round(self.taille * s)))
            Police._cache[cle] = pygame.font.Font(io.BytesIO(self.ttf), px) if self.ttf else \
                pygame.font.Font(None, int(px * 1.25))
        return Police._cache[cle]

    def size(self, txt):
        w, h = self.f.size(txt)
        return w / 2, h / 2

    def get_linesize(self):
        return self.f.get_linesize() / 2

    def autre(self, taille):
        return Police(self.ttf, taille)


def rect(r):
    return pygame.Rect(r[0], r[1], r[2] - r[0], r[3] - r[1])


class Conseil:
    def __init__(self, source):
        w, h, px, pal = donnees.lire_pcx(source.lire('ART/COUNCIL.ART'))
        brut = pygame.image.frombuffer(bytes(px), (w, h), 'P')
        brut.set_palette([tuple(pal[i * 3:i * 3 + 3]) for i in range(256)])
        self.planche = brut.convert()
        self.planche.set_colorkey(CLE)
        self.t = json.load(open(os.path.join(ICI, 'tables_conseil.json'), encoding='utf-8'))
        try:
            ttf = source.lire('ART/ANTQUA.TTF')
            Police(ttf, 15)
        except (KeyError, FileNotFoundError, pygame.error):
            ttf = None
        self.police, self.grande, self.petite = Police(ttf, 15), Police(ttf, 20), Police(ttf, 11)
        self.textes = []  # textes de l'image en cours : dessinés à la fin, à la résolution de l'écran
        self.surface = pygame.Surface((640, 480)).convert()
        # masques des pièces pour savoir quel comté est sous la souris
        self.masques = []
        for x, y, l, t, r, b in self.t['pieces']:
            piece = self.planche.subsurface(rect((l, t, r, b)))
            self.masques.append((pygame.Rect(x + 0x10e, y + 0x20, r - l, b - t), pygame.mask.from_surface(piece)))
        self.voisins = {}
        for i, j, x, y, d in self.t['liens']:
            self.voisins.setdefault(i, {})[j] = (x, y, d)
        self.catalogue = batiments.Catalogue(source)
        self.nouvelle_partie()

    def nouvelle_partie(self):
        dep = self.t['depart']
        self.proprio = [1] * 12  # 0 = joueur, 1 = ennemi (champ 0x006f204c) : on commence sans territoire
        self.mission = True  # mission de départ : prendre Fagaras avec la petite armée de Vlad
        self.annee, self.semaine = self.t['date']['annee'], self.t['date']['semaine']
        self.ressources = [v[0] for v in self.t['ressources']['valeurs']]
        self.revenus = [v[1] for v in self.t['ressources']['valeurs']]
        self.armees = {c: [] for c in range(12)}  # types d'unités du joueur stationnées dans chaque comté
        self.ordres = {c: [] for c in range(12)}  # par unité : None, 'sel' (choisie) ou comté de destination
        self.assauts, self.assaut = [], None  # batailles de la semaine : assauts du joueur puis attaques ennemies
        pts = dep['points_initiaux']  # FUN_004152d0 : 100 à 179 points, Rasova 400 ; Fagaras : 3 fantassins et 1 chevalier
        self.garnisons = {c: self.recruter_garnison(c, points=pts.get(str(c), random.randrange(*pts['autre'])))
                          for c in range(12)}
        self.garnisons[dep['comte_joueur']] = list(dep['garnison_mission'])
        self.brouillards = {}  # comté -> tuiles 128x128 : 2 jamais vue, 1 explorée, 0 vue (grille 0x7574b8 du jeu)
        self.tension, self.tour_renfort = 0, 0  # DAT_00753278 (monte chaque semaine) et DAT_0075327c
        self.defilement = 0
        self.commandes = {}  # (comté, type) -> semaines écoulées (une seule recrue par type et par comté à la fois)
        self.niveau_armement = 1
        self.niveau_architecture = 1
        self.ameliorations = {}  # 'armement' / 'architecture' -> semaines écoulées
        self.niveaux = {}  # type -> niveau des tables de caractéristiques (0 ou 1)
        self.production = copy.deepcopy(self.t['economie']['production'])  # par comté, change avec les forts et châteaux
        self.chantiers = Chantiers(self, self.catalogue)
        self.ressources[4] = self.nb_soldats()
        self.choisi = dep['comte_joueur']
        self.survol = None
        self.onglet = 3
        self.sceau_appuye = False
        self.message = ('Mission de départ : vous n\'avez encore aucun territoire. Prenez le fort de Fagaras '
                        'avec votre petite troupe (cliquez sur la carte). F9 : charger une partie.')

    def brouillard(self, c):
        """Brouillard de guerre du comté, conservé d'une bataille à l'autre ; vos comtés sont connus d'avance."""
        if c not in self.brouillards:
            self.brouillards[c] = bytearray([1 if self.proprio[c] == 0 else 2]) * (128 * 128)
        return self.brouillards[c]

    def mission_depart(self):
        dep = self.t['depart']
        return ('bataille', dep['comte_joueur'], None, [t for t in dep['armee'] if t in JOUABLES])

    # --- sauvegarde ----------------------------------------------------------------------------
    ETAT = ('proprio', 'mission', 'annee', 'semaine', 'ressources', 'revenus', 'armees', 'ordres', 'garnisons',
            'tension', 'tour_renfort', 'commandes', 'niveau_armement', 'niveau_architecture', 'ameliorations',
            'niveaux', 'production', 'choisi', 'onglet', 'brouillards')
    FICHIER = os.path.join(ICI, '..', 'sauvegardes', 'partie.sav')

    def sauver(self, chemin=None):
        chemin = chemin or self.FICHIER
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        ch = self.chantiers
        etat = {k: getattr(self, k) for k in self.ETAT}
        etat['chantiers'] = {'batiments': ch.batiments, 'chantier': ch.chantier}
        with open(chemin, 'wb') as f:
            pickle.dump({'version': 1, 'etat': etat}, f)
        self.message = 'Partie sauvegardée (semaine %d, %d). F9 pour la recharger.' % (self.semaine, self.annee)

    def charger_partie(self, chemin=None):
        chemin = chemin or self.FICHIER
        if not os.path.exists(chemin):
            self.message = 'Aucune sauvegarde trouvée (F5 pour sauvegarder).'
            return False
        with open(chemin, 'rb') as f:  # fichier écrit par sauver() sur ce même PC
            etat = pickle.load(f)['etat']
        for k in self.ETAT:
            if k in etat:  # une sauvegarde plus ancienne peut ne pas tout contenir
                setattr(self, k, etat[k])
        self.chantiers.batiments = etat['chantiers']['batiments']
        self.chantiers.chantier = etat['chantiers']['chantier']
        self.assauts, self.assaut = [], None
        self.message = 'Partie chargée : semaine %d de l\'an %d.' % (self.semaine, self.annee)
        return True

    # --- logique -------------------------------------------------------------------------------
    def comte_sous(self, pos):
        for i, (r, m) in enumerate(self.masques):
            if r.collidepoint(pos) and m.get_at((pos[0] - r.x, pos[1] - r.y)):
                return i
        return None

    @staticmethod
    def nom_comte(c):
        return donnees.COMTES[c].capitalize()

    def defenses(self, c):
        noms = {}
        for b in self.chantiers.batiments[c]:
            if b['cat'] >= 1:
                n = batiments.NOMS[b['cat']]
                noms[n] = noms.get(n, 0) + 1
        pluriel = {'tour de guet': 'tours de guet', 'château': 'châteaux'}
        return ['%d %s' % (k, pluriel.get(n, n + 's')) if k > 1 else n for n, k in noms.items()]

    def attaquable(self, i):
        return self.proprio[i] == 1 and any(self.proprio[j] == 0 for j in self.voisins.get(i, {}))

    def nb_soldats(self):
        return sum(len(a) for a in self.armees.values())

    def eco(self, nom, t, niveau=None):
        if niveau is None:
            niveau = self.niveaux.get(t, 0)
        return self.t['economie'][nom][t * 2 + niveau]

    def types_entrainables(self):
        n = str(min(5, self.niveau_armement))
        return [t for t in self.t['economie']['types_par_niveau'][n] if t in JOUABLES]

    def commander(self, comte, t):
        """Clic sur une recrue : la commander (payée tout de suite) ou annuler (remboursée), comme FUN_00433821."""
        cle = (comte, t)
        nom = NOMS_TYPES.get(t, '?')
        if cle in self.commandes:
            del self.commandes[cle]
            self.ressources[0] += self.eco('cout_or', t)
            self.ressources[3] += self.eco('cout_paysans', t)
            self.message = 'Recrutement du %s annulé.' % nom
        elif self.ressources[0] >= self.eco('cout_or', t) and self.ressources[3] >= self.eco('cout_paysans', t):
            self.commandes[cle] = 0
            self.ressources[0] -= self.eco('cout_or', t)
            self.ressources[3] -= self.eco('cout_paysans', t)
            self.message = 'Un %s sera prêt dans %d semaine(s).' % (nom, self.eco('duree', t) + 1)
        else:
            self.message = 'Pas assez d\'or ou de paysans pour un %s.' % nom

    def ameliorer(self, quoi):
        """Bouton Améliorer (FUN_00433a3d) : lancer l'amélioration (payée en or) ou l'annuler (remboursée)."""
        ad = self.t['administration']
        niveau = self.niveau_armement if quoi == 'armement' else self.niveau_architecture
        if niveau >= ad[quoi + '_max']:
            self.message = 'Niveau maximal atteint.'
            return
        cout = ad[quoi + '_cout'][niveau]
        if quoi in self.ameliorations:
            del self.ameliorations[quoi]
            self.ressources[0] += cout
            self.message = 'Amélioration de l\'%s annulée.' % quoi
        elif self.ressources[0] >= cout:
            self.ameliorations[quoi] = 0
            self.ressources[0] -= cout
            self.message = 'Amélioration de l\'%s lancée : %d semaines.' % (quoi, ad[quoi + '_duree'][niveau] + 1)
        else:
            self.message = 'Il faut %d pièces d\'or pour améliorer l\'%s.' % (cout, quoi)

    def avancer_ameliorations(self):
        ad = self.t['administration']
        msg = []
        for quoi in list(self.ameliorations):
            self.ameliorations[quoi] += 1
            niveau = self.niveau_armement if quoi == 'armement' else self.niveau_architecture
            if self.ameliorations[quoi] > ad[quoi + '_duree'][niveau]:
                del self.ameliorations[quoi]
                if quoi == 'armement':
                    for t in ad['armement_effets'].get(str(niveau), []):
                        self.niveaux[t] = 1
                    self.niveau_armement += 1
                    nouveaux = [NOMS_TYPES[t] for t in self.types_entrainables() if t in JOUABLES]
                    msg.append('Armement niveau %d : troupes améliorées, recrutables : %s.' % (self.niveau_armement, ', '.join(nouveaux)))
                else:
                    self.niveau_architecture += 1
                    msg.append('Architecture niveau %d.' % self.niveau_architecture)
        return msg

    def fin_de_tour(self):
        """Fin de semaine (FUN_0043f401) : améliorations, recrues, production, entretien, désertions."""
        eco = self.t['economie']
        ia = self.ia_ennemie()
        mouvements = self.deplacer()
        progres = self.avancer_ameliorations() + self.chantiers.semaine()
        nouvelles = []
        for (c, t) in list(self.commandes):
            self.commandes[c, t] += 1
            if self.commandes[c, t] > self.eco('duree', t):
                del self.commandes[c, t]
                self.armees[c].append(t)
                nouvelles.append(NOMS_TYPES.get(t, '?'))
        self.revenus = [0, 0, 0, 0, 0]
        for c in range(12):
            if self.proprio[c] == 0:
                for k, nom in enumerate(('or', 'bois', 'vivres', 'paysans')):
                    self.ressources[k] += self.production[nom][c]
                    self.revenus[k] += self.production[nom][c]
        self.semaine += 1
        if self.semaine > 52:
            self.semaine, self.annee = 1, self.annee + 1
        msg = ['Semaine %d de l\'an de grâce %d.' % (self.semaine, self.annee)] + mouvements
        if nouvelles:
            msg.append('Recrues prêtes : %s.' % ', '.join(nouvelles))
        msg += progres + ia
        # entretien : chaque soldat mange ; sans vivres, une chance sur deux qu'un soldat déserte
        for c in range(12):
            for t in self.armees[c]:
                self.ressources[2] -= eco['entretien'].get(str(t), 1)
                if self.ressources[2] <= 0 and random.randrange(100) < 50:
                    self.ressources[2] = max(self.ressources[2], 0)
                    camps = [k for k in range(12) if self.armees[k]]
                    k = random.choice(camps)
                    self.armees[k].pop(random.randrange(len(self.armees[k])))
                    msg = ['Famine : un soldat a déserté à %s !' % donnees.COMTES[k].capitalize()]
                    break
        self.ressources[2] = max(self.ressources[2], 0)
        self.ressources[4] = self.nb_soldats()
        self.message = ' '.join(msg)

    def comte_attaquant(self, cible):
        """Comté du joueur, voisin de la cible, d'où part l'assaut : celui choisi, sinon la plus grosse armée."""
        voisins = [j for j in self.voisins.get(cible, {}) if self.proprio[j] == 0]
        if self.choisi in voisins and self.armees[self.choisi]:
            return self.choisi
        voisins = [j for j in voisins if self.armees[j]]
        return max(voisins, key=lambda j: len(self.armees[j])) if voisins else None

    def resultat_bataille(self, comte, origine, victoire, survivants, ennemis=None):
        """Retour de bataille : les survivants occupent le comté conquis, ou rentrent chez eux."""
        nom = donnees.COMTES[comte].capitalize()
        if origine is None:  # mission de départ
            if victoire:
                self.mission = False
                self.proprio[comte] = 0
                self.armees[comte] = list(survivants)
                self.garnisons[comte] = []
                self.choisi = comte
                self.message = ('%s est à vous : Vlad a enfin une terre. Recrutez, bâtissez, puis attaquez vos voisins. '
                                'F5 sauvegarde, F9 recharge.' % nom)
            else:
                self.garnisons[comte] = list(self.t['depart']['garnison_mission'])
                self.message = 'La prise de %s a échoué. Cliquez sur %s pour réessayer.' % (nom, nom)
            self.ressources[4] = self.nb_soldats()
            return
        if self.assaut is None:  # assaut direct depuis la carte : toute l'armée part, la bataille prend une semaine
            self.armees[origine] = []
            self.ordres[origine] = []
            self.fin_de_tour()
        else:  # assaut ordonné dans l'onglet Mouvements : la semaine est déjà passée
            self.assaut = None
            self.message = ''
        if victoire:
            self.proprio[comte] = 0
            self.armees[comte] = list(survivants)
            self.ordres[comte] = []
            self.brouillards[comte] = bytearray([min(v, 1) for v in self.brouillard(comte)])
            self.garnisons[comte] = []
            self.choisi = comte
            self.message = ('%s est à vous. ' % nom + self.message).strip()
            if all(p == 0 for p in self.proprio):
                self.message = 'La Valachie entière vous appartient !'
        else:
            self.armees[origine] += list(survivants)
            if ennemis is not None:
                self.garnisons[comte] = list(ennemis)
            self.message = 'L\'assaut sur %s a échoué. ' % nom + self.message
        self.ressources[4] = self.nb_soldats()

    def evenement(self, e):
        """Renvoie ('quitter',), ('bataille', comte) ou None."""
        if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
            return ('quitter',)
        if e.type == pygame.KEYDOWN and e.key == pygame.K_F5:
            if self.mission:
                self.message = 'Prenez d\'abord Fagaras avant de sauvegarder.'
            else:
                self.sauver()
            return None
        if e.type == pygame.KEYDOWN and e.key == pygame.K_F9:
            self.charger_partie()
            return None
        if e.type == pygame.MOUSEMOTION:
            self.survol = self.comte_sous(e.pos)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            sceau = pygame.Rect(self.t['sceau']['pos'], rect(self.t['sceau']['rect']).size)
            if self.mission:
                if sceau.collidepoint(e.pos) or self.comte_sous(e.pos) is not None:
                    return self.mission_depart()
                return None
            if sceau.collidepoint(e.pos):
                self.sceau_appuye = True
                return None
            ox, oy = self.t['onglets']['pos']
            if pygame.Rect(ox, oy, 50, 340).collidepoint(e.pos):  # icônes des onglets à gauche du panneau
                self.onglet = min(4, max(0, (e.pos[1] - oy - 30) // 66))
                return None
            if self.onglet == 4:
                for quoi, b in zip(('armement', 'architecture'), self.t['administration']['boutons']):
                    if pygame.Rect(ox + b[0], oy + b[1], b[2] - b[0], b[3] - b[1]).collidepoint(e.pos):
                        self.ameliorer(quoi)
                        return None
            if self.onglet == 2 and self.clic_constructions(e.pos, ox, oy):
                return None
            if self.onglet == 1 and self.clic_mouvements(e.pos, ox, oy):
                return None
            if self.onglet == 0:
                for row, t in enumerate(self.types_entrainables()):
                    if pygame.Rect(ox + 0x38, oy + 0x62 + row * 0x1e, 0x31, 0x1d).collidepoint(e.pos):
                        if self.proprio[self.choisi] == 0:
                            self.commander(self.choisi, t)
                        return None
            c = self.comte_sous(e.pos)
            if c is None:
                return None
            nom = donnees.COMTES[c].capitalize()
            if self.onglet == 1 and self.choisi is not None and 'sel' in self.etats(self.choisi):
                self.ordonner(c)
                return None
            if self.proprio[c] == 0:
                self.choisi = c
                self.message = '%s : votre comté.' % nom
            elif self.attaquable(c):
                origine = self.comte_attaquant(c)
                if origine is None:
                    self.message = 'Aucune armée dans un comté voisin de %s : recrutez d\'abord.' % nom
                else:
                    return ('bataille', c, origine, list(self.armees[origine]))
            else:
                self.message = '%s est trop loin : il faut d\'abord un comté voisin.' % nom
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3 and self.onglet == 1:
            self.tout_choisir()
        elif e.type == pygame.MOUSEWHEEL and self.onglet == 1:
            self.defilement = max(0, self.defilement - e.y)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.sceau_appuye:
            self.sceau_appuye = False
            self.fin_de_tour()
            return self.prochain_assaut()
        return None

    # --- dessin --------------------------------------------------------------------------------
    def blit(self, pos, r):
        self.surface.blit(self.planche, pos, rect(r))

    def texte(self, txt, pos, police=None, centre=False, couleur=ENCRE):
        self.textes.append((str(txt), pos, police or self.police, centre, couleur))

    @staticmethod
    def couper(txt, police, largeur):
        lignes = []
        for paragraphe in str(txt).split('\n'):
            ligne = ''
            for mot in paragraphe.split():
                essai = (ligne + ' ' + mot).strip()
                if police.size(essai)[0] > largeur and ligne:
                    lignes.append(ligne)
                    ligne = mot
                else:
                    ligne = essai
            lignes.append(ligne)
        return lignes

    def texte_cadre(self, txt, zone, police=None, couleur=ENCRE, marge=5, centre_v=False):
        """Texte sur plusieurs lignes dans un cadre (x1, y1, x2, y2) : la police rétrécit jusqu'à ce que tout tienne,
        sinon la dernière ligne finit par « … ». Renvoie le bas du texte."""
        police = police or self.police
        x1, y1, x2, y2 = zone
        largeur, hauteur = x2 - x1 - 2 * marge, y2 - y1 - 2 * marge
        taille = police.taille
        while True:
            p = police if taille == police.taille else police.autre(taille)
            lignes = self.couper(txt, p, largeur)
            if len(lignes) * p.get_linesize() <= hauteur + 2 or taille <= 9:
                break
            taille -= 1
        n = max(1, int((hauteur + 2) // p.get_linesize()))
        if len(lignes) > n:
            lignes = lignes[:n]
            while lignes[-1] and p.size(lignes[-1] + ' …')[0] > largeur:
                lignes[-1] = lignes[-1].rsplit(' ', 1)[0] if ' ' in lignes[-1] else lignes[-1][:-1]
            lignes[-1] += ' …'
        h = len(lignes) * p.get_linesize()
        y = y1 + marge + (max(0, hauteur - h) / 2 if centre_v else 0)
        for l in lignes:
            self.texte(l, (x1 + marge, y), p, couleur=couleur)
            y += p.get_linesize()
        return y

    def poser_textes(self, ecran):
        """Dessine les textes de l'image à la résolution de l'écran (nets, même agrandis)."""
        s = ecran.get_width() / 640
        for txt, (x, y), police, centre, couleur in self.textes:
            img = police.rendu(s).render(txt, True, couleur)
            pos = (x * s, y * s)
            ecran.blit(img, img.get_rect(center=(int(pos[0]), int(pos[1]))) if centre else (int(pos[0]), int(pos[1])))
        self.textes = []

    def dessiner(self, ecran, batiments_par_comte=None):
        t = self.t
        self.textes = []
        self.surface.fill((0, 0, 0))
        self.blit((0, 0), (0, 0, 640, 480))
        # panneau de gauche
        ox, oy = t['onglets']['pos']
        self.blit((ox, oy), t['onglets']['rects'][self.onglet])
        self.panneau(ox, oy, batiments_par_comte)
        # carte des comtés
        for i, (x, y, l, tp, r, b) in enumerate(t['pieces']):
            k = (1 if i == self.survol else 0) + 2 * self.proprio[i]
            col = t['colonnes'][k]
            self.blit((x + 0x10e, y + 0x20), (l + col, tp, r + col, b))
        if self.choisi is not None:
            for j, (x, y, d) in self.voisins.get(self.choisi, {}).items():
                fl = t['fleches_ennemi' if self.proprio[j] else 'fleches_joueur'][d]
                self.blit((x, y), fl)
        for c in range(12):  # ordres de mouvement en attente
            for j in {d for d in self.etats(c) if isinstance(d, int)}:
                x, y, d = self.voisins[c][j]
                self.blit((x, y), t['fleches_ennemi' if self.proprio[j] else 'fleches_joueur'][d])
        if self.survol is not None:
            r = self.masques[self.survol][0]
            self.texte(donnees.COMTES[self.survol].capitalize(), (r.centerx, r.centery), self.grande, centre=True)
        # ressources, date, sceau
        rs = t['ressources']
        self.blit(rs['pos'], rs['rect'])
        for k, v in enumerate(self.ressources):
            self.texte(v, (0x13e + k * 0x26 + 8, 0x139 + 6), centre=True)
            if k < 4 and self.revenus[k]:
                self.texte('+%d' % self.revenus[k], (0x13e + k * 0x26 + 8, 0x148 + 8), self.petite, centre=True)
        self.texte_cadre(self.message, rs['texte'])
        self.blit(t['date']['pos'], t['date']['rect'])
        self.texte(self.annee, (0x233 + 10, 0x113 + 6), centre=True)
        self.texte(self.semaine, (0x233 + 10, 0x13d), centre=True)
        sc = t['sceau']
        self.blit(sc['pos'], sc['appuye'] if self.sceau_appuye else sc['rect'])
        ecran.blit(pygame.transform.smoothscale(self.surface, ecran.get_size()), (0, 0))
        self.poser_textes(ecran)

    def panneau(self, ox, oy, batiments_par_comte):
        if self.onglet == 0:
            return self.panneau_entrainement(ox, oy)
        if self.onglet == 4:
            return self.panneau_administration(ox, oy)
        if self.onglet == 2:
            return self.panneau_constructions(ox, oy)
        if self.onglet == 1:
            return self.panneau_mouvements(ox, oy)
        # onglet Informations : trois cadres de l'image d'origine (comté, ordres possibles, aide)
        c = self.survol if self.survol is not None else self.choisi
        if c is None:
            self.texte_cadre('Survolez ou choisissez un comté.', (ox + 56, oy + 349, ox + 240, oy + 385), self.petite,
                             centre_v=True)
            return
        if self.proprio[c] == 0:  # production de la semaine sous les icônes or, bois, vivres, paysans
            for k, nom in enumerate(('or', 'bois', 'vivres', 'paysans')):
                self.texte(self.production[nom][c], (ox + 0x4d + k * 0x30, oy + 0x87), self.petite, centre=True)
        y = self.texte_cadre(self.nom_comte(c), (ox + 56, oy + 155, ox + 240, oy + 180), self.police,
                             couleur=(120, 20, 10))
        lignes = ['À vous' if self.proprio[c] == 0 else 'Aux mains de l\'ennemi']
        b = self.defenses(c)
        lignes.append('Défenses : ' + (', '.join(b) if b else 'aucune'))
        if self.proprio[c] == 0:
            lignes.append('Armée : ' + (self.resume(self.armees[c]) or 'aucune'))
        else:
            lignes.append('Garnison : ' + (self.resume(self.garnisons[c]) or 'aucune'))
        self.texte_cadre('\n'.join(lignes), (ox + 56, y - 5, ox + 240, oy + 266), self.petite.autre(13))
        if self.proprio[c] == 0:
            aide = 'Onglets Entraînement et Constructions pour renforcer ce comté.'
        else:
            aide = 'Cliquez pour attaquer.' if self.attaquable(c) else 'Hors de portée : il faut un comté voisin.'
        self.texte_cadre(aide, (ox + 56, oy + 271, ox + 240, oy + 336), self.petite.autre(13), centre_v=True)

    @staticmethod
    def resume(types):
        noms = {}
        for t in types:
            noms[t] = noms.get(t, 0) + 1
        return ', '.join('%d %s%s' % (n, NOMS_TYPES.get(t, '?'), 's' if n > 1 else '') for t, n in sorted(noms.items()))

    def panneau_entrainement(self, ox, oy):
        """Onglet Entraînement (FUN_00436325 / FUN_004396db) : une ligne par type d'unité recrutable."""
        eco = self.t['economie']
        c = self.choisi
        if c is None or self.proprio[c] != 0:
            self.texte('Choisissez un de vos comtés.', (ox + 0x69, oy + 0x32), self.petite)
            return
        self.texte('En ' + donnees.COMTES[c].capitalize(), (ox + 0x69 - 30, oy + 0x31))
        ia, ig, bar = eco['icone_active'], eco['icone_grise'], eco['barre']
        for row, t in enumerate(self.types_entrainables()):
            x, y = ox + 0x38, oy + 0x62 + row * 0x1e
            possible = (c, t) not in self.commandes and self.ressources[0] >= self.eco('cout_or', t) \
                and self.ressources[3] >= self.eco('cout_paysans', t)
            if possible:
                self.blit((x, y), (ia[0], ia[1] + ia[3] * t, ia[2], ia[1] + ia[3] * (t + 1)))
            else:
                self.blit((x, y), (ig[0], ig[1] + ig[3] * t, ig[2], ig[1] + ig[3] * (t + 1)))
            sx, sy = ox + 0x6f, oy + 0x6e + row * 0x1e
            self.texte(self.eco('cout_or', t), (sx + 4, sy), self.petite, centre=True)
            if (c, t) in self.commandes:
                reste = self.eco('duree', t) + 1 - self.commandes[c, t]
                self.texte(reste, (sx + 0x11 + 4, sy), self.petite, centre=True)
            else:
                self.texte(self.eco('duree', t), (sx + 0x11 + 4, sy), self.petite, centre=True)
            for k in range(6):  # barres : attaque, portée, armure, vie, vitesse, vue
                h = eco['barres'][k][t * 2 + self.niveaux.get(t, 0)] * 3
                if h:
                    self.blit((sx - 2 + 0x22 + 0x11 * k, sy + 0xd - h), (bar[0], bar[1] - h, bar[2], bar[1]))
        self.texte_cadre('Armée : ' + (self.resume(self.armees[c]) or 'aucune') + '. Clic : recruter ou annuler.',
                         (ox + 56, oy + 349, ox + 240, oy + 385), self.petite, centre_v=True)

    def panneau_administration(self, ox, oy):
        """Onglet Administration (FUN_0043904d) : armement et architecture de toute la Valachie."""
        ad = self.t['administration']
        self.texte('En Valachie', (ox + 0x69 - 30, oy + 0x31))
        for quoi, y_img, y_txt in (('armement', 0x5a, 0x96), ('architecture', 0xdf, 0x11b)):
            niveau = self.niveau_armement if quoi == 'armement' else self.niveau_architecture
            if quoi == 'armement' and niveau >= ad['armement_max']:
                self.blit((ox + 0x38, oy + y_img), ad['image_armement_max'])
            else:
                x0, y0, l, h = ad['image_' + quoi]
                k = min(niveau - 1, 3)
                self.blit((ox + 0x38, oy + y_img), (x0 + k * l, y0, x0 + (k + 1) * l, y0 + h))
            # niveau atteint : petites cases pleines
            for i in range(ad[quoi + '_max']):
                r = pygame.Rect(ox + (0x85 if quoi == 'armement' else 0x8c) + 7 * i, oy + y_img - 8, 6, 6)  # (0x94/0x9b + 7i) à l'écran
                pygame.draw.rect(self.surface, (150, 30, 20) if i < niveau else (200, 180, 150), r)
                pygame.draw.rect(self.surface, ENCRE, r, 1)
            if niveau < ad[quoi + '_max']:
                self.texte(ad[quoi + '_cout'][niveau], (ox + 0xc5, oy + y_txt), self.petite, centre=True)
                self.texte(ad[quoi + '_duree'][niveau] + 1, (ox + 0xd8, oy + y_txt), self.petite, centre=True)
                if quoi in self.ameliorations:
                    reste = ad[quoi + '_duree'][niveau] + 1 - self.ameliorations[quoi]
                    self.texte('encore %d sem.' % reste, (ox + 0xcd, oy + y_txt + 0x14), self.petite, centre=True)
            else:
                self.texte('niveau max', (ox + 0xcd, oy + y_txt), self.petite, centre=True)
        self.texte_cadre('Armement %d/5, architecture %d/4. Clic sur Améliorer (reclic : annuler).'
                         % (self.niveau_armement, self.niveau_architecture), (ox + 56, oy + 349, ox + 240, oy + 385), self.petite, centre_v=True)

    # --- onglet Constructions (FUN_00437c8d) ---------------------------------------------------------
    def clic_constructions(self, pos, ox, oy):
        c, ch, t = self.choisi, self.chantiers, self.t['constructions']
        if c is None or self.proprio[c] != 0:
            return False
        x, y = pos[0] - ox, pos[1] - oy
        dans = lambda bx, by, l, h: bx <= x < bx + l and by <= y < by + h
        for k, (bx, by, _, _) in enumerate(t['boutons_mode']):
            if dans(bx, by, 0x32, 0x1e):
                if c in ch.chantier:
                    if ch.chantier[c]['mode'] == k:
                        ch.annuler(c)
                    else:
                        self.message = 'Un seul chantier à la fois par comté.'
                else:
                    ch.mode = k
                    self.message = ('Cliquez sur un bâtiment endommagé pour le réparer.',
                                    'Choisissez le modèle visé puis cliquez sur le fort ou château à améliorer.',
                                    'Choisissez un bâtiment puis cliquez sur un emplacement libre.')[k]
                return True
        if c not in ch.chantier and ch.mode > 0:
            for k, (bx, by, _, _) in enumerate(t['boutons_categorie']):
                if k in ch.categories() and dans(bx, by, 0x26, 0x26):
                    ch.categorie, ch.modele = k, 0
                    return True
            for k, (bx, by, _, _) in enumerate(t['boutons_modele']):
                if k < ch.nb_modeles(ch.categorie) and dans(bx, by, 0x1e, 0x14):
                    ch.modele = k
                    return True
        mx, my = t['minicarte_pos']
        if dans(mx, my, 128, 128):
            ch.clic_carte(c, x - mx, y - my)
            return True
        return False

    def panneau_constructions(self, ox, oy):
        c, ch, t = self.choisi, self.chantiers, self.t['constructions']
        if c is None or self.proprio[c] != 0:
            self.texte('Choisissez un de vos comtés.', (ox + 0x69, oy + 0x32), self.petite)
            return
        self.texte('En ' + self.nom_comte(c), (ox + 0x69 - 30, oy + 0x31))
        mx, my = ox + t['minicarte_pos'][0], oy + t['minicarte_pos'][1]
        sx, sy = t['minicartes'][c]
        self.blit((mx, my), (sx, sy, sx + 128, sy + 128))
        en_cours = ch.chantier.get(c)
        # repères : bâtiments existants, puis ce qu'on peut faire dans le mode courant
        surbrillance = set()
        if en_cours:
            if en_cours['cible'] is not None:
                surbrillance.add(id(en_cours['cible']))
        elif ch.mode == 1:
            surbrillance = {id(b) for b in ch.ameliorables(c)}
        elif ch.mode == 0:
            surbrillance = {id(b) for b in ch.endommages(c)}
        for b in ch.batiments[c]:
            x, y, r = ch.repere(c, b['cat'], b['sub'], b['site'], id(b) in surbrillance)
            self.blit((mx + x, my + y), r)
        if en_cours and en_cours['mode'] == 2:
            x, y, r = ch.repere(c, en_cours['cat'], en_cours['sub'], en_cours['site'], True)
            self.blit((mx + x, my + y), r)
        elif not en_cours and ch.mode == 2:
            for sub, site in ch.sites_libres(c):
                x, y, r = ch.repere(c, ch.categorie, sub, site, True)
                self.blit((mx + x, my + y), r)
        # boutons Réparer / Améliorer / Construire
        for k, (bx, by, normal, enfonce) in enumerate(t['boutons_mode']):
            actif = (en_cours['mode'] == k) if en_cours else (ch.mode == k)
            self.blit((ox + bx, oy + by), enfonce if actif else normal)
            if en_cours and en_cours['mode'] == k:
                reste = en_cours['duree'] - en_cours['semaines']
                self.texte('%d sem.' % reste, (ox + bx + 0x19, oy + by + 0x1e + 5), self.petite, centre=True)
        # coût de ce qui est choisi, sous les icônes or / bois / sablier
        if en_cours:
            prix = (en_cours['or'], en_cours['bois'], en_cours['duree'])
            cat, sub = en_cours['cat'], en_cours['sub']
        else:
            cat, sub = ch.categorie, ch.modele
            prix = ch.cout_affiche(cat, sub) if ch.mode == 2 else None
        if prix:  # or et sablier sur une ligne, bois en dessous, pour que les nombres ne se chevauchent pas
            for k, v in enumerate(prix):
                self.texte(v, (ox + 0x40 + 0x11 * k, oy + (0x6e if k == 1 else 0x65)), self.petite, centre=True)
        if not en_cours and ch.mode > 0:
            for k, (bx, by, normal, enfonce) in enumerate(t['boutons_categorie']):
                if k in ch.categories():
                    self.blit((ox + bx, oy + by), enfonce if k == ch.categorie else normal)
            for k, (bx, by, normal, enfonce) in enumerate(t['boutons_modele']):
                if k < ch.nb_modeles(ch.categorie):
                    self.blit((ox + bx, oy + by), enfonce if k == ch.modele else normal)
        apx, apy = t['apercu_pos']
        if en_cours or ch.mode > 0:
            idx = t['apercu_base'][cat] + (sub if cat in (2, 3) else 0)
            if cat == 0:
                idx = ch.modele if not en_cours else next(k for k, l in enumerate(t['types_ponts']) if sub in l or k == 2)
            self.blit((ox + apx, oy + apy), t['apercus'][idx])
        if en_cours:
            verbe = ('Réparation', 'Amélioration', 'Construction')[en_cours['mode']]
            txt = '%s : %s, encore %d semaine(s). Recliquez sur le bouton pour annuler.' % (
                verbe, ch.nom(cat, sub), en_cours['duree'] - en_cours['semaines'])
        else:
            txt = 'Architecture %d : %s.' % (self.niveau_architecture, ', '.join(
                batiments.NOMS[k] + 's' for k in ch.categories()).replace('châteaus', 'châteaux').replace('tour de guets', 'tours de guet'))
        self.texte_cadre(txt, (ox + 56, oy + 349, ox + 240, oy + 385), self.petite, centre_v=True)

    # --- onglet Mouvements (FUN_00437650, clics FUN_00435302, ordre FUN_0044090d, fin de semaine FUN_00440ca1) ---
    def etats(self, c):
        """État de chaque unité du comté : None (au repos), 'sel' (choisie) ou comté de destination."""
        o = self.ordres[c]
        n = len(self.armees[c])
        if len(o) != n:
            o[:] = (o + [None] * n)[:n]
        return o

    def tout_choisir(self):
        c = self.choisi
        if c is None or self.proprio[c] != 0:
            return
        o = self.etats(c)
        libres = [k for k, v in enumerate(o) if v in (None, 'sel')]
        valeur = None if all(o[k] == 'sel' for k in libres) else 'sel'
        for k in libres:
            o[k] = valeur

    def ordonner(self, j):
        c = self.choisi
        o = self.etats(c)
        if j == c:
            self.message = 'Choisissez un comté voisin comme destination.'
        elif j not in self.voisins.get(c, {}):
            self.message = '%s n\'est pas voisin de %s.' % (self.nom_comte(j), self.nom_comte(c))
        else:
            n = 0
            for k, v in enumerate(o):
                if v == 'sel':
                    o[k], n = j, n + 1
            verbe = 'attaqueront' if self.proprio[j] else 'iront à'
            self.message = '%d unité(s) %s %s au prochain sceau.' % (n, verbe, self.nom_comte(j))

    def deplacer(self):
        """Fin de semaine : les troupes rejoignent les comtés amis ; celles envoyées chez l'ennemi forment des assauts."""
        arrivees, assauts, msg = {}, {}, []
        for c in range(12):
            o = self.etats(c)
            restent, ordres_restants = [], []
            for t, d in zip(self.armees[c], o):
                if isinstance(d, int):
                    if self.proprio[d] == 0:
                        arrivees.setdefault(d, []).append(t)
                    else:
                        assauts.setdefault(d, []).append((c, t))
                else:
                    restent.append(t)
                    ordres_restants.append(None)
            self.armees[c], self.ordres[c] = restent, ordres_restants
        for d, types in arrivees.items():
            self.armees[d] += types
            msg.append('%d unité(s) arrivée(s) à %s.' % (len(types), self.nom_comte(d)))
        for d, liste in assauts.items():
            origines = [c for c, _ in liste]
            origine = max(set(origines), key=origines.count)  # les survivants d'un échec y rentrent
            self.assauts.insert(0, ('bataille', d, origine, [t for _, t in liste]))
        return msg

    def prochain_assaut(self):
        while self.assauts:
            nature, cible, origine, types = self.assauts.pop(0)
            if nature == 'bataille' and self.proprio[cible] == 0:  # déjà pris cette semaine : les troupes s'installent
                self.armees[cible] += types
                continue
            if nature == 'defense' and self.proprio[cible] == 1:  # déjà tombé cette semaine
                self.garnisons[cible] += types
                continue
            self.assaut = cible
            return (nature, cible, origine, types)
        return None

    # --- l'ennemi (FUN_0043efed, FUN_0043ea67, FUN_0043ed9d) ------------------------------------------
    def poids(self, table, t):
        e = self.t['ennemi'][table]
        return e.get(str(t), e.get('autre', 0))

    def tirer_type(self):
        r = random.randrange(100)
        return next(t for seuil, t, _ in self.t['ennemi']['tirage'] if r < seuil)

    def recruter_garnison(self, c, existante=(), points=None):
        """Garnison complétée jusqu'à son total de points (0x48f3d8 x échelle du moteur)."""
        e = self.t['ennemi']
        cible = int((e['garnison_points'][c] if points is None else points) * e['echelle'])
        g = list(existante)
        pts = sum(self.poids('points', t) for t in g)
        while pts < cible:
            t = self.tirer_type()
            g.append(t)
            pts += self.poids('points', t)
        return g

    def frontiere(self, c):
        return any(self.proprio[j] != self.proprio[c] for j in self.voisins.get(c, {}))

    def ia_ennemie(self):
        """Tour de l'ennemi : un comté frontalier reçoit des renforts et répare ses murs, puis attaques éventuelles."""
        e, msg = self.t['ennemi'], []
        debut = (self.annee, self.semaine) > (e['debut']['annee'], 3)
        c = self.tour_renfort
        self.tour_renfort = (c + 1) % 12
        if debut and self.proprio[c] == 1 and self.frontiere(c):
            self.garnisons[c] = self.recruter_garnison(c, self.garnisons[c])
            for b in self.chantiers.batiments[c]:
                b['pv'] = None
        if (self.annee, self.semaine) <= (e['debut']['annee'], e['debut']['semaine']):
            self.tension += 1
            return msg
        agressif = random.randrange(100) < e['agressif']
        visees = set()
        ordre = list(range(12))
        random.shuffle(ordre)
        for src in ordre:
            if self.proprio[src] != 1 or not self.frontiere(src):
                continue
            force = sum(self.poids('force', t) for t in self.garnisons[src])
            cibles = [j for j in self.voisins[src] if self.proprio[j] == 0]
            random.shuffle(cibles)
            cible = cibles[0]
            defense = sum(self.poids('force', t) for t in self.armees[cible])
            k = e['facteur_attaque']
            ratio = 1.0 if agressif else force * k / (force * k + defense or 1)
            proba = max(e['proba_base'], e['proba_base'] * ratio + max(0, self.tension))
            if force <= 0 or random.randrange(100) >= proba:
                continue
            budget = int(force * (random.randrange(5) + 3) / 10)
            if cible in visees or budget <= e['budget_min']:
                continue
            if self.annee == e['debut']['annee']:
                budget = min(budget, 15 if self.semaine < 20 else 40)
            troupes = self.composer_attaque(src, budget)
            if troupes:
                visees.add(cible)
                self.tension = 0
                self.assauts.append(('defense', cible, src, troupes))
                msg.append('%s attaque %s !' % (self.nom_comte(src), self.nom_comte(cible)))
        self.tension += 1
        return msg

    def composer_attaque(self, src, budget):
        """Tire au hasard les assaillants dans la garnison (FUN_0043ea67) ; au moins un bélier."""
        g = self.garnisons[src]
        cout = {t: c for _, t, c in self.t['ennemi']['tirage']}
        troupes, essais = [], 0
        while budget > 0 and g and essais < 500:
            essais += 1
            t = self.tirer_type()
            if t in g:
                g.remove(t)
                troupes.append(t)
                budget -= cout[t]
        if troupes and 5 not in troupes:
            troupes.append(5)
            if 5 in g:
                g.remove(5)
        return troupes

    def resultat_defense(self, comte, source, victoire, survivants, ennemis):
        nom = self.nom_comte(comte)
        self.assaut = None
        self.armees[comte] = list(survivants)
        self.ordres[comte] = []
        if victoire:
            self.garnisons[source] += list(ennemis)  # d'éventuels survivants rentrent
            self.message = '%s a tenu bon !' % nom
        else:
            self.proprio[comte] = 1
            self.armees[comte] = []
            self.garnisons[comte] = list(ennemis)
            self.chantiers.chantier.pop(comte, None)
            self.message = '%s est tombé aux mains de l\'ennemi.' % nom
            if self.choisi == comte:
                self.choisi = next((c for c in range(12) if self.proprio[c] == 0), None)
            if all(p == 1 for p in self.proprio):
                self.message = 'Vous avez perdu la Valachie. Échap pour quitter.'
        self.ressources[4] = self.nb_soldats()

    def clic_mouvements(self, pos, ox, oy):
        c = self.choisi
        if c is None or self.proprio[c] != 0:
            return False
        x, y = pos[0] - ox - 0x3a, pos[1] - oy - 0x54
        if not (0 <= x < 4 * 0x2a and 0 <= y < 9 * 0x1c):
            return False
        k = (y // 0x1c + self.defilement) * 4 + x // 0x2a
        o = self.etats(c)
        if k < len(o):
            o[k] = 'sel' if o[k] is None else None
        return True

    def panneau_mouvements(self, ox, oy):
        c = self.choisi
        if c is None or self.proprio[c] != 0:
            self.texte('Choisissez un de vos comtés.', (ox + 0x69, oy + 0x32), self.petite)
            return
        self.texte('De ' + self.nom_comte(c), (ox + 0x69 - 30, oy + 0x31))
        o = self.etats(c)
        lignes = (len(o) + 3) // 4
        self.defilement = min(self.defilement, max(0, lignes - 9))
        for k, (t, etat) in enumerate(zip(self.armees[c], o)):
            ligne = k // 4 - self.defilement
            if not 0 <= ligne < 9:
                continue
            if etat == 'sel':
                r = (0x205, 0x6a8 + 0x1c * t, 0x22f, 0x6c4 + 0x1c * t - (2 if t == 8 else 0))
            elif etat is None:
                r = (0x217, 0x332 + 0x1c * t, 0x241, 0x34e + 0x1c * t)
            else:
                r = (0x22b, 0xa6a + 0x1c * t, 0x255, 0xa86 + 0x1c * t)
            self.blit((ox + 0x3a + (k % 4) * 0x2a, oy + 0x54 + ligne * 0x1c), r)
        if not o:
            txt = 'Aucune troupe ici.'
        elif lignes > 9:
            txt = 'Molette : faire défiler. '
        else:
            txt = ''
        if o:
            txt += 'Clic : choisir une unité, clic droit : toutes. Puis cliquez un comté voisin ; départ au sceau.'
        self.texte_cadre(txt, (ox + 56, oy + 349, ox + 240, oy + 385), self.petite, centre_v=True)
