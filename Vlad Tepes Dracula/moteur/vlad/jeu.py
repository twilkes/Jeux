"""Prototype : bataille sur une carte de comté, avec les règles et les sons retrouvés dans DRACULA.EXE.

Lancement : python -m vlad <chemin des données> [--comte BRASOV]
  sans --comte : partie complète (écran du conseil, conquête des comtés) ; avec : bataille directe
  <chemin des données> = Dracula.bin (recommandé : musique du CD incluse) ou le dossier extrait/donnees
Commandes : clic gauche (ou rectangle) = sélection, clic droit = déplacer ou attaquer un ennemi
  (clic droit sur un mur ou une porte : le bélier, la catapulte et le canon choisis l'attaquent),
  flèches ou bord de l'écran = défilement, S = stop, F = obstacles, P = musique suivante,
  L = mode de lissage, T = filtre des tuiles (mode xbr), Tab = comté suivant (bataille directe), Échap = retraite / quitter,
  F11 (ou Alt+Entrée) = plein écran lissé, M = mini-carte (clic : y aller, clic droit : y envoyer), F5 / F9 au conseil = sauvegarder / charger. Option --plein-ecran.
Options : --lissage net|lisse|epx|xbr|hd   --hd <dossier du pack HD> (par défaut moteur/extrait/hd)
"""
import heapq, json, math, os, random, sys, threading
import pygame
from . import donnees, batiments
from .conseil import Conseil
from .sons import Sons

LARGEUR, HAUTEUR, BARRE = 640, 480, 24  # dimensions logiques (celles du jeu d'origine)
Z = 2  # facteur d'affichage : la fenêtre fait 1280x960, le jeu calcule toujours en 640x480
Y_SPRITES = 3708  # dans BATTLE.ART, les tuiles sont au-dessus, les sprites en dessous
MARGE = 8  # marge autour de chaque tuile dans l'export pour l'IA (voir outils/export_hd.py)
MODES = {'net': 'pixels nets', 'lisse': 'tuiles lissées', 'epx': 'lissage EPX', 'xbr': 'contours lissés xBR', 'hd': 'pack HD'}
TUILE, CASE = 40, 20
TRANSPARENT = 218
ZOOMS = (0.5, 0.67, 1.0, 1.5, 2.0)  # molette : 0,5 = vue deux fois plus haute
MAX_ARMEE = 40  # unités posées par camp sur le terrain ; le reste attend en réserve (choix du moteur, pour la fluidité)
TICKS = 20  # ticks de jeu par seconde (hypothèse : la vitesse des tables est en pixels par tick)
ICI = os.path.dirname(os.path.abspath(__file__))
NOMS = {0: 'Fantassin', 1: 'Archer', 3: 'Chevalier', 5: 'Bélier', 6: 'Catapulte', 7: 'Canon'}
TIR = {1: 'Battle_05', 6: 'Battle_29', 7: 'Battle_02', 5: 'Battle_37'}  # sons d'attaque (code d'origine)
# curseurs de bataille dans BATTLE.ART (rectangles et points chauds retrouvés dans DRACULA.EXE, FUN_00452c..)
_FLECHES = (0xe87, 0xead, 0xecc, 0xeec, 0xf0b, 0xf31, 0xf50, 0xf70, 0xf8f)  # N, NE, E, SE, S, SO, O, NO
CURSEURS = dict({'normal': ((0xf0, 0xe60, 39, 39), (0, 0)), 'choisir': ((0xf0, 0xfcd, 24, 24), (12, 12)),
                 'attaquer': ((0xf0, 0xfaa, 31, 35), (16, 17)), 'attaquer2': ((0x10f, 0xfaa, 31, 35), (16, 17)),
                 'marcher': ((0xf0, 0xf8f, 27, 27), (0, 0)), 'marcher2': ((0x10b, 0xf8f, 27, 27), (0, 0))},
                **{'fleche%d' % i: ((0xf0, _FLECHES[i], 40, _FLECHES[i + 1] - _FLECHES[i]), None) for i in range(8)})
FILTRES_TUILES = {'net': 'nettes', 'epx': 'EPX', 'bicubique': 'bicubiques', 'xbr': 'xBR'}  # touche T en mode xbr
MINI = 16  # position de la mini-carte (comme l'original : (16, 16), dans le cadre de pierre du panneau de BATTLE.ART)
CADRE_MINI = (0, 0xe60, 156, 156)  # haut du panneau de gauche de l'original : cadre de pierre, mini-carte posée dans le creux
COULEUR_PROJ = {1: (60, 40, 20), 6: (110, 100, 90), 7: (20, 20, 20)}


def stat(st, nom, t, niveau=0):
    return st[nom][t][niveau] if t < len(st[nom]) else 0


def avec_bordure(img, m):
    """Recopie les bords d'une image sur m pixels (évite que le lissage mélange une tuile avec sa voisine)."""
    w, h = img.get_size()
    s = pygame.Surface((w + 2 * m, h + 2 * m)).convert()
    s.blit(img, (m, m))
    for i in range(m):
        s.blit(img, (m, i), (0, 0, w, 1))
        s.blit(img, (m, h + m + i), (0, h - 1, w, 1))
    gauche, droite = s.subsurface((m, 0, 1, h + 2 * m)).copy(), s.subsurface((w + m - 1, 0, 1, h + 2 * m)).copy()
    for i in range(m):
        s.blit(gauche, (i, 0))
        s.blit(droite, (w + m + i, 0))
    return s


