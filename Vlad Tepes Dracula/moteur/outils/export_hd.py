"""Exporte les graphismes de BATTLE.ART en PNG prêts à être agrandis par une IA (Real-ESRGAN, chaiNNer...).

Usage : python outils/export_hd.py <Dracula.bin ou extrait/donnees> [dossier de sortie]
Sortie par défaut : moteur/extrait/hd_source/
  tuiles.png   16 colonnes de cases de 56x56 px : chaque tuile 40x40 entourée d'une marge de 8 px
               (bords reflétés), pour que l'IA ne crée pas de coutures entre les tuiles.
  sprites.png  les unités et effets, avec un vrai canal alpha (le cyan transparent est retiré).
Agrandis les deux fichiers avec le même modèle (x2 ou x4), garde les mêmes noms, et range-les dans
moteur/extrait/hd/ : le moteur les détecte, recoupe les marges et active le mode « pack HD » (touche L).
Ces images restent dérivées du jeu original : usage personnel uniquement, ne pas les distribuer.
"""
import os, sys
import numpy as np
from PIL import Image

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ICI))
from vlad import donnees  # noqa: E402

TUILE, MARGE, Y_SPRITES, TRANSPARENT = 40, 8, 3708, 218


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    sortie = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(ICI), 'extrait', 'hd_source')
    os.makedirs(sortie, exist_ok=True)
    w, h, px, pal = donnees.lire_pcx(donnees.Source(sys.argv[1]).lire('ART/BATTLE.ART'))
    idx = np.frombuffer(bytes(px), np.uint8).reshape(h, w)
    rgb = np.frombuffer(bytes(pal[:768]), np.uint8).reshape(256, 3)[idx]

    lignes = (Y_SPRITES + TUILE - 1) // TUILE
    zone = np.zeros((lignes * TUILE, w, 3), np.uint8)
    zone[:min(h, lignes * TUILE)] = rgb[:lignes * TUILE]
    C = TUILE + 2 * MARGE
    grille = np.zeros((lignes * C, 16 * C, 3), np.uint8)
    for i in range(16 * lignes):
        x, y = (i % 16) * TUILE, (i // 16) * TUILE
        t = np.pad(zone[y:y + TUILE, x:x + TUILE], ((MARGE, MARGE), (MARGE, MARGE), (0, 0)), mode='reflect')
        grille[(i // 16) * C:(i // 16 + 1) * C, (i % 16) * C:(i % 16 + 1) * C] = t
    Image.fromarray(grille).save(os.path.join(sortie, 'tuiles.png'))

    alpha = np.where(idx[Y_SPRITES:] == TRANSPARENT, 0, 255).astype(np.uint8)
    rgba = np.dstack([rgb[Y_SPRITES:], alpha])
    rgba[alpha == 0, :3] = 0
    Image.fromarray(rgba, 'RGBA').save(os.path.join(sortie, 'sprites.png'))
    print('écrit dans', sortie, ': tuiles.png', grille.shape[1::-1], ', sprites.png', rgba.shape[1::-1])
    return 0


if __name__ == '__main__':
    sys.exit(main())
