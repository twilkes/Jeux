"""Reconstitue une carte .MAP en image PNG à partir des tuiles de BATTLE.ART.

Usage : python carte.py <dossier extrait> <NOM.MAP> [--masque]

Format (voir docs/formats.md), entiers 32 bits little-endian :
  - N couches de 128x128 numéros de tuiles 40x40 px (BATTLE.ART, 16 tuiles par ligne, index 218 = transparent)
  - grilles rangées par colonnes : indice = x * cote + y (vérifié dans DRACULA.EXE)
  - N grilles 256x256 de drapeaux (bits 16+), une case = 20x20 px
  Comtés : N = 1.  BUILDING.MAP : N = 3 (sol, murs/bâtiments, toits).
"""
import os, struct, sys
from PIL import Image

TUILE, PAR_LIGNE, COTE, COTE_G, TRANSPARENT = 40, 16, 128, 256, 218
COULEURS = {0x4: (255, 0, 0), 0x8: (255, 128, 0), 0xC: (255, 255, 0), 0x10: (0, 255, 0),
            0x20: (0, 255, 255), 0x40: (0, 0, 255), 0x80: (255, 0, 255), 0x100: (255, 255, 255)}


def lire_carte(chemin):
    d = open(chemin, 'rb').read()
    v = struct.unpack('<%dI' % (len(d) // 4), d)
    n = len(v) // (COTE * COTE + COTE_G * COTE_G)
    couches = [v[i * COTE * COTE:(i + 1) * COTE * COTE] for i in range(n)]
    base = n * COTE * COTE
    grilles = [v[base + i * COTE_G * COTE_G: base + (i + 1) * COTE_G * COTE_G] for i in range(n)]
    return couches, grilles


def charger_atlas(chemin):
    a = Image.open(chemin)
    rgba = a.convert('RGBA')
    rgba.putalpha(Image.frombytes('L', a.size, bytes(0 if b == TRANSPARENT else 255 for b in a.tobytes())))
    return rgba


def dessiner(couches, atlas):
    im = Image.new('RGBA', (COTE * TUILE, COTE * TUILE), (0, 0, 0, 255))
    cache = {}
    for couche in couches:
        for i, val in enumerate(couche):
            t = val & 0xFFFF
            if not t and couche is not couches[0]:
                continue
            if t not in cache:
                sx, sy = (t % PAR_LIGNE) * TUILE, (t // PAR_LIGNE) * TUILE
                cache[t] = atlas.crop((sx, sy, sx + TUILE, sy + TUILE))
            im.alpha_composite(cache[t], ((i // COTE) * TUILE, (i % COTE) * TUILE))
    return im.convert('RGB')


def dessiner_grille(grille):
    im = Image.new('RGB', (COTE_G, COTE_G))
    p = im.load()
    for i, val in enumerate(grille):
        if val >> 16:
            p[i // COTE_G, i % COTE_G] = COULEURS.get(val >> 16, (128, 128, 128))
    return im


def main():
    racine, nom = sys.argv[1], sys.argv[2]
    atlas = charger_atlas(os.path.join(racine, 'png', 'BATTLE.ART.png'))
    couches, grilles = lire_carte(os.path.join(racine, 'donnees', 'COUNTIES', nom))
    os.makedirs(os.path.join(racine, 'cartes'), exist_ok=True)
    base = os.path.join(racine, 'cartes', os.path.splitext(nom)[0])
    im = dessiner(couches, atlas)
    im.save(base + '.png')
    print(base + '.png', im.size, len(couches), 'couche(s)')
    if '--masque' in sys.argv:
        for i, g in enumerate(grilles):
            gi = dessiner_grille(g).resize(im.size, Image.NEAREST)
            Image.blend(im, gi, 0.45).save('%s_grille%d.png' % (base, i))


if __name__ == '__main__':
    main()
