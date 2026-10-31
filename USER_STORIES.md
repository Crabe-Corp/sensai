# CAHIER DES CHARGES : USER STORIES (PROJET SENSAI - THÈME "7 GRANDS ROYAUMES CONQUERANTS")

Les user stories sont des manieres dont ont interprete les features a faire par le point de vue des utilisateurs, dans cette exercices le but est de genere un cahiers des charges des features principale du projet.

### [B1] Base Obligatoire (CLI Chatbot)

En tant que créateur de monde, je veux interagir avec mon assistant via un terminal de commande réactif, afin de tester et développer le *lore* de mes royaumes rapidement.

**Critères d'acceptation :**
* Le texte généré par l'IA s'affiche de manière fluide (streaming) et non d'un seul bloc à la fin du calcul.
* L'utilisateur peut spécifier le modèle à utiliser (ex: `llama3`) via un argument au lancement de la commande sans modifier le code source.

En tant que développeur, je veux que le système gère proprement ses erreurs de connexion, afin d'éviter de perdre mon historique si le modèle plante.

**Critères d'acceptation :**
* Si le modèle Ollama est éteint ou inaccessible, le programme affiche un message d'erreur clair ("Modèle indisponible") au lieu de crasher.
* Si l'utilisateur envoie une requête vide, l'agent invite simplement à reformuler au lieu de générer une erreur fatale.


### 1. Mémoire & Contexte (Memory & Context)

#### [M1] Session Persistence & Profiles

En tant que créateur de monde (romancier ou game designer), je veux pouvoir charger une précédente session de chat, afin de ne perdre aucune idée de *worldbuilding* et continuer à développer mon univers avec l'agent.

**Critères d'acceptation :**
* Au lancement de l'application CLI, une liste des anciennes sessions sauvegardées s'affiche à l'écran.
* Si l'utilisateur charge une ancienne session et pose une question sur un élément inventé la veille (ex: "Combien d'or possède le Royaume de Glace ?"), l'agent répond correctement en utilisant l'historique mémorisé.

En tant que créateur de monde, je veux pouvoir lister, renommer ou supprimer mes anciennes conversations, afin de garder mon espace de travail organisé lorsque je développe l'histoire de plusieurs royaumes en parallèle.

**Critères d'acceptation :**
* L'utilisateur peut taper une commande (ex: `/sessions`) pour afficher la liste de toutes les conversations sauvegardées, triées par date.
* L'utilisateur peut exécuter une commande pour supprimer définitivement une session brouillon ou la renommer (ex: `Campagne_Royaume_Glace`).

#### [M2] Token Budgeting & Semantic Compression

En tant que maître du jeu, je veux que l'agent résume automatiquement les plus anciens échanges d'une longue session, afin de ne pas saturer la mémoire du modèle (contexte) lors de très longues parties.

**Critères d'acceptation :**
* Lorsqu'un seuil de tokens défini (ex: 4000 tokens) est atteint, l'agent génère un résumé compact des premiers messages en arrière-plan.
* L'utilisateur peut demander à l'agent de se souvenir d'un événement du début de session, et l'agent répond juste en se basant sur le résumé compressé.

En tant que joueur, je veux pouvoir définir manuellement la limite maximale de tokens au lancement de l'application, afin d'optimiser les performances sur une machine disposant de peu de mémoire vive.

**Critères d'acceptation :**
* L'application accepte un argument `--max-tokens 2000` au lancement.
* Le processus de compression se déclenche automatiquement dès que ce plafond spécifique est atteint.

#### [M3] External Structured Memory

En tant que Maître de Guerre, je veux que l'agent connaisse l'état initial des sept royaumes combattants au lancement d'une bataille, afin de simuler un affrontement cohérent basé sur leurs statistiques historiques.

**Critères d'acceptation :**
* Au démarrage d'une simulation, les sept royaumes (Qin, Chu, Qi, Zhao, Wei, Han, Yan) sont initialisés avec leurs statistiques de base (troupes, moral, or, général).
* L'agent peut répondre à "Quel est l'état actuel du Qin ?" en retournant les statistiques du royaume pour la bataille en cours.

