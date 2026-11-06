-- Base actuelle du portail sinistres (extrait)
CREATE TABLE IF NOT EXISTS public.assure (
  id UUID PRIMARY KEY,
  nom VARCHAR(120) NOT NULL,
  prenom VARCHAR(120),
  email VARCHAR(255) NOT NULL UNIQUE,
  date_naissance DATE
);

CREATE TABLE public.contrat (
  id BIGSERIAL,
  numero VARCHAR(30) NOT NULL,
  assure_id UUID NOT NULL REFERENCES public.assure(id),
  souscrit_le TIMESTAMP WITH TIME ZONE,
  CONSTRAINT pk_contrat PRIMARY KEY (id),
  CONSTRAINT uq_numero UNIQUE (numero)
);

/* Garanties du catalogue */
CREATE TABLE garantie (
  code VARCHAR(10) PRIMARY KEY,
  libelle TEXT,
  plafond NUMERIC(12,2)
);

CREATE TABLE contrat_garantie (
  contrat_id BIGINT REFERENCES contrat(id),
  garantie_code VARCHAR(10),
  PRIMARY KEY (contrat_id, garantie_code),
  FOREIGN KEY (garantie_code) REFERENCES garantie(code)
);

CREATE TABLE "Sinistre" (
  "Id" UUID PRIMARY KEY,
  "ContratId" BIGINT NOT NULL,
  blessures TEXT,
  geom GEOGRAPHY,
  agence_id INTEGER REFERENCES agence(id),
  FOREIGN KEY ("ContratId") REFERENCES contrat (id)
);

CREATE TABLE journal (
  horodatage TIMESTAMP,
  message TEXT
);
