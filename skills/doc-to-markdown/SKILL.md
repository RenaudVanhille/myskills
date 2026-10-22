---
name: doc-to-markdown
description: Convertit un document PDF, DOCX, PPTX, XLSX ou une image en Markdown propre, en local. À utiliser pour extraire le contenu d'un document vers du Markdown.
---

# doc-to-markdown

> Statut : squelette. Contenu à écrire à l'étape 3.

## Ce que fera ce skill

1. Détecter le type de fichier (Office, PDF natif, PDF scanné, image).
2. Choisir l'outil : MarkItDown pour Office et PDF simples, Docling pour PDF scannés ou riches en tableaux, vision de l'agent pour les images.
3. Extraire les images dans un dossier `attachments/` et les lier.
4. Produire un rapport des éléments non convertis.