En tant que Maître de Guerre, je veux que l'état de la simulation soit réinitialisé à chaque nouvelle bataille, afin de jouer des affrontements indépendants sans que les erreurs ou hallucinations d'une partie n'affectent la suivante.

**Critères d'acceptation :**
* Chaque simulation démarre avec un état propre, indépendant de toute bataille précédente.
* Si aucune simulation n'est active, l'agent indique clairement qu'il faut lancer `/simulation` avant de simuler un combat.

#### [M4] Artifact & State Document

En tant que romancier, je veux que l'agent tienne à jour une "Fiche de Royaume" dans un document séparé, afin de visualiser instantanément l'évolution des caractéristiques d'un royaume sans relire l'historique complet.

**Critères d'acceptation :**
* Lorsqu'une nouvelle alliance est conclue dans le chat, le document texte "Fiche_Royaume_Eau.md" est édité uniquement sur la ligne "Alliances" par l'agent.
* L'utilisateur peut consulter ce document sur son disque à tout moment et y trouver les informations à jour.

En tant que romancier, je veux que l'agent crée automatiquement ces fiches d'état si elles n'existent pas encore, afin de démarrer le *worldbuilding* d'une nouvelle faction sans devoir préparer les fichiers à l'avance.

**Critères d'acceptation :**
* Si l'utilisateur mentionne un nouveau royaume ("Le Royaume d'Ombre vient d'être fondé"), l'agent détecte l'absence de fiche et crée le fichier `Fiche_Royaume_Ombre.md` avec un squelette de base.
* Le terminal affiche une notification confirmant la création du nouvel artéfact.

---

### 2. Outils (Tools)

#### [T1] MCP (Model Context Protocol)

En tant que maître du jeu, je veux que l'agent puisse appeler un outil externe de génération de documents, afin de créer des traités ou des fiches de statistiques au format PDF prêts à être distribués aux joueurs.

**Critères d'acceptation :**
* Lorsque l'utilisateur demande un PDF, l'agent met sa réponse en pause, exécute le script de création PDF, puis confirme la création dans le chat.
* Un fichier `.pdf` valide est généré dans le répertoire de travail.

En tant que créateur de jeu, je veux que l'agent simule des batailles et documente les résultats dans des fichiers structurés (JSON ou MD), afin de les comprendres facilement.

**Critères d'acceptation :**
* L'agent utilise un outil pour formater l'issue d'une bataille en un fichier JSON contenant des clés précises (`"pertes"`, `"vainqueur"`, `"butin"`).
* Le fichier est créé sur le disque et le formatage JSON est strict et valide.

#### [T3] Web Search

En tant que romancier, je veux que l'agent puisse faire des recherches sur internet en direct, afin de me proposer des tactiques de siège médiévales historiquement crédibles pour mes batailles fictives.

**Critères d'acceptation :**
* Lorsqu'on pose une question technique, le terminal affiche un indicateur de recherche web (ex: `[Recherche en cours...]`).
* L'agent cite l'URL de sa source réelle à la fin de son explication.

En tant que créateur de monde, je veux que l'agent vulgarise et adapte les informations techniques trouvées en ligne, afin de les intégrer de manière fluide dans le *lore* de mon univers.

**Critères d'acceptation :**
* La réponse intègre les données web tout en utilisant le vocabulaire des "7 Grands Royaumes Conquerants" (ex: adapter aux vocabulaire relatif à la Chine féodale).
* Le texte généré synthétise les articles sources sans faire de copier-coller brut.

#### [T4] File Access within Permissions

En tant que Maître de Guerre, je veux que l'agent puisse écrire le rapport final d'une simulation de bataille dans un dossier autorisé, afin de conserver une trace structurée de chaque affrontement entre royaumes combattants.

**Critères d'acceptation :**
* L'agent peut créer un rapport de bataille au format `.md` uniquement dans le dossier `battle_reports/`, via l'outil `write_battle_report`.
* Toute tentative d'écriture en dehors de ce dossier (path traversal, autre répertoire) est bloquée par le système de permissions et la raison du refus est communiquée à l'agent.

En tant que Maître de Guerre, je veux pouvoir relire un rapport de bataille précédemment sauvegardé, afin d'analyser l'évolution des forces en présence au fil des tours de simulation.

