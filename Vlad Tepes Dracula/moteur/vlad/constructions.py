"""Constructions du conseil : bâtir, améliorer et réparer ponts, tours de guet, forts et châteaux (d'après DRACULA.EXE).

- Ce qu'on peut bâtir dépend du niveau d'architecture : niveau N = catégories 0..N-1 (FUN_00435e2a).
- Emplacements : tables 0x471958/0x480598 (positions) et 0x471178 (nombre d'emplacements par comté, catégorie, modèle).
  Forts et châteaux partagent leurs numéros d'emplacement ; un pont est libre si aucun pont n'est à la même position.
- Un seul chantier à la fois par comté (DAT_0048f2e0), payé d'avance, remboursé si on l'annule.
- Amélioration : fort -> château, ou modèle supérieur de la même catégorie, au même emplacement,
  pour 1,25 x la différence de coût, de bois et de durée (FUN_0042f8d8).
- Réparation : coût x dégâts / structure totale x 1,1 (au moins 1).
- Fin de chantier (FUN_0043f401) : un fort ou un château neuf multiplie la production du comté.
"""
from . import batiments


class Chantiers:
    def __init__(self, conseil, catalogue):
        self.c = conseil
        self.cat = catalogue
        self.t = conseil.t['constructions']
        self.batiments = {k: [{'cat': cat, 'sub': sub, 'site': site, 'pv': None}
                              for cat, sub, site in catalogue.depart(k)
                              if catalogue.position(k, cat, sub, site) is not None] for k in range(12)}
        self.chantier = {}  # comté -> {'mode', 'cat', 'sub', 'site', 'cible', 'semaines', 'duree', 'or', 'bois'}
        self.mode = 2  # 0 réparer, 1 améliorer, 2 construire (param_1[0x193])
        self.categorie, self.modele = 0, 0

    # --- tables --------------------------------------------------------------------------------
    def cout(self, cat, sub):
        i = cat * 42 + sub
        return self.t['cout_or'][i], self.t['cout_bois'][i], self.t['duree'][i]

    def nb_sites(self, comte, cat, sub):
        return self.cat.t['nb_sites'][comte * 168 + cat * 42 + sub]

    def categories(self):
        return list(range(min(4, self.c.niveau_architecture)))

    def nb_modeles(self, cat):
        if cat == 0:
            return 1 if self.c.niveau_architecture == 1 else 3
        return self.t['modeles'][cat]

    def modeles_reels(self, cat, modele):
        """Pour les ponts, un « modèle » regroupe plusieurs gabarits (selon la forme de la rivière)."""
        return self.t['types_ponts'][modele] if cat == 0 else [modele]

    def cout_affiche(self, cat, modele):
        return self.cout(cat, self.modeles_reels(cat, modele)[0])

    def gabarit_taille(self, cat, sub):
        x1, y1, x2, y2 = self.cat.gabarit(cat, sub)
        return x2 - x1, y2 - y1

    # --- repères de la mini-carte ----------------------------------------------------------------
    def icone(self, cat, sub, dispo):
        jeu = self.t['dispo' if dispo else 'existant'][str(cat)]
        if cat == 0:
            l, h = self.gabarit_taille(cat, sub)
            return jeu[0 if l >= h else 1]
        return jeu[sub if cat >= 2 else 0]

    def decalage(self, cat):
        return (-2, -1) if cat == 1 else (0, 0)

    def repere(self, comte, cat, sub, site, dispo):
        """(x, y, rect planche) du repère sur la mini-carte (coordonnées en tuiles = pixels)."""
        x, y = self.cat.position(comte, cat, sub, site)
        dx, dy = self.decalage(cat)
        return x + dx, y + dy, self.icone(cat, sub, dispo)

    def sites_libres(self, comte):
        """Emplacements libres pour la catégorie et le modèle choisis : [(sub, site)]."""
        cat, modele = self.categorie, self.modele
        existants = self.batiments[comte]
        res = []
        if cat == 0:
            pris = {self.cat.position(comte, b['cat'], b['sub'], b['site']) for b in existants if b['cat'] == 0}
            for sub in self.modeles_reels(0, modele):
                for site in range(self.nb_sites(comte, 0, sub)):
                    if self.cat.position(comte, 0, sub, site) not in pris:
                        res.append((sub, site))
        elif cat == 1:
            pris = {b['site'] for b in existants if b['cat'] == 1}
            for sub in range(3):
                for site in range(self.nb_sites(comte, 1, sub)):
                    if site not in pris:
                        res.append((sub, site))
        else:
            pris = {b['site'] for b in existants if b['cat'] >= 2}
            res = [(modele, s) for s in range(self.nb_sites(comte, cat, modele)) if s not in pris]
        return res

    def ameliorables(self, comte):
        """Bâtiments qu'on peut améliorer vers la catégorie et le modèle choisis (FUN_004255f9, cas 1)."""
        cat, modele = self.categorie, self.modele
        if cat < 2:
            return []
        prix = self.cout(cat, modele)[0]
        res = []
        for b in self.batiments[comte]:
            if b['cat'] < 2 or self.cout(b['cat'], b['sub'])[0] >= prix:
                continue
            if b['cat'] == 2 and cat == 3 and b['site'] < self.nb_sites(comte, 3, modele):
                res.append(b)
            elif b['cat'] == cat and b['sub'] < modele and b['site'] < self.nb_sites(comte, cat, modele):
                res.append(b)
        return res

    @staticmethod
    def degats(b):
        if not b['pv']:
            return 0, 0
        total = sum(batiments.PV_TUILE for p in b['pv'].values() if p != 0)
        perdu = sum(batiments.PV_TUILE - max(p, 0) for p in b['pv'].values() if p != 0)
        return perdu, total

    def endommages(self, comte):
        return [b for b in self.batiments[comte] if self.degats(b)[0] > 0]

    def prix_reparation(self, b):
        perdu, total = self.degats(b)
        r = perdu / total if total else 1.0
        f = self.t['facteur_reparation']
        return [max(1, int(r * v * f)) for v in self.cout(b['cat'], b['sub'])]

    def prix_amelioration(self, b):
        f = self.t['facteur_amelioration']
        neuf, vieux = self.cout(self.categorie, self.modele), self.cout(b['cat'], b['sub'])
        return [int((n - v) * f) for n, v in zip(neuf, vieux)]

    # --- actions -------------------------------------------------------------------------------
    def lancer(self, comte, mode, cat, sub, site, prix, cible=None):
        o, bois, duree = prix
        res = self.c.ressources
        if res[0] < o or res[1] < bois:
            self.c.message = 'Il faut %d pièces d\'or et %d de bois.' % (o, bois)
            return
        res[0] -= o
        res[1] -= bois
        self.chantier[comte] = {'mode': mode, 'cat': cat, 'sub': sub, 'site': site, 'cible': cible,
                                'semaines': 0, 'duree': duree, 'or': o, 'bois': bois}
        verbe = ('Réparation', 'Amélioration', 'Construction')[mode]
        self.c.message = '%s : %s, %d semaine(s).' % (verbe, self.nom(cat, sub), duree)

    def annuler(self, comte):
        ch = self.chantier.pop(comte)
        self.c.ressources[0] += ch['or']
        self.c.ressources[1] += ch['bois']
        self.c.message = 'Chantier annulé, or et bois rendus.'

    def nom(self, cat, sub):
        n = batiments.NOMS[cat]
        return n if cat < 2 else '%s %d' % (n, sub + 1)

    def clic_carte(self, comte, x, y):
        """Clic sur la mini-carte (coordonnées relatives à la mini-carte)."""
        if comte in self.chantier:
            self.c.message = 'Un chantier est déjà en cours ici. Recliquez sur son bouton pour l\'annuler.'
            return

        def touche(cat, sub, site, dispo):
            rx, ry, r = self.repere(comte, cat, sub, site, dispo)
            return rx - 1 <= x < rx + r[2] - r[0] + 1 and ry - 1 <= y < ry + r[3] - r[1] + 1

        if self.mode == 2:
            for sub, site in self.sites_libres(comte):
                if touche(self.categorie, sub, site, True):
                    return self.lancer(comte, 2, self.categorie, sub, site, self.cout(self.categorie, sub))
            self.c.message = 'Cliquez sur un emplacement libre (repère clair).'
        elif self.mode == 1:
            for b in self.ameliorables(comte):
                if touche(b['cat'], b['sub'], b['site'], False):
                    return self.lancer(comte, 1, self.categorie, self.modele, b['site'], self.prix_amelioration(b), b)
            self.c.message = 'Rien à améliorer ici vers ce modèle.'
        else:
            for b in self.endommages(comte):
                if touche(b['cat'], b['sub'], b['site'], False):
                    return self.lancer(comte, 0, b['cat'], b['sub'], b['site'], self.prix_reparation(b), b)
            self.c.message = 'Aucun bâtiment endommagé ici.'

    def semaine(self):
        """Avance les chantiers d'une semaine ; renvoie les messages."""
        msg = []
        prod = self.c.production
        for comte, ch in list(self.chantier.items()):
            ch['semaines'] += 1
            if ch['semaines'] < ch['duree']:
                continue
            del self.chantier[comte]
            if self.c.proprio[comte] != 0:
                continue  # comté perdu entre-temps
            lieu = self.c.nom_comte(comte)
            if ch['mode'] == 0:
                ch['cible']['pv'] = None
                msg.append('%s réparé à %s.' % (self.nom(ch['cat'], ch['sub']).capitalize(), lieu))
            elif ch['mode'] == 1:
                b = ch['cible']
                b.update(cat=ch['cat'], sub=ch['sub'], pv=None)
                msg.append('Amélioration terminée à %s : %s.' % (lieu, self.nom(ch['cat'], ch['sub'])))
            else:
                self.batiments[comte].append({'cat': ch['cat'], 'sub': ch['sub'], 'site': ch['site'], 'pv': None})
                txt = '%s bâti à %s.' % (self.nom(ch['cat'], ch['sub']).capitalize(), lieu)
                m = self.t['multiplicateur'].get(str(ch['cat']))
                if m and ch['sub'] < len(m):
                    for nom in ('or', 'bois', 'vivres', 'paysans'):
                        prod[nom][comte] = int(prod[nom][comte] * m[ch['sub']])
                    txt += ' Production x%.2f.' % m[ch['sub']]
                msg.append(txt)
        return msg
