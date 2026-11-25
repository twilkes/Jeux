"""Bâtiments des comtés (ponts, tours de guet, forts, châteaux), d'après DRACULA.EXE.

BUILDING.MAP contient 3 couches de 128x128 tuiles et 3 grilles de 256x256 drapeaux :
couche 0 = intact, couche 1 = endommagé, couche 2 = détruit (FUN_00412110 / FUN_00410ba0).
Un bâtiment est un rectangle de ce catalogue (gabarit) recopié sur la carte du comté à une position
donnée par les tables de l'exécutable. Chaque tuile « solide » a 255 points de structure :
en dessous de 181 elle passe à la couche « endommagé », sous 1 à la couche « détruit ».
"""
import json, os, random
from . import donnees

ICI = os.path.dirname(os.path.abspath(__file__))
BLOQUE, TOUR, MURET = 0x40000, 0x100000, 0x1000000
PV_TUILE, SEUIL_ABIME = 255, 0xB5
# portes (tuile en haut à gauche, relative au bâtiment, 3x2 tuiles) : FUN_0040f1b0, champs 0x9d0/0x9d1 et 0x9d3/0x9d4
PORTES = {(2, 0): [(4, 8)], (2, 1): [(5, 12)], (2, 2): [(7, 16)],
          (3, 0): [(9, 18)], (3, 1): [(14, 24)], (3, 2): [(19, 37), (19, 24)],
          (3, 3): [(13, 22)], (3, 4): [(18, 28)], (3, 5): [(23, 41), (23, 28)]}
NOMS = {0: 'pont', 1: 'tour de guet', 2: 'fort', 3: 'château'}


class Catalogue:
    def __init__(self, source):
        self.tuiles, self.drapeaux = donnees.lire_carte(source.lire('COUNTIES/BUILDING.MAP'))
        self.t = json.load(open(os.path.join(ICI, 'tables_batiments.json'), encoding='utf-8'))

    def gabarit(self, cat, modele):
        i = cat * 42 + modele
        return self.t['x1'][i], self.t['y1'][i], self.t['x2'][i], self.t['y2'][i]

    def position(self, comte, cat, modele, site):
        p = self.t['positions'].get('%d,%d,%d,%d' % (comte, cat, modele, site))
        return tuple(p) if p is not None else None

    def depart(self, comte):
        """Bâtiments présents en début de partie dans ce comté (FUN_00414790)."""
        return [tuple(b[1:]) for b in self.t['initiaux'] if b[0] == comte]


class Batiment:
    def __init__(self, cat_, comte, cat, modele, site, camp=1):
        self.cat, self.modele, self.camp = cat, modele, camp
        self.catalogue = cat_
        self.X, self.Y = cat_.position(comte, cat, modele, site)
        self.x1, self.y1, x2, y2 = cat_.gabarit(cat, modele)
        self.l, self.h = x2 - self.x1, y2 - self.y1
        self.portes = [(gx + i, gy + j) for gx, gy in PORTES.get((cat, modele), []) for i in range(3) for j in range(2)]
        # points de structure : 255 si une des 4 cases de la tuile bloque ou est une tour (FUN_0040f8a0)
        self.pv = {}
        for dx in range(self.l):
            for dy in range(self.h):
                solide = any(self.drapeau(0, dx, dy, i, j) & BLOQUE for i in (0, 1) for j in (0, 1))
                solide = solide or self.drapeau(0, dx, dy, 0, 0) & (BLOQUE | TOUR)
                self.pv[dx, dy] = PV_TUILE if solide else 0

    @property
    def nom(self):
        return NOMS.get(self.cat, 'bâtiment')

    def drapeau(self, couche, dx, dy, i, j):
        return self.catalogue.drapeaux[couche][(2 * (self.y1 + dy) + j) * 256 + 2 * (self.x1 + dx) + i]

    def etat(self, dx, dy):
        pv = self.pv[dx, dy]
        return 0 if pv == 0 else 2 if pv < 1 else 1 if pv < SEUIL_ABIME else 0

    def contient(self, tx, ty):
        """Tuile du comté -> tuile du bâtiment, ou None."""
        dx, dy = tx - self.X, ty - self.Y
        return (dx, dy) if 0 <= dx < self.l and 0 <= dy < self.h else None

    def poser(self, carte):
        for dx in range(self.l):
            for dy in range(self.h):
                self.poser_tuile(carte, dx, dy)

    def poser_tuile(self, carte, dx, dy):
        """Recopie la tuile et ses 4 cases de passage selon l'état (règle de FUN_00412110)."""
        k = self.etat(dx, dy)
        cat = self.catalogue
        tx, ty = self.X + dx, self.Y + dy
        carte.tuiles[ty * 128 + tx] = cat.tuiles[k][(self.y1 + dy) * 128 + self.x1 + dx]
        for i in (0, 1):
            for j in (0, 1):
                f = self.drapeau(k, dx, dy, i, j)
                if f & MURET:
                    v = MURET | BLOQUE
                elif self.drapeau(0, dx, dy, i, j) & MURET:
                    v = BLOQUE
                else:
                    v = f
                carte.poser_drapeau(2 * tx + i, 2 * ty + j, v)

    def endommager(self, carte, dx, dy, degats):
        """Dégâts sur une tuile (FUN_00410eb0). Renvoie la liste des tuiles détruites."""
        if self.pv.get((dx, dy), 0) <= 0:
            return []
        groupe = self.portes if (dx, dy) in self.portes else [(dx, dy)]  # une porte encaisse d'un bloc
        detruites = []
        for t in groupe:
            if self.pv.get(t, 0) <= 0:
                continue
            self.pv[t] -= degats
            if self.pv[t] < 1:
                self.pv[t] = -1
                detruites.append(t)
                # les tuiles voisines intactes deviennent endommagées
                for vx in (-1, 0, 1):
                    for vy in (-1, 0, 1):
                        v = (t[0] + vx, t[1] + vy)
                        if self.pv.get(v, 0) >= SEUIL_ABIME:
                            self.pv[v] = SEUIL_ABIME - 1
                            self.poser_tuile(carte, *v)
            self.poser_tuile(carte, *t)
        if detruites and groupe is self.portes:  # la porte tombe en entier, y compris ses morceaux décoratifs
            for t in self.portes:
                if self.pv.get(t, 0) == 0:
                    self.pv[t] = -1
                    self.poser_tuile(carte, *t)
        return detruites

    def debout(self):
        return any(p > 0 for p in self.pv.values())


def charger(source, carte, comte, cat_=None, liste=None):
    """Pose sur la carte les bâtiments du comté : ceux de la partie (liste d'entrées {cat, sub, site, pv})
    ou, à défaut, ceux de départ. Les ponts restent neutres."""
    cat_ = cat_ or Catalogue(source)
    if liste is None:
        liste = [{'cat': c, 'sub': m, 'site': s, 'pv': None} for c, m, s in cat_.depart(comte)]
    res = []
    for e in liste:
        if cat_.position(comte, e['cat'], e['sub'], e['site']) is None:
            continue
        b = Batiment(cat_, comte, e['cat'], e['sub'], e['site'], camp=1 if e['cat'] >= 1 else None)
        b.entree = e
        if e.get('pv'):
            b.pv.update(e['pv'])
        b.poser(carte)
        res.append(b)
    return res


def degats_siege(st_degats):
    """Dégâts d'un tir de siège sur une tuile : 1 à 6 + dégâts de l'unité (code d'origine)."""
    return random.randint(1, 6) + st_degats
