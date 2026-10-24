from src.api.declarations import statut


def publier(message):
    return statut(len(message))
