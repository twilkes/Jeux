"""Filtres d'agrandissement du pixel art (aucune donnée du jeu ici : ce sont des algorithmes publics).

xbr2 : agrandissement x2 à détection de contours, d'après l'algorithme xBR de Hyllian (niveau 1).
Pour chaque coin de chaque pixel, on compare deux diagonales (somme des différences de couleur le long
de chacune) : si un contour passe en biais, le coin prend la couleur du voisin situé de l'autre côté du
contour, à demi mélangée. Appliqué deux fois (x4), les escaliers deviennent des courbes lisses.
La transparence (couche alpha) est traitée comme une couleur : les bords des sprites deviennent
semi-transparents au lieu d'être en escalier.

reduire2 : moyenne 2x2 en alpha prémultiplié (sur-échantillonnage x4 -> x2, sans liseré sombre).
contraste : renforcement doux des contours (masque flou), pour garder du piqué après lissage.
cubique : bicubique (Catmull-Rom) pour les tuiles de terrain, dont la texture bruitée n'a pas de contours nets.
"""
import numpy as np
import pygame

# poids YUV (comme xBR) : la luminance compte bien plus que la teinte ; l'alpha compte comme un contour franc
_POIDS = np.array([[0.299, 0.587, 0.114], [-0.169, -0.331, 0.5], [0.5, -0.419, -0.081]], np.float32)


def vers_tableau(surface):
    """Surface pygame -> tableau (h, w, 4) float32 en alpha prémultiplié, valeurs 0..1."""
    rgb = pygame.surfarray.pixels3d(surface).transpose(1, 0, 2).astype(np.float32) / 255
    if surface.get_flags() & pygame.SRCALPHA:
        a = pygame.surfarray.pixels_alpha(surface).T.astype(np.float32) / 255
    else:
        a = np.ones(rgb.shape[:2], np.float32)
        cle = surface.get_colorkey()
        if cle is not None:
            c = np.array(cle[:3], np.float32) / 255
            a[np.all(np.abs(rgb - c) < 1 / 512, axis=2)] = 0
    return np.dstack([rgb * a[..., None], a])


def vers_surface(t):
    """Tableau prémultiplié (h, w, 4) -> Surface SRCALPHA."""
    a = t[..., 3:4]
    rgb = np.where(a > 1e-4, t[..., :3] / np.maximum(a, 1e-4), 0)
    h, w = t.shape[:2]
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(s)[...] = np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8).transpose(1, 0, 2)
    pygame.surfarray.pixels_alpha(s)[...] = np.clip(a[..., 0] * 255 + 0.5, 0, 255).astype(np.uint8).T
    return s


def _yuva(t):
    a = t[..., 3]
    rgb = t[..., :3] / np.maximum(a, 1e-4)[..., None]
    y = rgb @ _POIDS.T
    return np.dstack([y * np.array([48, 7, 6], np.float32) * a[..., None], a * 40])


def _coin(t, q):
    """Coin bas-droit de chaque pixel (2xBR niveau 1). t et q sont bordés de 2 pixels."""
    h, w = t.shape[0] - 4, t.shape[1] - 4

    def v(dx, dy, src):
        return src[2 + dy:2 + dy + h, 2 + dx:2 + dx + w]

    def d(a, b):
        return np.abs(a - b).sum(axis=2)

    E, B, C, D, F, G, H, I = (v(0, 0, q), v(0, -1, q), v(1, -1, q), v(-1, 0, q), v(1, 0, q),
                              v(-1, 1, q), v(0, 1, q), v(1, 1, q))
    F4, H5, I4, I5 = v(2, 0, q), v(0, 2, q), v(2, 1, q), v(1, 2, q)
    e = d(E, C) + d(E, G) + d(I, F4) + d(I, H5) + 4 * d(H, F)
    i = d(H, D) + d(H, I5) + d(F, I4) + d(F, B) + 4 * d(E, I)
    seuil = 1.0  # différences minimes (dégradés) ignorées
    contour = (e + seuil < i) & (d(E, F) > seuil) & (d(E, H) > seuil)
    choix = (d(E, F) <= d(E, H))[..., None]
    px = np.where(choix, v(1, 0, t), v(0, 1, t))
    Et = v(0, 0, t)
    return np.where(contour[..., None], (Et + px) * 0.5, Et)


def xbr2(t):
    """Agrandit x2 un tableau prémultiplié (h, w, 4)."""
    p = np.pad(t, ((2, 2), (2, 2), (0, 0)), mode='edge')
    q = _yuva(p)
    h, w = t.shape[:2]
    res = np.empty((2 * h, 2 * w, 4), np.float32)
    # les quatre coins : on tourne l'image, on calcule le coin bas-droit, on la remet droite
    for k, (oy, ox) in enumerate(((1, 1), (1, 0), (0, 0), (0, 1))):
        c = np.rot90(_coin(np.rot90(p, k), np.rot90(q, k)), -k)
        res[oy::2, ox::2] = c
    return res


def reduire2(t):
    h, w = t.shape[0] // 2 * 2, t.shape[1] // 2 * 2
    t = t[:h, :w]
    return (t[0::2, 0::2] + t[1::2, 0::2] + t[0::2, 1::2] + t[1::2, 1::2]) * 0.25


def contraste(t, force=0.35):
    """Masque flou : renforce un peu les contours après le lissage (force 0 = rien)."""
    if force <= 0:
        return t
    p = np.pad(t, ((1, 1), (1, 1), (0, 0)), mode='edge')
    flou = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] + 4 * p[1:-1, 1:-1]) / 8
    r = t + force * (t - flou)
    a = np.clip(r[..., 3:4], 0, 1)
    return np.dstack([np.clip(r[..., :3], 0, a), a])


def cubique(t, f):
    """Agrandissement bicubique (Catmull-Rom, séparable) x f : doux et sans escaliers, idéal pour les textures
    bruitées (herbe, rochers) où xBR ne trouve pas de vrais contours."""
    def axe(a, ax):
        n = a.shape[ax]
        pos = (np.arange(n * f) + 0.5) / f - 0.5
        i = np.floor(pos).astype(int)
        x = (pos - i).astype(np.float32)
        x = x[:, None, None] if ax == 0 else x[None, :, None]
        p0, p1, p2, p3 = (np.take(a, np.clip(i + k, 0, n - 1), axis=ax) for k in (-1, 0, 1, 2))
        return 0.5 * (2 * p1 + (p2 - p0) * x + (2 * p0 - 5 * p1 + 4 * p2 - p3) * x * x + (3 * p1 - p0 - 3 * p2 + p3) * x * x * x)
    r = axe(axe(t, 0), 1)
    a = np.clip(r[..., 3:4], 0, 1)
    return np.dstack([np.clip(r[..., :3], 0, a), a]).astype(np.float32)


def agrandir(surface, facteur, marge=0, net=0.35, methode='xbr'):
    """Agrandit une surface x2 ou x4 (xBR, puis sur-échantillonnage pour x2). marge = pixels de bord à rogner
    (déjà inclus dans la surface, pour que le filtre voie les voisins) ; le résultat est rogné à la taille utile."""
    t = vers_tableau(surface)
    t = xbr2(xbr2(t)) if methode == 'xbr' else cubique(t, 4)  # x4
    if facteur == 2:
        t = reduire2(t)
    t = contraste(t, net)
    if marge:
        m = marge * facteur
        t = t[m:-m, m:-m]
    return vers_surface(np.ascontiguousarray(t))
