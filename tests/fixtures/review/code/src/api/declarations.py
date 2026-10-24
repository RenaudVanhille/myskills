from src.messagerie.file import publier
from src.outils.texte import nettoyer


def declarer(donnees):
    return publier(nettoyer(donnees))


def statut(numero):
    return {"numero": numero}
