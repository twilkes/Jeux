"""Sons d'origine (.WG = WAV) et musique CD (pistes audio de Dracula.bin)."""
import io, os, random, struct, tempfile
import pygame
from . import donnees


class Sons:
    def __init__(self, source):
        self.source = source
        self.actif = True
        self.cache = {}
        try:
            pygame.mixer.init(44100, -16, 2, 1024)
            pygame.mixer.set_num_channels(24)
        except pygame.error:
            self.actif = False
        self.pistes = donnees.pistes_cd(source.chemin) if source.chemin.lower().endswith('.bin') else {}
        self.piste = None

    def son(self, nom):
        """nom = 'Battle_05' ou 'Council_12'."""
        if not self.actif:
            return None
        if nom not in self.cache:
            dossier, num = nom.split('_')
            try:
                data = self.source.lire('AUDIO/%s/%s.WG' % (dossier.upper(), num))
                self.cache[nom] = pygame.mixer.Sound(file=io.BytesIO(data))
            except (KeyError, FileNotFoundError, pygame.error):
                self.cache[nom] = None
        return self.cache[nom]

    def jouer(self, nom, volume=1.0):
        s = self.son(nom)
        if s:
            s.set_volume(volume)
            s.play()

    def musique(self, piste=None):
        """Joue une piste audio du CD (2 à 8). Écrit un WAV temporaire, la lecture se fait en flux."""
        if not (self.actif and self.pistes):
            return False
        if piste is None:
            choix = [p for p in self.pistes if p != self.piste]
            piste = random.choice(choix)
        debut, fin = self.pistes[piste]
        chemin = os.path.join(tempfile.gettempdir(), 'vlad_piste%02d.wav' % piste)
        if not os.path.exists(chemin) or os.path.getsize(chemin) != fin - debut + 44:
            with open(self.source.chemin, 'rb') as f, open(chemin, 'wb') as w:
                n = fin - debut
                w.write(b'RIFF' + struct.pack('<I', 36 + n) + b'WAVEfmt ' +
                        struct.pack('<IHHIIHH', 16, 1, 2, 44100, 44100 * 4, 4, 16) + b'data' + struct.pack('<I', n))
                f.seek(debut)
                while n > 0:
                    bloc = f.read(min(n, 1 << 20))
                    w.write(bloc)
                    n -= len(bloc)
        pygame.mixer.music.load(chemin)
        pygame.mixer.music.set_volume(0.6)
        pygame.mixer.music.play()
        self.piste = piste
        return True
