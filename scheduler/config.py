"""Authoritative configuration extracted from Untitled6.ipynb."""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
REGISTRY_FILE = DATA_DIR / "assignment_registry.json"

DEFAULT_EXTERNAL_EMPLOYEES_FILE = Path(r"C:\Users\amine\medimar\employees.csv")

AVAILABILITY_API_URL = (
    "https://tools.triweb-apps.com/Triweb_NewV/intern/api/VPlanificationV/"
    "GetVwCollaboratorDailyAvailability"
)
PROJECTS_API_URL = "https://tools.triweb-apps.com/Triweb_NewV/intern/api/VPlanificationV"

MAX_WEEKLY_HOURS = 38.0
POST_TASK_BREAK_MINUTES = 20
MAX_RECEPTION_AGE_DAYS = 15
WORKING_PERIODS = ((8, 30, 12, 30), (13, 30, 17, 0))
STAGE_EFFORT_SPLIT = {"Redaction": 0.45, "Graphe": 0.55}
SCHEDULABLE_DEPARTMENTS = {"Redaction", "Graphe"}

# Exact final notebook mapping; keys are normalized at lookup time.
NATURE_WORKFLOW: dict[str, tuple[str, ...] | None] = {
    "Rédactionnel / création site Webtool": ("Redaction", "Graphe"),
    "Rédactionnel / création site ecommerce": ("Redaction", "Graphe"),
    "Rédactionnel / création site Toolbox": ("Redaction", "Graphe"),
    "Corrections MAJ refonte": ("Redaction", "Graphe"),
    "Corrections CREA refonte": ("Redaction", "Graphe"),
    "Corrections CREA/minimes (-30 min)": ("Redaction", "Graphe"),
    "Corrections CREA/minimes (-15 min)": ("Redaction", "Graphe"),
    "Corrections CREA/importantes (1h )": ("Redaction", "Graphe"),
    "Corrections CREA/importantes (1h30 )": ("Redaction", "Graphe"),
    "Corrections CREA/importantes (2H )": ("Redaction", "Graphe"),
    "Corrections CREA/importantes (2H30 )": ("Redaction", "Graphe"),
    "Corrections CREA/importantes (3H )": ("Redaction", "Graphe"),
    "Corrections CREA/importantes (> 3H )": ("Redaction", "Graphe"),
    "Corrections MAJ/minimes (-30 min)": ("Redaction", "Graphe"),
    "Corrections MAJ/minimes (-15 min)": ("Redaction", "Graphe"),
    "Corrections MAJ/importantes (1h )": ("Redaction", "Graphe"),
    "Corrections MAJ/importantes (1h30 )": ("Redaction", "Graphe"),
    "Corrections MAJ/importantes (2H )": ("Redaction", "Graphe"),
    "Corrections MAJ/importantes (2H30 )": ("Redaction", "Graphe"),
    "Corrections MAJ/importantes (3H )": ("Redaction", "Graphe"),
    "Corrections MAJ/importantes (> 3H )": ("Redaction", "Graphe"),
    "Création de page (2H)": ("Redaction", "Graphe"),
    "Création de page (3H)": ("Redaction", "Graphe"),
    "Création de page (4H)": ("Redaction", "Graphe"),
    "Création de page (5H)": ("Redaction", "Graphe"),
    "Création de page (7H)": ("Redaction", "Graphe"),
    "Création campagne": ("Redaction",),
    "Référencement/SEO (30 min)": ("Redaction",),
    "Référencement/SEO (1h30)": ("Redaction",),
    "Création du logo": ("Graphe",),
    "Logo": ("Graphe",),
    "Maquette": ("Graphe",),
    "Corrections MAJ refonte sans rédaction": ("Graphe",),
    "Corrections MAJ/importantes (2H)": ("Graphe",),
    "Corrections MAJ/importantes (2H30 )": ("Graphe",),
    "SAV": None,
    "Création campagne sur mesure": None,
}

NATURE_DURATION_HOURS = {
    "Rédactionnel / création site Webtool": 8.0,
    "Rédactionnel / création site ecommerce": 10.0,
    "Rédactionnel / création site Toolbox": 8.0,
    "Création de page (2H)": 2.0,
    "Création de page (3H)": 3.0,
    "Création de page (4H)": 4.0,
    "Création de page (5H)": 5.0,
    "Création de page (7H)": 7.0,
    "Création du logo": 3.0,
    "Logo": 3.0,
    "Maquette": 6.0,
    "Corrections CREA/minimes (-30 min)": 0.5,
    "Corrections CREA/minimes (-15 min)": 0.25,
    "Corrections CREA/importantes (1h )": 1.0,
    "Corrections CREA/importantes (1h30 )": 1.5,
    "Corrections CREA/importantes (2H )": 2.0,
    "Corrections CREA/importantes (2H30 )": 2.5,
    "Corrections CREA/importantes (3H )": 3.0,
    "Corrections CREA/importantes (> 3H )": 4.0,
    "Corrections CREA refonte": 4.0,
    "Corrections MAJ/minimes (-30 min)": 0.5,
    "Corrections MAJ/minimes (-15 min)": 0.25,
    "Corrections MAJ/importantes (1h )": 1.0,
    "Corrections MAJ/importantes (1h30 )": 1.5,
    "Corrections MAJ/importantes (2H )": 2.0,
    "Corrections MAJ/importantes (2H30 )": 2.5,
    "Corrections MAJ/importantes (3H )": 3.0,
    "Corrections MAJ/importantes (> 3H )": 4.0,
    "Corrections MAJ refonte": 4.0,
    "Corrections MAJ refonte sans rédaction": 4.0,
    "Référencement/SEO (30 min)": 0.5,
    "Référencement/SEO (1h30)": 1.5,
    "Création campagne": 1.0,
}


def employees_file() -> Path:
    """Use an explicit setting, the supplied source file, then repo fallback."""
    configured = os.getenv("TRIWEB_EMPLOYEES_CSV")
    if configured:
        return Path(configured)
    if DEFAULT_EXTERNAL_EMPLOYEES_FILE.exists():
        return DEFAULT_EXTERNAL_EMPLOYEES_FILE
    return DATA_DIR / "employees.csv"


def verify_tls() -> bool:
    """The reference notebook used disabled TLS verification for this legacy API."""
    return os.getenv("TRIWEB_VERIFY_TLS", "false").casefold() in {"1", "true", "yes"}
