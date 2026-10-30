"""Starting conditions of the simulation.

Troop numbers follow the proportions of the ancient sources (often inflated); gold is a balancing
value, not a historical figure. Generals come from different eras (from Tian Dan to Wang Jian):
an assumed "what if". Han and Yan have no general: they fight with a default skill.
"""

# (id, name, troops, morale, gold)
KINGDOMS = [
    ("qin", "Qin", 600_000, 90, 3_000_000),
    ("chu", "Chu", 500_000, 80, 2_000_000),
    ("qi", "Qi", 300_000, 70, 2_200_000),
    ("zhao", "Zhao", 400_000, 85, 1_500_000),
    ("wei", "Wei", 250_000, 75, 1_400_000),
    ("han", "Han", 100_000, 60, 500_000),
    ("yan", "Yan", 150_000, 65, 700_000),
]

# (name, kingdom id, tactical skill, status)
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