class Graphismes:
    def __init__(self, source, dossier_hd=None):
        w, h, px, pal = donnees.lire_pcx(source.lire('ART/BATTLE.ART'))
        self.brut = pygame.image.frombuffer(bytes(px), (w, h), 'P')
        self.brut.set_palette([tuple(pal[i * 3:i * 3 + 3]) for i in range(256)])
        self.cle = tuple(pal[TRANSPARENT * 3:TRANSPARENT * 3 + 3])
        self.hauteur = h
        self.t = json.load(open(os.path.join(ICI, 'tables_unites.json'), encoding='utf-8'))
        self.hd = {}
        for nom in ('tuiles', 'sprites'):
            f = os.path.join(dossier_hd or '', nom + '.png')
            if dossier_hd and os.path.isfile(f):
                self.hd[nom] = f
        self.mode = None
        self.cache = {}  # (mode, 't' tuile | 's' sprite, clé, facteur) -> Surface
        self.urgent, self.fond, self.demande = [], [], set()  # agrandissements xBR à calculer (fil de fond)
        self.verrou = threading.Condition()
        self.fil = None
        self.filtre_tuiles = 'net'  # en mode xbr : filtre du terrain, à part de celui des unités (touche T)

    def modes(self):
        try:
            import numpy  # noqa: F401 (le filtre xBR en a besoin ; Anaconda l'inclut)
            xbr = True
        except ImportError:
            xbr = False
        return [m for m in MODES if (m != 'hd' or self.hd) and (m != 'xbr' or xbr)]

    def preparer(self, mode):
        """Construit les planches agrandies x Z selon le mode de lissage (xbr : planches EPX en attendant le calcul)."""
        self.mode = mode
        with self.verrou:
            self.urgent.clear(), self.fond.clear(), self.demande.clear()
            self.cache = {k: v for k, v in self.cache.items() if k[0] == mode}
        if mode == 'xbr':
            mode = 'epx'
        if mode == 'hd' and getattr(self, '_cache_hd', None):  # le pack HD est long à charger : on le garde
            self.tuiles, self.sprites = self._cache_hd
            return
        lignes = (Y_SPRITES + TUILE - 1) // TUILE
        if mode == 'hd' and 'tuiles' in self.hd:
            self.tuiles = self.tuiles_hd(self.hd['tuiles'])
        else:
            src = self.brut.subsurface((0, 0, 640, lignes * TUILE)).convert()
            if mode == 'net':
                self.tuiles = pygame.transform.scale(src, (640 * Z, lignes * TUILE * Z))
            else:  # chaque tuile est agrandie seule, avec ses bords recopiés, pour ne pas baver sur ses voisines
                self.tuiles = pygame.Surface((640 * Z, lignes * TUILE * Z)).convert()
                T, m = TUILE * Z, 2
                for i in range(16 * lignes):
                    x, y = (i % 16) * TUILE, (i // 16) * TUILE
                    b = avec_bordure(src.subsurface((x, y, TUILE, TUILE)), m)
                    if mode == 'epx':
                        g = pygame.transform.scale2x(b)
                    else:
                        g = pygame.transform.smoothscale(b, (b.get_width() * Z, b.get_height() * Z))
                    self.tuiles.blit(g, (x * Z, y * Z), (m * Z, m * Z, T, T))
        hs = self.hauteur - Y_SPRITES
        if mode == 'hd' and 'sprites' in self.hd:
            img = pygame.image.load(self.hd['sprites']).convert_alpha()
            if img.get_size() != (640 * Z, hs * Z):
                img = pygame.transform.smoothscale(img, (640 * Z, hs * Z))
            self.sprites = img
        else:
            src = self.brut.subsurface((0, Y_SPRITES, 640, hs)).convert()
            # EPX ne recopie que des couleurs existantes : le cyan de transparence reste intact
            self.sprites = pygame.transform.scale(src, (640 * Z, hs * Z)) if mode == 'net' else pygame.transform.scale2x(src)
            self.sprites.set_colorkey(self.cle)
        if mode == 'hd':
            self._cache_hd = self.tuiles, self.sprites

    def tuiles_hd(self, chemin):
        """Pack HD : la grille de tuiles avec marges exportée par export_hd.py, agrandie par n'importe quel facteur."""
        img = pygame.image.load(chemin).convert()
        cell = img.get_width() / 16
        f = cell / (TUILE + 2 * MARGE)
        lignes = int(round(img.get_height() / cell))
        res = pygame.Surface((640 * Z, lignes * TUILE * Z)).convert()
        for i in range(16 * lignes):
            x0, y0 = (i % 16) * cell + MARGE * f, (i // 16) * cell + MARGE * f
            r = pygame.Rect(int(round(x0)), int(round(y0)), int(round(TUILE * f)), int(round(TUILE * f))).clip(img.get_rect())
            if r.w and r.h:
                t = pygame.transform.smoothscale(img.subsurface(r), (TUILE * Z, TUILE * Z))
                res.blit(t, ((i % 16) * TUILE * Z, (i // 16) * TUILE * Z))
        return res

    # --- morceaux agrandis à la demande (facteur 4 pour le zoom avant, ou filtre xBR) -------------------
    def morceau(self, genre, cle, f):
        """Surface et rectangle source d'une tuile (cle = numéro) ou d'un sprite (cle = rect) agrandi x f (2 ou 4).
        En mode xbr, le calcul se fait dans un fil de fond ; en attendant on rend la version EPX."""
        if f == 2 and self.mode != 'xbr':
            if genre == 't':
                T = TUILE * Z
                return self.tuiles, ((cle % 16) * T, (cle // 16) * T, T, T)
            return self.sprites, self.source_z(pygame.Rect(cle))
        if self.mode == 'xbr' and genre == 't':
            ft = self.filtre_tuiles
            if ft in ('net', 'epx'):
                s = self.cache.get(('xbr', 't', (cle, ft), f))
                if s is None:
                    if ft == 'epx':
                        s = self.agrandi_simple('t', cle, f, 'epx')
                    else:
                        b = self.brut.subsurface(((cle % 16) * TUILE, (cle // 16) * TUILE, TUILE, TUILE)).convert()
                        s = pygame.transform.scale(b, (TUILE * f, TUILE * f))
                    self.cache[('xbr', 't', (cle, ft), f)] = s
                return s, None
            cle = (cle, ft)
        s = self.cache.get((self.mode, genre, cle, f))
        if s is not None:
            return s, None
        if self.mode == 'xbr':
            self.demander((genre, cle, f), True)
            c0 = cle[0] if genre == 't' else cle
            s = self.cache.get(('epx', genre, c0, f))
            if s is None:
                s = self.cache[('epx', genre, c0, f)] = self.agrandi_simple(genre, c0, f, 'epx')
            return s, None
        s = self.cache[(self.mode, genre, cle, f)] = self.agrandi_simple(genre, cle, f, self.mode)
        return s, None

    def agrandi_simple(self, genre, cle, f, mode):
        """Agrandissement rapide x f à partir des planches x2 déjà prêtes."""
        planche, src = (self.tuiles, ((cle % 16) * TUILE * Z, (cle // 16) * TUILE * Z, TUILE * Z, TUILE * Z)) \
            if genre == 't' else (self.sprites, self.source_z(pygame.Rect(cle)))
        p = planche.subsurface(src).copy()
        if f == 2:
            return p
        if mode == 'epx' or (mode == 'net' and genre == 's'):
            g = pygame.transform.scale2x(p) if mode == 'epx' else pygame.transform.scale(p, (src[2] * 2, src[3] * 2))
        elif mode == 'net':
            g = pygame.transform.scale(p, (src[2] * 2, src[3] * 2))
        else:
            g = pygame.transform.smoothscale(p.convert_alpha() if genre == 's' else p, (src[2] * 2, src[3] * 2))
        if genre == 's' and not g.get_flags() & pygame.SRCALPHA:
            g.set_colorkey(self.cle)
        return g

    def demander(self, cle, urgent):
        with self.verrou:
            if cle in self.demande:
                if urgent and cle in self.fond:  # devenu visible : passe devant
                    self.fond.remove(cle)
                    self.urgent.append(cle)
                return
            self.demande.add(cle)
            (self.urgent if urgent else self.fond).append(cle)
            self.verrou.notify()
        if self.fil is None:
            self.fil = threading.Thread(target=self.travailler, daemon=True)
            self.fil.start()

    def prechauffer(self, tuiles, types, f=2):
        """Met en file (priorité basse) toutes les tuiles d'une carte et les images des unités présentes."""
        if self.mode != 'xbr':
            return
        if self.filtre_tuiles not in ('net', 'epx'):
            for t in sorted(set(tuiles)):
                self.demander(('t', (t, self.filtre_tuiles), f), False)
        for ty in sorted(set(types)):
            for camp in (0, 1):
                for anim in range(3):
                    for d in range(8):
                        for im in range(self.nb_images(ty, anim)):
                            r = self.rect(ty, anim, camp, im, d)
                            if r is not None and r.y >= Y_SPRITES:
                                self.demander(('s', tuple(r), f), False)

    def travailler(self):
        from . import filtres
        while True:
            with self.verrou:
                while not self.urgent and not self.fond:
                    self.verrou.wait()
                cle = self.urgent.pop() if self.urgent else self.fond.pop(0)
                mode = self.mode
            genre, c, f = cle
            try:
                if genre == 't':
                    n, ft = c
                    b = avec_bordure(self.brut.subsurface(((n % 16) * TUILE, (n // 16) * TUILE, TUILE, TUILE)), 2)
                    s = filtres.agrandir(b, f, 2, net=0.2 if ft == 'bicubique' else 0.35,
                                         methode='cubique' if ft == 'bicubique' else 'xbr')
                    s = s.convert() if pygame.display.get_init() and pygame.display.get_surface() else s
                else:
                    b = self.brut.subsurface(pygame.Rect(c)).convert()
                    b.set_colorkey(self.cle)
                    s = filtres.agrandir(b, f)
            except Exception as ex:  # pas de numpy, etc. : on garde la version EPX
                print('xBR :', ex)
                s = None
            with self.verrou:
                self.demande.discard(cle)
                if s is not None and mode == self.mode:
                    self.cache[(mode, genre, c, f)] = s

    def curseur(self, nom, k):
        """Curseur agrandi pour k pixels d'écran par unité logique : (surface, point chaud en pixels)."""
        cle = ('curseur', nom, round(k, 3))
        if cle not in self.cache:
            r, chaud = CURSEURS[nom]
            b = self.brut.subsurface(r).convert()
            b.set_colorkey(self.cle)
            zone = b.get_bounding_rect()
            b = b.subsurface(zone).copy()
            try:
                from . import filtres
                g = filtres.agrandir(b, 4)
            except Exception:
                g = pygame.transform.scale2x(pygame.transform.scale2x(b))
                g.set_colorkey(self.cle)
            taille = (max(1, int(zone.w * k)), max(1, int(zone.h * k)))
            g = pygame.transform.smoothscale(g.convert_alpha(), taille)
            chaud = (0, 0) if chaud is None else ((chaud[0] - zone.x) * k, (chaud[1] - zone.y) * k)
            self.cache[cle] = (g, chaud)
        return self.cache[cle]

    def cadre_minicarte(self, k):
        cle = ('cadre', round(k, 3))
        if cle not in self.cache:
            b = self.brut.subsurface(CADRE_MINI).convert()  # le creux (cyan) est caché par la mini-carte
            try:
                from . import filtres
                g = filtres.agrandir(b, 4, net=0.2, methode='cubique')
            except Exception:
                g = pygame.transform.scale2x(pygame.transform.scale2x(b))
            g = pygame.transform.smoothscale(g.convert(), (int(CADRE_MINI[2] * k), int(CADRE_MINI[3] * k)))
            pygame.draw.rect(g, (20, 16, 12), g.get_rect(), max(1, int(k)))
            self.cache[cle] = g
        return self.cache[cle]

    def couleurs_minicarte(self, source):
        """MINIMAP.WG : pour chaque tuile, 3 index de palette (visible, déjà vue, inconnue) -> couleurs RGB."""
        if not hasattr(self, 'mini'):
            try:
                d = source.lire('ART/MINIMAP.WG')
            except Exception:
                d = b''
            pal = self.brut.get_palette()
            self.mini = [tuple(pal[c])[:3] for c in d]
        return self.mini

    def source_z(self, r):
        """Rectangle d'un sprite (coordonnées BATTLE.ART) -> rectangle dans la planche agrandie."""
        if r is None or r.y < Y_SPRITES:
            return None
        return pygame.Rect(r.x * Z, (r.y - Y_SPRITES) * Z, r.w * Z, r.h * Z)

    def nb_images(self, type_, anim):
        return self.t['nb_images'][3 * type_ + anim]

    def rect(self, type_, anim, camp, image, direction):
        """Formule retrouvée dans DRACULA.EXE (fonction de dessin des unités)."""
        S = self.t['taille'][type_]
        i = (3 * type_ + anim) * 3 + camp
        x = self.t['x'][i] + S * image
        y = self.t['y'][i] + S * direction
        if y + S > self.hauteur:
            return None
        return pygame.Rect(x, y, S, S)

    def valide(self, type_, camp):
        return all(self.nb_images(type_, a) and self.rect(type_, a, camp, 0, 7) for a in range(3))


class Carte:
    def __init__(self, source, nom):
        self.nom = nom
        couches, grilles = donnees.lire_carte(source.lire('COUNTIES/%s.MAP' % nom))
        self.tuiles = list(couches[0])
        self.drapeaux = list(grilles[0])
        self.bloque = bytearray(1 if v & batiments.BLOQUE else 0 for v in self.drapeaux)
        self._zones = None

    def poser_drapeau(self, cx, cy, v):
        if 0 <= cx < 256 and 0 <= cy < 256:
            self.drapeaux[cy * 256 + cx] = v
            b = 1 if v & batiments.BLOQUE else 0
            if self.bloque[cy * 256 + cx] != b:
                self.bloque[cy * 256 + cx] = b
                self._zones = None

    def zone(self, c):
        """Numéro de la zone connexe d'une case libre (0 si bloquée) : évite de chercher des chemins impossibles."""
        if self._zones is None:
            z = [0] * 65536
            n = 0
            for depart in range(65536):
                if z[depart] or self.bloque[depart]:
                    continue
                n += 1
                z[depart] = n
                pile = [depart]
                while pile:
                    i = pile.pop()
                    x, y = i & 255, i >> 8
                    for j, ok in ((i - 1, x > 0), (i + 1, x < 255), (i - 256, y > 0), (i + 256, y < 255)):
                        if ok and not z[j] and not self.bloque[j]:
                            z[j] = n
                            pile.append(j)
            self._zones = z
        x, y = c
        return self._zones[y * 256 + x] if 0 <= x < 256 and 0 <= y < 256 else 0

    def sur_tour(self, c):
        return 0 <= c[0] < 256 and 0 <= c[1] < 256 and bool(self.drapeaux[c[1] * 256 + c[0]] & batiments.TOUR)

    def libre(self, cx, cy):
        return 0 <= cx < 256 and 0 <= cy < 256 and not self.bloque[cy * 256 + cx]

    def chemin(self, depart, arrivee, limite=40000):
        """A* sur la grille de passage 256x256, 8 directions, sans couper les angles."""
        if not self.libre(*arrivee):
            return None
        ouverts = [(0, depart)]
        venu = {depart: None}
        cout = {depart: 0}
        while ouverts and limite:
            limite -= 1
            _, c = heapq.heappop(ouverts)
            if c == arrivee:
                res = []
                while c != depart:
                    res.append(c)
                    c = venu[c]
                return res[::-1]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                n = (c[0] + dx, c[1] + dy)
                if not self.libre(*n):
                    continue
                if dx and dy and not (self.libre(c[0] + dx, c[1]) and self.libre(c[0], c[1] + dy)):
                    continue
                g = cout[c] + (14 if dx and dy else 10)
                if g < cout.get(n, 1 << 30):
                    cout[n] = g
                    venu[n] = c
                    h = 10 * max(abs(n[0] - arrivee[0]), abs(n[1] - arrivee[1]))
                    heapq.heappush(ouverts, (g + h, n))
        return None


class Projectile:
    def __init__(self, tireur, cible, case_visee):
        self.tireur, self.cible = tireur, cible
        self.x, self.y = tireur.x + CASE / 2, tireur.y + CASE / 2
        self.tx, self.ty = case_visee[0] * CASE + CASE / 2, case_visee[1] * CASE + CASE / 2
        self.vitesse = 260 if tireur.type == 1 else 200
        self.fini = False

    def avancer(self, dt, jeu):
        dx, dy = self.tx - self.x, self.ty - self.y
        d = math.hypot(dx, dy)
        pas = self.vitesse * dt
        if d <= pas:
            self.fini = True
            jeu.impact(self)
        else:
            self.x += dx / d * pas
            self.y += dy / d * pas


class CibleMur:
    """Une tuile de bâtiment visée par une arme de siège (se comporte comme une unité pour le combat)."""
    def __init__(self, bat, dx, dy):
        self.bat, self.dx, self.dy = bat, dx, dy
        self.camp = bat.camp
        tx, ty = bat.X + dx, bat.Y + dy
        self.cases = [(2 * tx + i, 2 * ty + j) for i in (0, 1) for j in (0, 1)]
        self.x, self.y = tx * TUILE + CASE / 2, ty * TUILE + CASE / 2
        self.case = (2 * tx + 1, 2 * ty + 1)

    @property
    def mort(self):
        return self.bat.pv.get((self.dx, self.dy), 0) <= 0


class Unite:
    def __init__(self, type_, camp, cx, cy, st, niveau=0):
        self.niveau = niveau  # niveau d'armement du type (0 ou 1), indice type*2+niveau des tables
        self.type, self.camp = type_, camp
        self.x, self.y = cx * CASE, cy * CASE
        self.direction = random.randrange(8)
        self.anim, self.image = 0, 0.0
        self.chemin = []
        self.selection = False
        self.mort = False
        self.pv_max = stat(st, 'pv_max', type_, niveau)
        self.pv = float(self.pv_max)
        self.cible = None
        self.recharge = 0.0
        self.recalcul = 0.0
        self.attente = 0.0
        self.coup_porte = True

    @property
    def case(self):
        return int(self.x + CASE / 2) // CASE, int(self.y + CASE / 2) // CASE

    def distance(self, autre):
        a = self.case
        return min(max(abs(a[0] - b[0]), abs(a[1] - b[1])) for b in getattr(autre, 'cases', [autre.case]))

    def viser(self, autre):
        dx, dy = autre.x - self.x, autre.y - self.y
        if dx or dy:
            self.direction = round(math.atan2(dx, -dy) / (math.pi / 4)) % 8

    def ordonner(self, carte, cible):
        if self.mort:
            return
        self.cible = None
        c = carte.chemin(self.case, cible)
        if c is not None:
            self.chemin = c
            self.anim = 0

    def avancer(self, dt, jeu):
        gfx, st = jeu.gfx, jeu.st
        nb = gfx.nb_images(self.type, self.anim)
        self.recharge = max(0.0, self.recharge - dt)
        self.attente = max(0.0, self.attente - dt)
        if self.mort:
            self.image = min(self.image + dt * 8, nb - 1)
            return
        # combat : approche puis attaque
        if self.cible is not None:
            if self.cible.mort:
                self.cible = None
            else:
                portee = max(1, stat(st, 'portee', self.type, self.niveau) * 2)  # x2 = cases de 20 px (code d'origine)
                if self.distance(self.cible) <= portee:
                    self.chemin = []
                    self.viser(self.cible)
                    if self.anim != 1 and self.recharge <= 0:
                        self.anim, self.image, self.coup_porte = 1, 0.0, False
                        jeu.son_attaque(self)
                else:
                    self.recalcul -= dt
                    if self.recalcul <= 0 or not self.chemin:
                        self.recalcul = 0.5
                        chemin = jeu.approche(self, self.cible, max(1, portee - 1))
                        if chemin is None:  # inaccessible (derrière un mur) : on abandonne pour un moment
                            self.cible, self.chemin, self.attente = None, [], 3.0
                        else:
                            self.chemin = chemin
        if self.anim == 1:
            nb = gfx.nb_images(self.type, 1)
            self.image += dt * 10
            if not self.coup_porte and self.image >= nb / 2:
                self.coup_porte = True
                jeu.frapper(self)
            if self.image >= nb:
                self.anim, self.image = 0, 0.0
                reload = stat(st, 'recharge', self.type, self.niveau) * 8 / TICKS
                self.recharge = max(reload, 0.3)
            return
        if self.chemin:
            cx, cy = self.chemin[0]
            tx, ty = cx * CASE, cy * CASE
            dx, dy = tx - self.x, ty - self.y
            dist = math.hypot(dx, dy)
            vit = stat(st, 'vitesse', self.type, self.niveau)
            if self.pv < self.pv_max * 0.5 and self.type not in (6, 7):
                vit = max(1, vit - 1)  # « ils marcheront plus lentement » (code d'origine)
            pas = vit * TICKS * dt
            if dist > 0.01:
                self.direction = round(math.atan2(dx, -dy) / (math.pi / 4)) % 8
            if dist <= pas:
                self.x, self.y = tx, ty
                self.chemin.pop(0)
            else:
                self.x += dx / dist * pas
                self.y += dy / dist * pas
            self.image = (self.image + dt * 10) % gfx.nb_images(self.type, 0)
        else:
            self.anim, self.image = 0, 0.0

    def rect_ecran(self, gfx, camera):
        S = gfx.t['taille'][self.type]
        a = gfx.t['ancrage'][self.type]
        return pygame.Rect(int(self.x) - a - camera[0], int(self.y) - a - camera[1], S, S)


class Jeu:
    def __init__(self, source, comte, lissage=None, dossier_hd=None, plein_ecran=False):
        pygame.init()
        pygame.display.set_caption('Vlad Tepes Dracula - moteur libre (prototype)')
        self.plein_ecran = plein_ecran
        self.fenetre()
        self.ecran = pygame.Surface((LARGEUR * Z, HAUTEUR * Z)).convert()  # image du conseil (1280x960)
        self.zoom = 1.0
        self.monde = None
        self.brouillard, self.visible, self.voir_brouillard, self.revele = None, None, True, 0.0
        self.source = source
        self.gfx = Graphismes(source, dossier_hd)
        modes = self.gfx.modes()
        self.gfx.preparer(lissage if lissage in modes else ('hd' if 'hd' in modes else 'xbr'))
        self.st = json.load(open(os.path.join(ICI, 'stats_unites.json'), encoding='utf-8'))
        self.sons = Sons(source)
        self.police = pygame.font.Font(None, 20 * Z)
        self.grande = pygame.font.Font(None, 48 * Z)
        self.voir_obstacles = False
        self.conseil, self.comte_bataille, self.origine, self.types_joueur = None, None, None, None
        if comte is None:  # partie complète : on commence au conseil
            self.conseil = Conseil(source)
            self.mode = 'conseil'
        else:
            self.mode = 'bataille'
            self.charger(comte)
        self.sons.musique()

    # --- fenêtre, plein écran, coordonnées --------------------------------------------------------
    def fenetre(self):
        """Fenêtre redimensionnable (1280x960 au départ) ou plein écran à la résolution du bureau."""
        if self.plein_ecran:
            self.affichage = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.affichage = pygame.display.set_mode((LARGEUR * Z, HAUTEUR * Z), pygame.RESIZABLE)

    def echelle(self):
        """Pixels de l'écran par unité logique (l'écran fait toujours 480 unités de haut)."""
        return self.affichage.get_height() / HAUTEUR

    def ecran_l(self):
        return self.affichage.get_width() / self.echelle()  # 640 en 4/3, plus en écran large : on voit plus loin

    def vue(self):
        """Taille de la zone du monde visible, en pixels du monde (zoom compris)."""
        return self.ecran_l() / self.zoom, HAUTEUR / self.zoom

    def cadre_conseil(self):
        W, H = self.affichage.get_size()
        s = min(W / (LARGEUR * Z), H / (HAUTEUR * Z))
        return s, (W - LARGEUR * Z * s) / 2, (H - HAUTEUR * Z * s) / 2

    def souris(self, pos):
        """Position à l'écran -> unités logiques (conseil : 640x480 ; bataille : 480 de haut, avant zoom)."""
        if self.mode == 'conseil':
            s, ox, oy = self.cadre_conseil()
            return int((pos[0] - ox) / s) // Z, int((pos[1] - oy) / s) // Z
        k = self.echelle()
        return pos[0] / k, pos[1] / k

    def vers_vue(self, pos):
        return pos[0] / self.zoom, pos[1] / self.zoom

    def centrer(self, x, y):
        l, h = self.vue()
        self.camera = [x - l / 2, y - h / 2]

    def zoomer(self, sens, pos=None):
        """Molette : zoom avant / arrière autour du curseur (vue de plus haut en arrière)."""
        niveaux = ZOOMS
        i = min(range(len(niveaux)), key=lambda k: abs(niveaux[k] - self.zoom))
        i = max(0, min(len(niveaux) - 1, i + sens))
        pos = pos or (self.ecran_l() / 2, HAUTEUR / 2)
        wx, wy = self.camera[0] + pos[0] / self.zoom, self.camera[1] + pos[1] / self.zoom
        self.zoom = niveaux[i]
        self.camera = [wx - pos[0] / self.zoom, wy - pos[1] / self.zoom]
        self.defiler(0)

    # --- brouillard de guerre ------------------------------------------------------------------
    def reveler(self):
        """Tuiles vues par les unités du joueur (rayon tiré de leur vue, bonus des tours) ; le reste reste exploré ou noir."""
        vis = bytearray(128 * 128)
        for u in self.unites:
            if u.camp != 0 or u.mort:
                continue
            vue = stat(self.st, 'vue', u.type, u.niveau) * 2 + (6 if self.carte.sur_tour(u.case) else 2)
            r = vue // 2 + 2
            tx, ty = u.case[0] // 2, u.case[1] // 2
            for y in range(max(0, ty - r), min(128, ty + r + 1)):
                for x in range(max(0, tx - r), min(128, tx + r + 1)):
                    if (x - tx) ** 2 + (y - ty) ** 2 <= r * r + 1:
                        vis[y * 128 + x] = 1
                        self.brouillard[y * 128 + x] = 0
        self.visible = vis

    def vu(self, u):
        if not self.voir_brouillard or u.camp == 0 or self.visible is None:
            return True
        return bool(self.visible[(u.case[1] // 2) * 128 + u.case[0] // 2])

    def charger(self, nom, defense=False):
        self.carte = Carte(self.source, nom)
        c = donnees.COMTES.index(nom)
        if self.conseil:  # bâtiments tels que la partie les a laissés (constructions, dégâts des assauts précédents)
            self.batiments = batiments.charger(self.source, self.carte, c, self.conseil.catalogue,
                                               self.conseil.chantiers.batiments[c])
        else:
            self.batiments = batiments.charger(self.source, self.carte, c)
        self.defense = defense
        if defense:  # le joueur défend ses propres murs
            for b in self.batiments:
                if b.camp is not None:
                    b.camp = 0
        self.unites, self.projectiles, self.effets, self.reserve = [], [], [], []
        forts = [b for b in self.batiments if b.cat >= 2]
        self.fort = max(forts, key=lambda b: b.l * b.h) if forts else None
        if self.fort:
            self.siege(self.fort)
        else:
            self.bataille((128, 128))
        self.debut_selection = None
        self.message = ''
        if self.conseil:
            self.brouillard = self.conseil.brouillard(c)
        else:
            self.brouillard = bytearray([2]) * (128 * 128)
        self.reveler()

    def placer(self, types, camp, cases):
        """Crée les unités d'une liste de types sur des cases ; renvoie les types restés sans place."""
        types = [t for t in types if self.gfx.valide(t, camp)]
        for t, c in zip(types, cases):
            niveau = self.conseil.niveaux.get(t, 0) if (self.conseil and camp == 0) else 0
            self.unites.append(Unite(t, camp, *c, self.st, niveau))
        return types[len(cases):]

    def armee_joueur(self, centre):
        types = self.types_joueur or (0, 0, 0, 0, 1, 1, 1, 1, 3, 3, 5, 6, 7)
        self.reserve_joueur = self.placer(types[:MAX_ARMEE], 0, self.cases_libres(centre, min(len(types), MAX_ARMEE), 2))
        self.reserve_joueur += list(types[MAX_ARMEE:])
        u = next(u for u in self.unites if u.camp == 0)
        self.centrer(u.x, u.y)

    def bataille(self, centre):
        """Bataille en rase campagne."""
        self.armee_joueur(centre)
        ennemi = [t for t in (0, 0, 0, 0, 1, 1, 1, 3, 3) if self.gfx.valide(t, 1)]
        for t, c in zip(ennemi, self.cases_libres((centre[0] + 24, centre[1] - 4), len(ennemi), 2)):
            self.unites.append(Unite(t, 1, *c, self.st))
        self.camera[0] += 120

    def siege(self, fort):
        """Siège : une garnison dans le fort (archers sur les tours), l'autre armée devant la porte.
        Assaut du joueur : garnison ennemie dedans. Défense : l'armée du joueur dedans, les assaillants dehors."""
        x0, y0, x1, y1 = 2 * fort.X, 2 * fort.Y, 2 * (fort.X + fort.l), 2 * (fort.Y + fort.h)
        dedans = lambda c: x0 <= c[0] < x1 and y0 <= c[1] < y1
        # tours : un archer par groupe de cases « tour »
        tours, vues = [], set()
        for cy in range(y0, y1):
            for cx in range(x0, x1):
                if self.carte.sur_tour((cx, cy)) and (cx, cy) not in vues:
                    tours.append((cx, cy))
                    vues.update((cx + i, cy + j) for i in range(-2, 3) for j in range(-2, 3))
        # cour intérieure : cases libres reliées au centre du fort, sans sortir du rectangle
        depart = next((c for c in self.cases_libres(((x0 + x1) // 2, (y0 + y1) // 2), 40, 1) if dedans(c)), None)
        cour, pile = set(), [depart] if depart else []
        while pile:
            c = pile.pop()
            if c in cour or not dedans(c) or not self.carte.libre(*c):
                continue
            cour.add(c)
            pile.extend(((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)))
        cour = sorted(cour, key=lambda c: (c[0] - (x0 + x1) / 2) ** 2 + (c[1] - (y0 + y1) / 2) ** 2)
        cour = [c for c in cour if c[0] % 2 == 0 and c[1] % 2 == 0]
        tours = tours[::max(1, len(tours) // 6)][:6]  # au plus 6 archers postés, répartis sur les remparts
        # devant la porte principale, hors de portée des tours
        if fort.portes:
            px = 2 * (fort.X + fort.portes[0][0]) + 3
            py = 2 * (fort.Y + fort.portes[0][1]) + 4
        else:
            px, py = (x0 + x1) // 2, y1
        devant = (px, min(py + 22, 250))
        if self.conseil and self.conseil.mission and not self.defense:
            devant = tuple(self.conseil.t['depart']['position_armee'])  # FUN_00444785(3, type, 0, 0xb2, 0xa4)
        if self.defense:
            garnison, camp = list(self.types_joueur or ()), 0
        elif self.conseil and self.comte_bataille is not None:
            garnison, camp = list(self.conseil.garnisons[self.comte_bataille]), 1
        else:
            garnison, camp = [0, 0, 0, 0, 3, 3, 1, 1] + [1] * len(tours), 1
        random.shuffle(garnison)
        archers = [t for t in garnison if t == 1][:len(tours)]
        reste = [t for t in garnison if t != 1] + [1] * (garnison.count(1) - len(archers))
        reste = [t for t in reste if t not in (5,)] + [t for t in reste if t == 5]  # les béliers restent en réserve d'abord
        place = max(0, MAX_ARMEE - len(archers))
        hors = self.placer(archers, camp, tours) + self.placer(reste[:place], camp, cour)
        hors += reste[place:]
        if self.defense:
            self.reserve_joueur = hors
            self.reserve = self.placer(self.assaillants[:MAX_ARMEE], 1, self.cases_libres(devant, min(len(self.assaillants), MAX_ARMEE), 2))
            self.reserve += self.assaillants[MAX_ARMEE:]
            u = next((u for u in self.unites if u.camp == 0), self.unites[0])
            self.centrer(u.x, u.y)
        else:
            self.reserve = hors
            self.armee_joueur(devant)

    # --- passage conseil <-> bataille -----------------------------------------------------------
    def lancer_bataille(self, comte, origine, types, defense=False, assaillants=()):
        """Assaut du joueur sur un comté ennemi, ou défense d'un de ses comtés (assaillants = types ennemis)."""
        self.comte_bataille, self.origine, self.types_joueur = comte, origine, types
        self.assaillants = list(assaillants)
        self.charger(donnees.COMTES[comte], defense)
        self.mode = 'bataille'
        if defense and not any(u.camp == 0 for u in self.unites):
            self.message = 'Défaite...'  # aucun défenseur : le comté tombe sans combat

    def lancer(self, r):
        """Applique une demande du conseil : ('bataille', cible, origine, types) ou ('defense', comté, source, assaillants)."""
        if r[0] == 'bataille':
            self.lancer_bataille(*r[1:])
        else:
            comte, source, assaillants = r[1:]
            self.lancer_bataille(comte, source, list(self.conseil.armees[comte]), True, assaillants)

    def retour_conseil(self, victoire):
        joueur = [u.type for u in self.unites if u.camp == 0 and not u.mort] + getattr(self, 'reserve_joueur', [])
        ennemis = [u.type for u in self.unites if u.camp == 1 and not u.mort] + self.reserve
        for b in self.batiments:  # les dégâts restent jusqu'à réparation (onglet Constructions)
            if getattr(b, 'entree', None) is not None:
                abime = any(0 != p < batiments.PV_TUILE for p in b.pv.values())
                b.entree['pv'] = dict(b.pv) if abime else None
        if self.defense:
            self.conseil.resultat_defense(self.comte_bataille, self.origine, victoire, joueur, ennemis)
        else:
            self.conseil.resultat_bataille(self.comte_bataille, self.origine, victoire, joueur, ennemis)
        self.mode = 'conseil'
        self.unites, self.projectiles, self.effets, self.reserve, self.reserve_joueur = [], [], [], [], []
        suite = self.conseil.prochain_assaut()  # autres batailles de la même semaine
        if suite:
            self.lancer(suite)

    def cases_libres(self, centre, n, ecart):
        res = []
        for r in range(0, 120):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    c = (centre[0] + dx * ecart, centre[1] + dy * ecart)
                    if self.carte.libre(*c) and c not in res:
                        res.append(c)
                        if len(res) == n:
                            return res
        return res

    def case_libre_pres(self, c):
        r = self.cases_libres(c, 1, 1)
        return r[0] if r else None

    def approche(self, u, cible, portee):
        """Chemin vers une case libre d'où l'unité peut frapper la cible, ou None si elle est inaccessible."""
        zone = self.carte.zone(u.case)
        if not zone:
            return None
        cases = []
        for (cx, cy) in getattr(cible, 'cases', [cible.case]):
            for dx in range(-portee, portee + 1):
                for dy in range(-portee, portee + 1):
                    c = (cx + dx, cy + dy)
                    if self.carte.zone(c) == zone:
                        cases.append(c)
        if not cases:
            if isinstance(cible, CibleMur) and not getattr(cible, 'repli', False):
                # tuile visée hors d'atteinte (côté intérieur d'une porte...) : on vise la tuile solide voisine la plus proche
                b = cible.bat
                voisines = sorted((t for t, p in b.pv.items() if p > 0 and max(abs(t[0] - cible.dx), abs(t[1] - cible.dy)) <= 2
                                   and t != (cible.dx, cible.dy)),
                                  key=lambda t: abs(t[0] - cible.dx) + abs(t[1] - cible.dy))
                for t in voisines:
                    autre = CibleMur(b, *t)
                    autre.repli = True
                    ch = self.approche(u, autre, portee)
                    if ch is not None:
                        u.cible = autre
                        return ch
            return None
        if u.case in cases:
            return []
        dest = min(set(cases), key=lambda c: max(abs(c[0] - u.case[0]), abs(c[1] - u.case[1])))
        return self.carte.chemin(u.case, dest)

    def endommager(self, attaquant, mur):
        """Coup d'arme de siège sur une tuile de bâtiment (FUN_00410eb0)."""
        d = batiments.degats_siege(stat(self.st, 'degats', attaquant.type, attaquant.niveau))
        detruites = mur.bat.endommager(self.carte, mur.dx, mur.dy, d)
        x, y = mur.x, mur.y
        if detruites:
            self.sons.jouer('Battle_51', self.volume(attaquant))
            for t in detruites:  # les unités sur une tuile qui s'effondre meurent (666 points de dégâts)
                tx, ty = mur.bat.X + t[0], mur.bat.Y + t[1]
                for v in self.unites:
                    if not v.mort and v.case[0] // 2 == tx and v.case[1] // 2 == ty:
                        v.pv = 0
                        v.mort, v.anim, v.image, v.cible, v.chemin, v.selection = True, 2, 0.0, None, [], False
        else:
            self.sons.jouer('Battle_18', self.volume(attaquant))
        self.effets.append([x, y, 0.0])

    def mur_sous(self, case, camp=1):
        """Tuile d'un bâtiment du camp donné encore debout sous une case, ou None."""
        tx, ty = case[0] // 2, case[1] // 2
        for b in self.batiments:
            t = b.contient(tx, ty)
            if t and b.camp == camp and b.pv.get(t, 0) > 0:
                return CibleMur(b, *t)
        return None

    # --- combat ---------------------------------------------------------------------------------
    def son_attaque(self, u):
        self.sons.jouer(TIR.get(u.type, 'Battle_05'), self.volume(u))

    def volume(self, u):
        l, h = self.vue()
        cx, cy = self.camera[0] + l / 2, self.camera[1] + h / 2
        d = math.hypot(u.x - cx, u.y - cy)
        return max(0.15, 1 - d / 900)

    def degats(self, attaquant, victime):
        if victime.mort:
            return
        dmg = stat(self.st, 'degats', attaquant.type, attaquant.niveau) + random.randint(1, 10)
        dmg -= stat(self.st, 'armure', victime.type, victime.niveau)
        if dmg > 0:
            victime.pv -= dmg
        if victime.cible is None and not victime.chemin:
            victime.cible = attaquant  # riposte
        if victime.pv <= 0:
            victime.pv, victime.mort = 0, True
            victime.anim, victime.image, victime.cible, victime.chemin = 2, 0.0, None, []
            victime.selection = False

    def frapper(self, u):
        c = u.cible
        if c is None or c.mort:
            return
        if stat(self.st, 'recharge', u.type, u.niveau) == 0 and u.type != 5:  # corps à corps
            self.degats(u, c)
            return
        # tir : précision = % de toucher la case visée, sinon ±1 case (code d'origine)
        case = c.case
        if random.randrange(100) >= stat(self.st, 'precision', u.type, u.niveau):
            case = (case[0] + random.randint(-1, 1), case[1] + random.randint(-1, 1))
        if u.type == 5:
            if isinstance(c, CibleMur):
                self.endommager(u, c)
            else:
                self.degats(u, c)
        else:
            self.projectiles.append(Projectile(u, c, case))

    def impact(self, p):
        t = p.tireur
        case = (int(p.tx) // CASE, int(p.ty) // CASE)
        if isinstance(p.cible, CibleMur):
            mur = self.mur_sous(case, 1 - t.camp)
            if mur:
                self.endommager(t, mur)
            return
        rayon = 1 if t.type in (6, 7) else 0
        for v in self.unites:
            if v.camp != t.camp and not v.mort:
                vc = v.case
                if max(abs(vc[0] - case[0]), abs(vc[1] - case[1])) <= rayon:
                    self.degats(t, v)
        if t.type in (6, 7):
            self.effets.append([p.tx, p.ty, 0.0])
            self.sons.jouer('Battle_18', self.volume(t))

    def ia(self):
        """Toute unité inactive attaque l'ennemi le plus proche dans son champ de vision."""
        for u in self.unites:
            if u.mort or u.cible is not None or u.chemin or u.attente > 0:
                continue
            vue = stat(self.st, 'vue', u.type, u.niveau) * 2 + (6 if self.carte.sur_tour(u.case) else 2)  # bonus des tours
            proches = [(u.distance(v), id(v), v) for v in self.unites
                       if v.camp != u.camp and not v.mort and u.distance(v) <= vue]
            if self.defense and u.camp == 1 and (u.type in (5, 6, 7) or not proches):
                cible = self.cible_assaillant(u)  # les assaillants vont au fort : armes de siège sur la porte
                if cible is not None:
                    u.cible = cible
                    continue
            if proches:
                u.cible = min(proches)[2]

    def cible_assaillant(self, u):
        """Assaillant sans ennemi en vue : la porte (ou un mur) pour une arme de siège, sinon le défenseur le plus proche."""
        f = self.fort
        if u.type in (5, 6, 7) and f is not None:
            tuiles = [t for t in f.portes if f.pv.get(t, 0) > 0]
            if not tuiles and not any(self.carte.zone(v.case) == self.carte.zone(u.case)
                                      for v in self.unites if v.camp == 0 and not v.mort):
                tuiles = [t for t, p in f.pv.items() if p > 0]  # porte tombée mais défenseurs encore hors d'atteinte
            if tuiles:
                tx, ty = min(tuiles, key=lambda t: abs(2 * (f.X + t[0]) - u.case[0]) + abs(2 * (f.Y + t[1]) - u.case[1]))
                return CibleMur(f, tx, ty)
        vivants = [v for v in self.unites if v.camp == 0 and not v.mort]
        if vivants:
            return min(vivants, key=lambda v: u.distance(v))
        return None

    # --- interface ------------------------------------------------------------------------------
    def cam(self):
        return int(self.camera[0]), int(self.camera[1])

    def ecran_vers_case(self, pos):
        return int(pos[0] + self.camera[0]) // CASE, int(pos[1] + self.camera[1]) // CASE

    def unite_sous(self, pos, camp=None):
        for u in sorted(self.unites, key=lambda u: -u.y):
            if u.mort or (camp is not None and u.camp != camp):
                continue
            if u.rect_ecran(self.gfx, self.cam()).inflate(-8, -8).collidepoint(pos):
                return u
        return None

    def ordonner(self, pos):
        choisies = [u for u in self.unites if u.selection and u.camp == 0 and not u.mort]
        if not choisies:
            return
        ennemi = self.unite_sous(pos, camp=1)
        mur = self.mur_sous(self.ecran_vers_case(pos))
        siege = [u for u in choisies if u.type in (5, 6, 7)]
        if ennemi:
            for u in choisies:
                u.cible, u.chemin, u.recalcul = ennemi, [], 0
        elif mur and siege:  # seuls le bélier, la catapulte et le canon attaquent les murs
            for u in siege:
                u.cible, u.chemin, u.recalcul = CibleMur(mur.bat, mur.dx, mur.dy), [], 0
            for u in choisies:
                if u not in siege:
                    u.cible = None
            choisies = siege
        else:
            cible = self.ecran_vers_case(pos)
            for u, c in zip(choisies, self.cases_libres(cible, len(choisies), 2)):
                u.ordonner(self.carte, c)
        voix = self.st['sons'].get('voix_type%d' % choisies[0].type)
        if voix:
            self.sons.jouer('Battle_' + random.choice(voix), 0.9)

    def selectionner(self, a, b):
        zone = pygame.Rect(min(a[0], b[0]), min(a[1], b[1]), abs(a[0] - b[0]) + 1, abs(a[1] - b[1]) + 1)
        petit = zone.width < 4 and zone.height < 4
        for u in self.unites:
            u.selection = False
        if petit:
            u = self.unite_sous(a, camp=0)
            if u:
                u.selection = True
            return
        for u in self.unites:
            if u.camp == 0 and not u.mort and zone.colliderect(u.rect_ecran(self.gfx, self.cam())):
                u.selection = True

    def selectionner_type(self, t):
        l, h = self.vue()
        ecran = pygame.Rect(0, 0, int(l), int(h - BARRE / self.zoom))
        for u in self.unites:
            u.selection = (u.camp == 0 and not u.mort and u.type == t
                           and ecran.colliderect(u.rect_ecran(self.gfx, self.cam())))

    def defiler(self, dt):
        vit = 500 * dt
        touches = pygame.key.get_pressed()
        mx, my = self.souris(pygame.mouse.get_pos())
        f = pygame.mouse.get_focused() and dt > 0
        vit /= self.zoom
        L = self.ecran_l()
        if touches[pygame.K_LEFT] or (f and mx < 4):
            self.camera[0] -= vit
        if touches[pygame.K_RIGHT] or (f and mx > L - 5):
            self.camera[0] += vit
        if touches[pygame.K_UP] or (f and my < 4):
            self.camera[1] -= vit
        if touches[pygame.K_DOWN] or (f and my > HAUTEUR - 5):
            self.camera[1] += vit
        l, h = self.vue()
        self.camera[0] = max(0, min(self.camera[0], 128 * TUILE - l))
        self.camera[1] = max(0, min(self.camera[1], 128 * TUILE - h + BARRE / self.zoom))

    def dessiner(self):
        cam = self.cam()
        g = self.gfx
        l, h = self.vue()
        # facteur de rendu : x4 quand l'écran agrandit fort (zoom avant, grand écran), sinon x2
        Z = 4 if self.zoom * self.echelle() > 2.9 else 2
        if getattr(self, '_prechauffe', None) != (self.carte.nom, Z, g.mode):
            self._prechauffe = (self.carte.nom, Z, g.mode)
            g.prechauffer(self.carte.tuiles, [u.type for u in self.unites], Z)
        taille = (max(1, int(l * Z)), max(1, int(h * Z)))
        if self.monde is None or self.monde.get_size() != taille:
            self.monde = pygame.Surface(taille).convert()
        E = self.monde
        E.fill((0, 0, 0))

        def dans(m, pos):  # (surface, zone source) + position -> arguments de blit
            return m[0], pos, m[1]

        def P(x, y):  # coordonnées du monde -> pixels de la fenêtre
            return int((x - cam[0]) * Z), int((y - cam[1]) * Z)

        T = TUILE * Z
        tx0, ty0 = cam[0] // TUILE, cam[1] // TUILE
        nl, nh = int(l // TUILE) + 2, int(h // TUILE) + 2
        for ty in range(ty0, min(ty0 + nh, 128)):
            for tx in range(tx0, min(tx0 + nl, 128)):
                t = self.carte.tuiles[ty * 128 + tx]
                E.blit(*dans(g.morceau('t', t, Z), P(tx * TUILE, ty * TUILE)))
        if self.voir_obstacles:
            voile = pygame.Surface((CASE * Z, CASE * Z), pygame.SRCALPHA)
            voile.fill((255, 0, 0, 90))
            for cy in range(cam[1] // CASE, min(cam[1] // CASE + 2 * nh, 256)):
                for cx in range(cam[0] // CASE, min(cam[0] // CASE + 2 * nl, 256)):
                    if self.carte.bloque[cy * 256 + cx]:
                        E.blit(voile, P(cx * CASE, cy * CASE))
        reperes = []
        for u in sorted(self.unites, key=lambda u: (not u.mort, u.y)):
            if not self.vu(u):
                continue
            src = g.rect(u.type, u.anim, u.camp, int(u.image), u.direction)
            if src is None or src.y < Y_SPRITES:
                continue
            r1 = u.rect_ecran(g, cam)
            E.blit(*dans(g.morceau('s', tuple(src), Z), (r1.x * Z, r1.y * Z)))
            if not u.mort and (u.selection or u.pv < u.pv_max):
                reperes.append((u, r1))  # cercle de sélection et barre de vie : dessinés après l'agrandissement, nets
        for p in self.projectiles:
            if p.tireur.type == 1:
                d = math.hypot(p.tx - p.x, p.ty - p.y) or 1
                pygame.draw.line(E, COULEUR_PROJ[1], P(p.x, p.y),
                                 P(p.x - (p.tx - p.x) / d * 7, p.y - (p.ty - p.y) / d * 7), 2 * Z)
            else:
                pygame.draw.circle(E, COULEUR_PROJ.get(p.tireur.type, (0, 0, 0)), P(p.x, p.y), 3 * Z)
        if self.voir_brouillard and self.brouillard is not None:  # brouillard de guerre : noir = inconnu, voilé = déjà vu
            # une valeur d'opacité par tuile (1 tuile de marge), puis agrandissement lissé : bords du brouillard adoucis
            x0, y0 = max(0, tx0 - 1), max(0, ty0 - 1)
            x1, y1 = min(128, tx0 + nl + 1), min(128, ty0 + nh + 1)
            px = bytearray()
            for ty in range(y0, y1):
                for tx in range(x0, x1):
                    i = ty * 128 + tx
                    px += b'\0\0\0' + (b'\0' if self.visible[i] else b'\xff' if self.brouillard[i] == 2 else b'\x78')
            voile = pygame.image.frombuffer(bytes(px), (x1 - x0, y1 - y0), 'RGBA')
            voile = pygame.transform.smoothscale(voile, ((x1 - x0) * 8, (y1 - y0) * 8))  # dégradé doux, peu coûteux
            brume = (voile, x0, y0, x1, y1)  # posée plus bas, à la taille de l'écran (bien moins de pixels qu'en zoom arrière)
        else:
            brume = None
        for e in self.effets:
            src = g.rect(9, 1, 2, min(int(e[2]), 7), 2)
            if src and src.y >= Y_SPRITES:
                E.blit(*dans(g.morceau('s', tuple(src), Z), P(e[0] - 16, e[1] - 20)))
        # image du monde -> écran (agrandie ou réduite selon le zoom et la résolution, avec lissage)
        A = self.affichage
        W, H = A.get_size()
        k = self.echelle()
        vis = E  # surface entière (pas de sous-surface : smoothscale la déforme sur certains processeurs)
        if vis.get_size() == (W, H):
            A.blit(vis, (0, 0))
        elif (vis.get_width() * 2, vis.get_height() * 2) == (W, H):
            A.blit(pygame.transform.scale2x(vis), (0, 0))  # zoom x2 : agrandissement EPX, reste net
        else:
            A.blit(pygame.transform.smoothscale(vis, (W, H)), (0, 0))
        if brume:
            voile, x0, y0, x1, y1 = brume
            f = self.zoom * k  # pixels d'écran par pixel du monde
            taille = (int((x1 - x0) * TUILE * f) + 1, int((y1 - y0) * TUILE * f) + 1)
            A.blit(pygame.transform.scale(voile, taille),
                   (int((x0 * TUILE + TUILE / 2 - cam[0]) * f), int((y0 * TUILE + TUILE / 2 - cam[1]) * f)))
        f = self.zoom * k  # pixels d'écran par pixel du monde
        e = max(1, int(f))
        for u, r1 in reperes:
            r = pygame.Rect(int(r1.x * f), int(r1.y * f), int(r1.w * f), int(r1.h * f))
            if u.selection:
                pygame.draw.ellipse(A, (255, 255, 0), r.inflate(-r.w // 3, -r.h // 2).move(0, r.h // 5), e)
            lb = max(12 * f, r.w / 2)
            x0, y0, hb = int(r.centerx - lb / 2), r.top + e, max(3, int(1.5 * f))
            pygame.draw.rect(A, (40, 0, 0), (x0, y0, int(lb), hb))
            part = u.pv / u.pv_max
            coul = (40, 200, 40) if part > 0.5 else (230, 180, 0) if part > 0.25 else (220, 30, 30)
            pygame.draw.rect(A, coul, (x0, y0, max(e, int(lb * part)), hb))
        if self.debut_selection:  # cadre de sélection (le point de départ est gardé en coordonnées du monde)
            ax, ay = self.debut_selection
            a = ((ax - cam[0]) * f, (ay - cam[1]) * f)
            b = pygame.mouse.get_pos()
            pygame.draw.rect(A, (255, 255, 0), (min(a[0], b[0]), min(a[1], b[1]),
                                                abs(a[0] - b[0]), abs(a[1] - b[1])), e)
        E = A
        if self.message:
            s = self.grande.render(self.message, True, (240, 220, 160))
            E.blit(s, s.get_rect(center=(W // 2, int((HAUTEUR // 2 - 40) * k))))
            if self.conseil:
                s = self.police.render('Entrée : retour au conseil', True, (240, 220, 160))
                E.blit(s, s.get_rect(center=(W // 2, H // 2)))
        pygame.draw.rect(E, (20, 16, 12), (0, int((HAUTEUR - BARRE) * k), W, int(BARRE * k) + 1))
        sel = [u for u in self.unites if u.selection]
        vivants = [sum(1 for u in self.unites if u.camp == c and not u.mort) for c in (0, 1)]
        info = ''
        if len(sel) == 1:
            u = sel[0]
            info = ' : %s %d/%d PV' % (NOMS.get(u.type, '?'), u.pv, u.pv_max)
        mode = MODES[g.mode] + (' (T : tuiles %s)' % FILTRES_TUILES[g.filtre_tuiles] if g.mode == 'xbr' else '')
        texte = '%s | vous %d - ennemis %d | %d choisie(s)%s | L : %s%s' % (
            self.carte.nom.capitalize(), vivants[0], vivants[1], len(sel), info, mode,
            ' | Échap : retraite' if self.conseil else '')
        texte += ' | molette : zoom x%g | B : brouillard | M : carte | F11' % self.zoom
        s = self.police.render(texte, True, (230, 210, 160))
        if s.get_width() > W - 12:
            s = pygame.transform.smoothscale(s, (W - 12, s.get_height() * (W - 12) // s.get_width()))
        E.blit(s, (int(6 * k), int((HAUTEUR - BARRE + 5) * k)))
        self.minicarte(E, k)
        self.dessiner_curseur(E, k)

    # --- mini-carte (comme l'original : un pixel par tuile, couleurs de MINIMAP.WG selon le brouillard) ----------
    def rect_minicarte(self):
        return pygame.Rect(MINI, MINI, 128, 128)

    def minicarte(self, A, k):
        if not getattr(self, 'voir_minicarte', True):
            return
        maintenant = pygame.time.get_ticks()
        fond = getattr(self, '_mini', None)
        if fond is None or fond[1] != self.carte.nom or maintenant - fond[2] > 500:
            coul = self.gfx.couleurs_minicarte(self.source)
            br = self.brouillard if self.voir_brouillard else None
            vis, tu = self.visible, self.carte.tuiles
            px = bytearray()
            for i in range(16384):
                etat = 0 if br is None or (vis is not None and vis[i]) else min(2, br[i])
                j = tu[i] * 3 + etat
                px += bytes(coul[j]) if j < len(coul) else (b'\0\0\0' if etat == 2 else b'\x60\x60\x60')
            fond = (pygame.image.frombuffer(bytes(px), (128, 128), 'RGB').convert(), self.carte.nom, maintenant)
            self._mini = fond
        img = fond[0].copy()
        for u in self.unites:
            if not u.mort and (u.camp == 0 or self.vu(u)):
                img.fill((255, 230, 60) if u.camp == 0 else (230, 30, 30), (int(u.x) // TUILE, int(u.y) // TUILE, 2, 2))
        l, h = self.vue()
        pygame.draw.rect(img, (255, 255, 255), (int(self.camera[0] / TUILE), int(self.camera[1] / TUILE),
                                                max(2, int(l / TUILE)), max(2, int(h / TUILE))), 1)
        r = self.rect_minicarte()
        A.blit(self.gfx.cadre_minicarte(k), (0, 0))
        cadre = pygame.Rect(int(r.x * k), int(r.y * k), int(r.w * k), int(r.h * k))
        A.blit(pygame.transform.scale(img, cadre.size), cadre)

    def clic_minicarte(self, e):
        """Clic gauche (ou glisser) sur la mini-carte : centre la vue ; clic droit : y envoie les unités choisies."""
        if not getattr(self, 'voir_minicarte', True) or not hasattr(e, 'pos'):
            return False
        lx, ly = self.souris(e.pos)
        r = self.rect_minicarte()
        dedans = r.collidepoint(lx, ly)
        wx = (min(max(lx, r.x), r.right - 1) - r.x + 0.5) * TUILE
        wy = (min(max(ly, r.y), r.bottom - 1) - r.y + 0.5) * TUILE
        if e.type == pygame.MOUSEBUTTONDOWN and dedans and e.button == 1:
            self.glisse_mini = True
            self.centrer(wx, wy)
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and dedans and e.button == 3:
            self.ordonner((wx - self.camera[0], wy - self.camera[1]))
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and lx < CADRE_MINI[2] and ly < CADRE_MINI[3]:
            return True  # clic sur le cadre de pierre : ignoré
        if e.type == pygame.MOUSEMOTION and getattr(self, 'glisse_mini', False):
            self.centrer(wx, wy)
            return True
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and getattr(self, 'glisse_mini', False):
            self.glisse_mini = False
            return True
        return False

    # --- curseur de la souris selon l'action (sprites de BATTLE.ART, comme l'original) --------------------
    def nom_curseur(self):
        mx, my = self.souris(pygame.mouse.get_pos())
        if getattr(self, 'voir_minicarte', True) and mx < CADRE_MINI[2] and my < CADRE_MINI[3]:
            return 'normal'
        if getattr(self, 'glisse_mini', False) or self.debut_selection:
            return 'normal'
        dx = -1 if mx < 4 else 1 if mx > self.ecran_l() - 5 else 0
        dy = -1 if my < 4 else 1 if my > HAUTEUR - 5 else 0
        if dx or dy:
            return 'fleche%d' % ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)).index((dx, dy))
        if my >= HAUTEUR - BARRE:
            return 'normal'
        pos = self.vers_vue((mx, my))
        clin = '2' if pygame.time.get_ticks() // 300 % 2 else ''
        choisies = [u for u in self.unites if u.selection and u.camp == 0 and not u.mort]
        if choisies:
            ennemi = self.unite_sous(pos, camp=1)
            if ennemi and self.vu(ennemi):
                return 'attaquer' + clin
            case = self.ecran_vers_case(pos)
            if any(u.type in (5, 6, 7) for u in choisies) and self.mur_sous(case):
                return 'attaquer' + clin
        if self.unite_sous(pos, camp=0):
            return 'choisir'
        if choisies and self.carte.libre(*self.ecran_vers_case(pos)):
            return 'marcher' + clin
        return 'normal'

    def dessiner_curseur(self, A, k):
        if not pygame.mouse.get_focused():
            return
        nom = self.nom_curseur()
        img, chaud = self.gfx.curseur(nom, k)
        x, y = pygame.mouse.get_pos()
        if nom.startswith('fleche'):  # flèche de défilement : collée au bord, entièrement visible
            W, H = A.get_size()
            x = min(max(0, x - img.get_width() // 2), W - img.get_width())
            y = min(max(0, y - img.get_height() // 2), H - img.get_height())
        else:
            x, y = x - chaud[0], y - chaud[1]
        A.blit(img, (int(x), int(y)))

    def evenement(self, e):
        if self.clic_minicarte(e):
            return True
        if hasattr(e, 'pos'):
            e.pos = self.vers_vue(self.souris(e.pos))
        if e.type == pygame.MOUSEWHEEL:
            self.zoomer(1 if e.y > 0 else -1, self.souris(pygame.mouse.get_pos()))
            return True
        if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
            return False
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.debut_selection = (e.pos[0] + self.camera[0], e.pos[1] + self.camera[1])  # point du monde
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.debut_selection:
            a = (self.debut_selection[0] - self.camera[0], self.debut_selection[1] - self.camera[1])
            self.selectionner(a, e.pos)
            self.debut_selection = None
            maintenant = pygame.time.get_ticks()
            u = self.unite_sous(e.pos, camp=0)
            dernier = getattr(self, 'dernier_clic', None)
            if u and dernier and maintenant - dernier[0] < 400 and dernier[1] is u:
                self.selectionner_type(u.type)  # double-clic : toutes les unités de ce type à l'écran
            self.dernier_clic = (maintenant, u)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
            self.ordonner(e.pos)
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_f:
                self.voir_obstacles = not self.voir_obstacles
            elif e.key == pygame.K_b:
                self.voir_brouillard = not self.voir_brouillard
            elif e.key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS):
                self.zoomer(1)
            elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.zoomer(-1)
            elif e.key == pygame.K_l:
                modes = self.gfx.modes()
                self.gfx.preparer(modes[(modes.index(self.gfx.mode) + 1) % len(modes)])
            elif e.key == pygame.K_t and self.gfx.mode == 'xbr':
                ft = list(FILTRES_TUILES)
                self.gfx.filtre_tuiles = ft[(ft.index(self.gfx.filtre_tuiles) + 1) % len(ft)]
                self._prechauffe = None
            elif e.key == pygame.K_m:
                self.voir_minicarte = not self.voir_minicarte
            elif e.key == pygame.K_p:
                self.sons.musique()
            elif e.key == pygame.K_s:
                for u in self.unites:
                    if u.selection:
                        u.chemin, u.cible = [], None
            elif e.key == pygame.K_TAB and not self.conseil:
                i = donnees.COMTES.index(self.carte.nom)
                self.charger(donnees.COMTES[(i + 1) % len(donnees.COMTES)])
        return True

    def mettre_a_jour(self, dt):
        self.defiler(dt)
        self.revele -= dt
        if self.revele <= 0:
            self.revele = 0.2
            self.reveler()
        self.ia()
        for u in self.unites:
            u.avancer(dt, self)
        for p in self.projectiles:
            p.avancer(dt, self)
        self.projectiles = [p for p in self.projectiles if not p.fini]
        for e in self.effets:
            e[2] += dt * 12
        self.effets = [e for e in self.effets if e[2] < 8]
        vivants = [sum(1 for u in self.unites if u.camp == c and not u.mort) for c in (0, 1)]
        if not self.message:
            if vivants[1] == 0:
                self.message = 'Victoire !'
            elif vivants[0] == 0:
                self.message = 'Défaite...'
        if self.sons.actif and self.sons.pistes and not pygame.mixer.music.get_busy():
            self.sons.musique()

    def boucle(self, capture=None, images_max=None):
        horloge = pygame.time.Clock()
        n = 0
        while True:
            dt = horloge.tick(60) / 1000
            if images_max:
                dt = 1 / 30
            for e in pygame.event.get():
                if e.type == pygame.KEYDOWN and (e.key == pygame.K_F11 or (
                        e.key == pygame.K_RETURN and e.mod & pygame.KMOD_ALT)):
                    self.plein_ecran = not self.plein_ecran  # F11 ou Alt+Entrée : plein écran à la résolution du bureau
                    try:
                        self.fenetre()
                    except pygame.error:
                        self.plein_ecran = False
                        self.fenetre()
                    continue
                if e.type == pygame.VIDEORESIZE:
                    self.affichage = pygame.display.get_surface()
                    continue
                if self.mode == 'conseil':
                    if hasattr(e, 'pos'):
                        e.pos = self.souris(e.pos)
                    r = self.conseil.evenement(e)
                    if r and r[0] == 'quitter':
                        return
                    if r and r[0] in ('bataille', 'defense'):
                        self.lancer(r)
                    continue
                if not self.evenement(e):
                    if self.conseil and e.type != pygame.QUIT:  # Échap en bataille = retraite
                        self.retour_conseil(False)
                        continue
                    return
                if self.message and self.conseil and e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self.retour_conseil(self.message.startswith('Victoire'))
            pygame.mouse.set_visible(self.mode == 'conseil')  # en bataille : curseurs du jeu, dessinés par le moteur
            if self.mode == 'conseil':
                self.conseil.dessiner(self.ecran)
                s, ox, oy = self.cadre_conseil()
                self.affichage.fill((0, 0, 0))
                taille = (int(LARGEUR * Z * s), int(HAUTEUR * Z * s))
                img = self.ecran if taille == self.ecran.get_size() else pygame.transform.smoothscale(self.ecran, taille)
                self.affichage.blit(img, (int(ox), int(oy)))
            else:
                self.mettre_a_jour(min(dt, 0.1))
                self.dessiner()
            pygame.display.flip()
            n += 1
            if images_max and n >= images_max:
                if capture:
                    pygame.image.save(self.affichage, capture)
                return


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)
    if not args or args[0].startswith('-'):
        print(__doc__)
        return 1
    comte = None  # sans --comte : partie complète, en commençant par le conseil
    if '--comte' in args:
        comte = args[args.index('--comte') + 1].upper()
    elif '--test' in args:
        comte = 'BRASOV'
    lissage = args[args.index('--lissage') + 1] if '--lissage' in args else None
    hd = args[args.index('--hd') + 1] if '--hd' in args else os.path.join(os.path.dirname(ICI), 'extrait', 'hd')
    jeu = Jeu(donnees.Source(args[0]), comte, lissage, hd, '--plein-ecran' in args)
    if '--test' in args:  # mode automatique : attaque générale puis capture d'écran
        sortie = args[args.index('--test') + 1]
        images = int(args[args.index('--images') + 1]) if '--images' in args else 150
        ennemis = [u for u in jeu.unites if u.camp == 1]
        for u in jeu.unites:
            if u.camp == 0:
                u.cible = ennemis[0]
        jeu.boucle(images_max=images)
        vivants = [u for u in jeu.unites if not u.mort] or jeu.unites
        u = max(vivants, key=lambda u: sum(1 for v in vivants if abs(v.x - u.x) + abs(v.y - u.y) < 200))
        jeu.centrer(u.x, u.y)
        jeu.defiler(0)
        jeu.dessiner()
        pygame.image.save(jeu.affichage, sortie)
        print('vivants joueur/ennemi :', [sum(1 for u in jeu.unites if u.camp == c and not u.mort) for c in (0, 1)],
              'projectiles', len(jeu.projectiles))
    else:
        jeu.boucle()
    pygame.quit()
    return 0
