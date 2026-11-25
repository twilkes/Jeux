"""Extrait les fichiers de jeu de l'image CD Dracula.bin et convertit les .ART en PNG.

Usage : python extraire.py <Dracula.bin> <dossier_sortie>
Ne modifie jamais l'image d'origine.
"""
import json, os, struct, sys, zlib

SECT, OFF = 2352, 16  # piste MODE1/2352 : 16 octets d'en-tête puis 2048 octets de données


class ImageCD:
    def __init__(self, chemin):
        self.f = open(chemin, 'rb')

    def secteurs(self, lba, n=1):
        out = bytearray()
        for i in range(n):
            self.f.seek((lba + i) * SECT + OFF)
            out += self.f.read(2048)
        return bytes(out)

    def fichiers(self):
        pvd = self.secteurs(16)
        assert pvd[1:6] == b'CD001', 'pas une piste ISO9660'
        res = []
        def parcourir(rec, chemin):
            lba, taille = struct.unpack('<I', rec[2:6])[0], struct.unpack('<I', rec[10:14])[0]
            data, p = self.secteurs(lba, (taille + 2047) // 2048), 0
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
                        parcourir(r, chemin + n + '/')
                    else:
                        res.append((chemin + n, struct.unpack('<I', r[2:6])[0], struct.unpack('<I', r[10:14])[0]))
                p += l
        parcourir(pvd[156:190], '')
        return res

    def lire(self, lba, taille):
        return self.secteurs(lba, (taille + 2047) // 2048)[:taille]


def pcx_vers_indices(d):
    """Décode un PCX 8 bits RLE. Renvoie (largeur, hauteur, pixels, palette RGB 768 octets)."""
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
    assert d[-769] == 0x0C, 'palette absente'
    pixels = b''.join(out[y * bpl:y * bpl + w] for y in range(h))
    return w, h, pixels, d[-768:]


def ecrire_png(chemin, w, h, pixels, palette):
    def bloc(t, data):
        c = t + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c))
    brut = b''.join(b'\0' + pixels[y * w:(y + 1) * w] for y in range(h))
    with open(chemin, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + bloc(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 3, 0, 0, 0))
                + bloc(b'PLTE', palette) + bloc(b'IDAT', zlib.compress(brut, 6)) + bloc(b'IEND', b''))


def main():
    image, sortie = sys.argv[1], sys.argv[2]
    cd = ImageCD(image)
    liste = [f for f in cd.fichiers() if not f[0].startswith('DIRECTX/')]
    for chemin, lba, taille in liste:
        dest = os.path.join(sortie, 'donnees', chemin)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'wb') as f:
            f.write(cd.lire(lba, taille))
        if chemin.upper().endswith('.ART'):
            w, h, px, pal = pcx_vers_indices(cd.lire(lba, taille))
            os.makedirs(os.path.join(sortie, 'png'), exist_ok=True)
            ecrire_png(os.path.join(sortie, 'png', os.path.basename(chemin) + '.png'), w, h, px, pal)
            print(f'{chemin}: {w}x{h}')
    with open(os.path.join(sortie, 'fichiers.json'), 'w') as f:
        json.dump(liste, f, indent=1)
    print(len(liste), 'fichiers extraits dans', sortie)


if __name__ == '__main__':
    main()