**Critères d'acceptation :**
* L'agent peut lire un fichier `.md` existant dans `battle_reports/` via l'outil `read_battle_report` et en restituer le contenu dans le chat.
* Les fichiers d'extension incorrecte (ex : `.txt`, `.json`) ou situés hors de `battle_reports/` sont refusés en lecture comme en écriture, avec un message explicite.

#### [T5] Structured Output

En tant que développeur, je veux forcer l'agent à me renvoyer les statistiques d'un type d'unité historique (ex: "Arbalétriers de Qin" ou "Chars de guerre") uniquement au format JSON, afin de pouvoir intégrer cette unité directement dans la base de données de mon jeu sans avoir à nettoyer du texte superflu.

**Critères d'acceptation :**
* La réponse de l'agent ne contient aucun texte poli (ex: "Voici votre unité de chars :").
* La réponse est un objet JSON pur et strictement conforme au schéma imposé (Points de vie, Attaque, Défense).

En tant que développeur, je veux que l'agent renvoie une erreur JSON standardisée s'il ne comprend pas ma demande de génération procédurale, afin que mon application puisse gérer l'échec de manière programmatique.

**Critères d'acceptation :**
* En cas de requête absurde, l'agent renvoie un objet `{"error": "description du problème", "code": 400}` au lieu d'un texte d'excuse.
* L'application réceptrice peut parser cette erreur avec `json.loads()` sans exception.

---

### 3. Recherche documentaire (RAG)

#### [R1] Basic RAG

En tant que maître du jeu, je veux que l'agent lise et recherche des informations dans mon manuel de règles en PDF, afin qu'il me rappelle précisément comment fonctionne la diplomatie en temps de guerre.

**Critères d'acceptation :**
* L'agent indexe le document fourni au démarrage en créant des *embeddings*.
* L'agent retrouve le bon paragraphe et base sa réponse exclusivement sur ce document en citant le passage.

En tant que maître du jeu, je veux pouvoir ingérer de nouveaux fichiers textes en plein milieu de la session, afin de mettre à jour les connaissances de l'agent sans devoir redémarrer le système.

**Critères d'acceptation :**
* L'utilisateur peut taper une commande `/learn nouveau_chapitre.txt`.
* L'agent découpe le nouveau fichier, met à jour sa base vectorielle en arrière-plan, et peut immédiatement répondre à des questions sur ce nouveau texte.

---

### 4. Orchestration & Raisonnement

#### [A3] Human-in-the-Loop

En tant que Maître de Guerre, je veux sélectionner individuellement les changements issus d'une bataille simulée que je souhaite appliquer ou ignorer, afin de garder le contrôle sur les résultats avant qu'ils ne soient entérinés.

