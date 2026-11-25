"""Exporte les animations des unités de BATTLE.ART à partir des tables extraites de DRACULA.EXE.

Usage : python unites.py <dossier extrait>
Écrit extrait/unites/t<type>_a<anim>_c<camp>.png : 8 lignes (directions) x N colonnes (images).
Les entrées qui sortent de la planche (ex. type 4, camp 1) sont signalées et ignorées.
"""
import json, os, sys
from PIL import Image

ICI = os.path.dirname(os.path.abspath(__file__))


def entrees(t):
    for ty, S in enumerate(t['taille']):
        if not S:
            continue
        for an in range(3):
            nf = t['nb_images'][3 * ty + an]
            for camp in range(3):
                i = (3 * ty + an) * 3 + camp
                x, y = t['x'][i], t['y'][i]
                if nf and (x or y):
                    yield ty, an, camp, x, y, S, nf


def main():
    racine = sys.argv[1]
    t = json.load(open(os.path.join(ICI, 'tables_unites.json'), encoding='utf-8'))
    atlas = Image.open(os.path.join(racine, 'png', 'BATTLE.ART.png'))
    sortie = os.path.join(racine, 'unites')
    os.makedirs(sortie, exist_ok=True)
    for ty, an, camp, x, y, S, nf in entrees(t):
        if y + 8 * S > atlas.height or x + nf * S > atlas.width:
            print(f'type {ty} anim {an} camp {camp} : hors planche ({x},{y}), ignoré')
            continue
        bloc = atlas.crop((x, y, x + nf * S, y + 8 * S))
        bloc.save(os.path.join(sortie, f't{ty}_a{an}_c{camp}.png'))
    print('fini ->', sortie)


if __name__ == '__main__':
    main()
