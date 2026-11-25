"""Repère automatiquement les sprites (zones non transparentes) d'une planche .ART.

Usage : python sprites.py <dossier extrait> <NOM.ART.png> <y_debut> [y_fin]
Écrit extrait/sprites/<NOM>.json : liste de rectangles {x, y, w, h}, triés par ligne puis colonne.
Les pixels d'index 218 (cyan) sont transparents. Les composantes très proches (2 px) sont fusionnées.
"""
import json, os, sys
from PIL import Image

TRANSPARENT, MARGE = 218, 2


def composantes(d, W, y0, y1):
    vu = bytearray(W * (y1 - y0))
    boites = []
    for y in range(y0, y1):
        for x in range(W):
            i = (y - y0) * W + x
            if vu[i] or d[y * W + x] == TRANSPARENT:
                continue
            pile = [(x, y)]; vu[i] = 1
            bx0 = bx1 = x; by0 = by1 = y
            while pile:
                cx, cy = pile.pop()
                bx0, bx1, by0, by1 = min(bx0, cx), max(bx1, cx), min(by0, cy), max(by1, cy)
                for nx in range(max(cx - MARGE, 0), min(cx + MARGE + 1, W)):
                    for ny in range(max(cy - MARGE, y0), min(cy + MARGE + 1, y1)):
                        j = (ny - y0) * W + nx
                        if not vu[j] and d[ny * W + nx] != TRANSPARENT:
                            vu[j] = 1; pile.append((nx, ny))
            boites.append([bx0, by0, bx1 + 1, by1 + 1])
    return boites


def main():
    racine, nom, y0 = sys.argv[1], sys.argv[2], int(sys.argv[3])
    a = Image.open(os.path.join(racine, 'png', nom))
    W, H = a.size
    y1 = int(sys.argv[4]) if len(sys.argv) > 4 else H
    boites = composantes(a.tobytes(), W, y0, y1)
    boites = [b for b in boites if (b[2] - b[0]) * (b[3] - b[1]) >= 16]  # ignore les poussières
    boites.sort(key=lambda b: (b[1] // 8, b[0]))
    os.makedirs(os.path.join(racine, 'sprites'), exist_ok=True)
    sortie = os.path.join(racine, 'sprites', nom.split('.')[0] + '.json')
    json.dump([dict(x=b[0], y=b[1], w=b[2] - b[0], h=b[3] - b[1]) for b in boites], open(sortie, 'w'), indent=0)
    print(len(boites), 'sprites ->', sortie)


if __name__ == '__main__':
    main()