**Critères d'acceptation :**
* Après le calcul d'une bataille (`simulate_battle`), l'agent présente la liste des changements proposés (pertes de troupes, chute d'un général, etc.) et l'utilisateur peut les accepter tous, les rejeter tous, ou en sélectionner un sous-ensemble.
* Seuls les changements explicitement validés sont appliqués ; les autres sont ignorés sans modifier l'état de la simulation.

En tant que Maître de Guerre, je veux confirmer l'écriture du rapport de bataille avant qu'il ne soit sauvegardé sur disque, afin de m'assurer que le compte-rendu reflète bien ce qui s'est passé durant cet affrontement.

**Critères d'acceptation :**
* Avant de sauvegarder dans `battle_reports/`, l'agent affiche un aperçu du rapport et demande une confirmation explicite (CLI : O/N, web : bouton d'approbation dans l'interface).
* Si le fichier existe déjà, le message indique explicitement qu'il sera écrasé. Si l'utilisateur refuse, aucun fichier n'est créé ni modifié.

#### [A4] Prompt Versioning

En tant que développeur, je veux sauvegarder les différentes versions de mon "Prompt Système" (ex: la personnalité de l'Empereur), afin de comparer quelle version produit les meilleurs dialogues géopolitiques.

**Critères d'acceptation :**
* L'utilisateur peut lister les anciens prompts via une commande (ex: `/prompts`).
* Il est possible de charger la version 1.2 du prompt et de tester une réponse pour comparer avec la version 2.0.

En tant que développeur, je veux associer des métadonnées (date, auteur, notes) à chaque version de prompt, afin de me souvenir pourquoi une modification spécifique a été apportée.

**Critères d'acceptation :**
* Lors de la sauvegarde d'un nouveau prompt, le système invite à saisir un message de commit (ex: "Ajout de la consigne sur l'accent de l'Empereur").
* L'historique affiche ces notes à côté des numéros de version.

#### [A5] Persona

En tant que romancier, je veux pouvoir basculer dynamiquement la personnalité de l'agent (de "Général" à "Espion"), afin d'obtenir des points de vue radicalement différents sur la même situation politique.

**Critères d'acceptation :**
* En tapant `/persona espion`, le ton et le vocabulaire de l'agent changent immédiatement pour devenir furtifs et manipulateurs.
* L'historique factuel de la conversation est conservé malgré le changement de rôle.

En tant que romancier, je veux définir mes propres Personas via un fichier de configuration externe, afin de personnaliser entièrement le casting de mon univers sans modifier le code.

**Critères d'acceptation :**
* Un fichier `personas.json` permet de lister de nouveaux rôles et leurs instructions système respectives.
* L'application charge ce fichier au démarrage et rend les nouveaux Personas immédiatement disponibles via la commande `/persona`.

#### [A6] Semantic Cache

En tant que créateur de jeu, je veux que le système garde en cache les questions fréquentes (ex: "Quel est le coût d'une forteresse ?"), afin d'obtenir une réponse instantanée et d'économiser les ressources de calcul du modèle LLM.

**Critères d'acceptation :**
* Une question formulée légèrement différemment ("Combien coûte la construction d'une forteresse ?") déclenche le cache grâce à l'évaluation sémantique.
* Le temps de réponse (affiché dans le terminal) tombe sous la barre des 50 millisecondes.

En tant que créateur de jeu, je veux pouvoir vider manuellement ce cache sémantique, afin de forcer l'agent à recalculer ses réponses après une mise à jour des règles du jeu.

**Critères d'acceptation :**
* L'utilisateur peut taper `/clearcache` dans le terminal.
* La même question posée ensuite est obligatoirement traitée par le modèle LLM et génère une réponse actualisée.

---

### 5. Évaluation & Sécurité

#### [EV1] Automated Eval & Hallucination Detection

En tant que romancier, je veux qu'un système automatique signale si l'agent invente une fausse alliance ou un lieu inexistant, afin de garantir la cohérence absolue de mon univer.

**Critères d'acceptation :**
* À la fin de la génération, une évaluation croisée est effectuée.
* Si l'agent invente une ville non répertoriée dans les documents sources, un avertissement de potentiel risque d'hallucination s'affiche (ex: `[Alerte Hallucination détectée]`).

En tant que développeur, je veux qu'un second LLM juge automatiquement la qualité des réponses selon une grille prédéfinie, afin d'automatiser mes tests de non-régression.

**Critères d'acceptation :**
* L'exécution d'un script d'évaluation note 10 échanges sur 10 selon des critères de concision et de respect de l'univers.
* Un score final sur 100 est généré en sortie de script.

#### [EV2] Content & Privacy Guardrails

En tant que développeur de l'outil, je veux que l'agent bloque toute requête qui sort du thème de la Chine antique et des Royaumes Combattants, afin d'assurer que les utilisateurs restent concentrés sur l'expérience historique et la simulation de batailles.

**Critères d'acceptation :**
* Si l'utilisateur demande "Donne-moi une recette de cuisine moderne" ou mentionne un sujet explicitement hors-thème (jeux vidéo modernes, technologie contemporaine), le filtre à l'entrée bloque la requête.
* L'agent refuse poliment de répondre via un message d'erreur standardisé ("Le conseiller impérial refuse de discuter de ce sujet.") sans appeler le LLM lourd.

En tant que développeur, je veux que le système anonymise automatiquement les données personnelles réelles (emails, numéros de téléphone) saisies par erreur, afin de garantir la confidentialité de l'utilisateur.

**Critères d'acceptation :**
* Si l'utilisateur tape un vrai numéro de téléphone ou une adresse email dans son prompt, un filtre le remplace par `[DONNÉE MASQUÉE]` avant de l'envoyer au modèle.
* Le log de la conversation n'enregistre aucune donnée sensible.

#### [EV3] Logging & Monitoring Dashboard

En tant que développeur, je veux visualiser le temps de réponse et le coût en tokens de mes sessions de simulation, afin d'optimiser les performances de mon application.

**Critères d'acceptation :**
* Les données de chaque requête (latence, tokens utilisés, outil appelé) sont écrites systématiquement dans un fichier de logs (`logs.csv` ou base de données métriques).
* Les données sont structurées pour être facilement exploitables.

En tant que développeur, je veux accéder à un tableau de bord visuel, afin de surveiller la santé de mon système en un coup d'œil.

**Critères d'acceptation :**
* Une commande permet de lancer une petite page web de monitoring affichant des graphiques (latence moyenne, pics d'utilisation des tokens).
* Les graphiques se mettent à jour en temps réel à chaque nouvelle requête traitée par l'agent.

---

### 6. Expérience Utilisateur & Cycle de Vie (UX)

#### [X1] Web UI

En tant que maître du jeu, je veux utiliser une interface web graphique au lieu du terminal, afin de gérer mes 7 royaumes avec un confort de lecture optimal.

**Critères d'acceptation :**
* L'application peut être lancée via une URL locale (`localhost`) affichant une interface type messagerie.
* L'interface affiche proprement les messages, interprète le Markdown (gras, tableaux) et gère le streaming du texte.

En tant que maître du jeu, je veux avoir des indicateurs visuels dans l'interface, afin de surveiller la technique sans ouvrir le terminal.

**Critères d'acceptation :**
* L'interface web intègre une barre latérale ou un badge montrant le nombre de tokens consommés pour la session en cours.
* Un menu déroulant graphique permet de changer le modèle LLM actif en un clic.

#### [X2] Branching - Resume & Interrupt

En tant que scénariste, je veux pouvoir modifier mon message précédent pour faire gagner un autre royaume lors d'une bataille passée, afin d'explorer une autre branche narrative sans recommencer toute la session.

**Critères d'acceptation :**
* L'utilisateur peut cibler et éditer un message passé (ex: le message #4).
* L'agent génère une nouvelle suite à partir de la nouvelle branche, créant un "univers parallèle" à partir de ce point.

En tant que scénariste, je veux pouvoir stopper une génération en plein milieu de phrase, afin de redonner immédiatement une instruction si je vois que l'agent part dans la mauvaise direction.

**Critères d'acceptation :**
* Un raccourci clavier (ex: `Ctrl+C` adapté) interrompt le streaming de la réponse textuelle.
* L'application redonne instantanément la main à l'utilisateur pour taper un nouveau prompt.

#### [X3] Export & Publication

En tant que maître du jeu, je veux pouvoir exporter le récapitulatif de notre session de jeu au format Markdown ou PDF, afin de l'envoyer par e-mail aux joueurs le lendemain.

**Critères d'acceptation :**
* La commande `/export pdf` ou `/export md` génère le fichier formaté correspondant sur le disque.
* Le document final est lisible et conserve la structure des échanges.

En tant que maître du jeu, je veux que l'export nettoie automatiquement la conversation, afin de fournir un document propre sans les commandes techniques de la session.

**Critères d'acceptation :**
* Le système d'export purge automatiquement les commandes comme `/persona`, `/learn` ou les messages d'erreurs annulés.
* Le document final ne contient que la partie narrative ou *roleplay* de l'échange.

#### [X4] Questions & Forms

En tant que game designer, je veux que l'agent me présente un petit formulaire interactif lorsque je crée une nouvelle faction, afin de m'assurer que je n'oublie de lui renseigner aucune statistique vitale (Nom, Économie, Militaire).

**Critères d'acceptation :**
* Au déclenchement de la création, l'agent pose les questions une par une et attend la réponse de l'utilisateur avant de passer à la suivante.
* Une fois le formulaire rempli, l'agent génère le récapitulatif complet de la faction.

En tant que game designer, je veux pouvoir annuler ou quitter ce formulaire en cours de route, afin de revenir à la conversation libre si j'ai changé d'avis.

**Critères d'acceptation :**
* L'utilisateur peut taper `annuler` ou `/quit` lors d'une question du formulaire.
* L'agent abandonne le processus de création de faction et se remet en attente d'un prompt standard.