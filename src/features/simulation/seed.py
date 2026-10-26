"""Conditions de départ de la simulation.

Les effectifs respectent les proportions des sources antiques (souvent gonflées) ; l'or est une valeur
d'équilibrage, pas un chiffre historique. Les généraux viennent d'époques différentes (de Tian Dan à
Wang Jian) : c'est un "et si" assumé. Han et Yan n'ont pas de général : ils se battent avec une
compétence par défaut.
"""

# (id, nom, troupes, moral, or)
KINGDOMS = [
    ("qin", "Qin", 600_000, 90, 3_000_000),
    ("chu", "Chu", 500_000, 80, 2_000_000),
    ("qi", "Qi", 300_000, 70, 2_200_000),
    ("zhao", "Zhao", 400_000, 85, 1_500_000),
    ("wei", "Wei", 250_000, 75, 1_400_000),
    ("han", "Han", 100_000, 60, 500_000),
    ("yan", "Yan", 150_000, 65, 700_000),
]

# (nom, id du royaume, compétence tactique, statut)
GENERALS = [
    ("Wang Jian", "qin", 95, "active"),
    ("Meng Wu", "qin", 80, "active"),
    ("Li Xin", "qin", 78, "active"),
    ("Li Mu", "zhao", 92, "active"),
    ("Lian Po", "zhao", 90, "exiled"),
    ("Zhao Kuo", "zhao", 40, "active"),
    ("Xiang Yan", "chu", 88, "active"),
    ("Pang Juan", "wei", 85, "active"),
    ("Wei Wuji", "wei", 85, "active"),
    ("Tian Dan", "qi", 88, "active"),
]
