# sensai
projet IA de la mort


### RAG

pour l'initialisation du RAG il faudrais executer le fichier RAG_embedding et s'assurer d'avoir le model nomic-embed-text d'installer sur la machine car c'est ce model qui vas parcourire les centaines de fichier historique sur la perdiode des 7 royaumes combattant pour les transformer en vector et les stocker dans la base de donner qdrant (vector_db container) qui est expert dans le stockage de vector.

Cette etape vas etre a réaliser une seul fois pour avoir la base de donnée set a chaque creation de volume, ce qui veut dire a chaque initialisation de projet et apres chaque docker compose docn -v qui reinitialise les volumes. 

Ensuite le modele iras automatiquement chercher une correspondence avec les prompt donner et les données stocker dans la db de vector. ce qu'il vas faire precisement cest treansformer le prompt de la meme maniere que les text en vector et comparer ensuite les vector pour trouver les vector stocké en base qui se rapproche le plus des sujet traité dans le prompt.