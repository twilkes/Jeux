"""Accès aux fichiers du jeu d'origine : dossier extrait ou image CD (Dracula.bin)."""
import os, struct

SECT, OFF = 2352, 16


class Source:
    """Lit un fichier du jeu par son chemin (ex. 'ART/BATTLE.ART'), depuis un dossier ou une image .bin."""

    def __init__(self, chemin):
        self.chemin = chemin
        self.index = None
        if chemin.lower().endswith('.bin'):
            self.f = open(chemin, 'rb')
            self.index = {nom.upper(): (lba, taille) for nom, lba, taille in self._lister()}

    def _secteurs(self, lba, n):
        out = bytearray()
        for i in range(n):
            self.f.seek((lba + i) * SECT + OFF)
            out += self.f.read(2048)
        return bytes(out)

    def _lister(self):
        pvd = self._secteurs(16, 1)
        if pvd[1:6] != b'CD001':
            raise ValueError("ce fichier .bin n'est pas l'image CD attendue")
        res = []

        def parcourir(rec, prefixe):
            lba, taille = struct.unpack('<I', rec[2:6])[0], struct.unpack('<I', rec[10:14])[0]
            data, p = self._secteurs(lba, (taille + 2047) // 2048), 0
            while p < len(data):
                l = data[p]
                if l == 0:
                    p = (p // 2048 + 1) * 2048
                    continue
                r = data[p:p + l]
                nom = r[33:33 + r[32]]
                if nom not in (b'\x00', b'\x01'):
                    n = nom.decode('latin1').split(';')[0]
                    if r[25] & 2:
                        parcourir(r, prefixe + n + '/')
                    else:
                        res.append((prefixe + n, struct.unpack('<I', r[2:6])[0], struct.unpack('<I', r[10:14])[0]))
                p += l

        parcourir(pvd[156:190], '')
        return res

    def lire(self, nom):
        if self.index is not None:
            lba, taille = self.index[nom.upper()]
            return self._secteurs(lba, (taille + 2047) // 2048)[:taille]
        # dossier : recherche insensible à la casse (fichiers en majuscules sur le CD)
        chemin = self.chemin
        for morceau in nom.split('/'):
            noms = {n.upper(): n for n in os.listdir(chemin)}
            chemin = os.path.join(chemin, noms[morceau.upper()])
        with open(chemin, 'rb') as f:
            return f.read()


def lire_pcx(d):
    """PCX 8 bits RLE -> (largeur, hauteur, pixels bytes, palette 768 octets)."""
    x0, y0, x1, y1 = struct.unpack('<HHHH', d[4:12])
    bpl = struct.unpack('<H', d[66:68])[0]
    w, h = x1 - x0 + 1, y1 - y0 + 1
    i, out, besoin = 128, bytearray(), bpl * d[65] * h
    while len(out) < besoin:
        b = d[i]; i += 1
        if b >= 0xC0:
            out += bytes([d[i]]) * (b & 0x3F); i += 1
        else:
            out.append(b)
    if bpl != w:
        out = b''.join(out[y * bpl:y * bpl + w] for y in range(h))
    return w, h, bytes(out), d[-768:]


COTE, COTE_G = 128, 256


def _transposer(v, cote):
    """Le fichier range les cases colonne par colonne (indice = x*cote + y) ; on rend des lignes (y*cote + x)."""
    return [v[x * cote + y] for y in range(cote) for x in range(cote)]


def lire_carte(d):
    """Carte .MAP -> (couches de tuiles 128x128, grilles de drapeaux 256x256), indexées [y * cote + x].

    Dans le fichier, comme dans DRACULA.EXE, les grilles sont rangées par colonnes (x * cote + y).
    """
    v = struct.unpack('<%dI' % (len(d) // 4), d)
    n = len(v) // (COTE * COTE + COTE_G * COTE_G)
    couches = [_transposer([x & 0xFFFF for x in v[i * COTE * COTE:(i + 1) * COTE * COTE]], COTE) for i in range(n)]
    base = n * COTE * COTE
    grilles = [_transposer(v[base + i * COTE_G * COTE_G: base + (i + 1) * COTE_G * COTE_G], COTE_G) for i in range(n)]
    return couches, grilles


COMTES = ['BRAILA', 'BRASOV', 'CUERTA', 'FAGARAS', 'GIURGIU', 'HIRSOVA', 'OSTROV',
          'PITESTI', 'RASOVA', 'SIBIU', 'SNAGOV', 'TIRGO']


def pistes_cd(chemin_bin):
    """Pistes audio du CD d'après le .cue voisin : {numéro: (octet_début, octet_fin)} dans le .bin."""
    cue = os.path.splitext(chemin_bin)[0] + '.cue'
    if not os.path.exists(cue):
        return {}
    debuts, piste, audio = {}, None, set()
    for ligne in open(cue, encoding='latin1'):
        mots = ligne.split()
        if mots[:1] == ['TRACK']:
            piste = int(mots[1])
            if mots[2] == 'AUDIO':
                audio.add(piste)
        elif mots[:2] == ['INDEX', '01'] and piste:
            m, s, f = (int(x) for x in mots[2].split(':'))
            debuts[piste] = ((m * 60 + s) * 75 + f) * SECT
    taille = os.path.getsize(chemin_bin)
    ordre = sorted(debuts)
    res = {}
    for i, p in enumerate(ordre):
        fin = debuts[ordre[i + 1]] if i + 1 < len(ordre) else taille
        if p in audio:
            res[p] = (debuts[p], fin)
    return res
