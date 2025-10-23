# Sécurité de l'API Blender

## Améliorations de sécurité implémentées

### ✅ Problèmes corrigés

1. **Token d'authentification sécurisé**
   - ❌ Token par défaut codé en dur `"your-secure-token-here"`
   - ✅ Génération automatique de token sécurisé si variable d'environnement absente
   - ✅ Usage obligatoire de la variable d'environnement `AUTH_TOKEN`

2. **Protection contre l'exécution de code arbitraire**
   - ✅ Ajout du flag `--disable-autoexec` à Blender
   - ✅ Validation stricte des fichiers .blend (signature)
   - ✅ Scanner de scripts Python suspects
   - ✅ Timeout de 5 minutes sur le rendu
   - ✅ Suppression automatique des fichiers suspects

3. **Validation des fichiers uploadés**
   - ✅ Vérification de l'extension (.blend uniquement)
   - ✅ Validation de la signature du fichier BLENDER
   - ✅ Limite de taille (100MB)
   - ✅ Détection de patterns suspects dans le contenu

4. **Protection CSRF**
   - ✅ Activation de `CSRFProtect`
   - ✅ Validation du token CSRF sur l'upload
   - ✅ Token CSRF dans le formulaire

5. **Autres améliorations**
   - ✅ Suppression de la route de debug `/debug_auth`
   - ✅ Mode debug désactivé en production
   - ✅ Génération automatique de `SECRET_KEY` sécurisée

## Configuration de production

### 1. Génération des tokens
```bash
python generate_tokens.py
```

### 2. Variables d'environnement
```bash
export AUTH_TOKEN="votre-token-securise"
export SECRET_KEY="votre-cle-secrete"
export FLASK_DEBUG=false
```

### 3. Fichier .env
```
AUTH_TOKEN=votre-token-securise
SECRET_KEY=votre-cle-secrete
FLASK_DEBUG=false
```

### 4. Installation des dépendances
```bash
pip install -r requirements.txt
```

## Fonctionnalités de sécurité

### Validation des fichiers .blend
- Vérification de la signature `BLENDER` 
- Limite de taille configurable (100MB par défaut)
- Scanner de scripts Python suspects
- Suppression automatique des fichiers invalides

### Patterns suspects détectés
- `import os`
- `subprocess`
- `exec()`
- `eval()`
- `__import__`
- `open()`
- `system()`
- `popen()`

### Protection Blender
- `--disable-autoexec` : Désactive l'auto-exécution des scripts
- Timeout de 5 minutes
- Isolation des processus de rendu

### CSRF Protection
- Token CSRF requis pour tous les uploads
- Validation automatique côté serveur
- Protection contre les attaques cross-site

## Recommandations supplémentaires

### Production
1. **HTTPS obligatoire** - Déployez avec SSL/TLS
2. **Reverse proxy** - Utilisez nginx ou apache
3. **Rate limiting** - Limitez les requêtes par IP
4. **Monitoring** - Surveillez les logs d'activité
5. **Backup** - Sauvegardez régulièrement les données

### Docker (optionnel)
Pour une isolation maximale, exécutez Blender dans un conteneur :
```bash
docker run --rm --memory=2g --cpus=2 --network=none \
  -v /path/to/blend:/input:ro \
  -v /path/to/output:/output \
  blender:latest blender -b /input/file.blend --disable-autoexec -f 1
```

### Surveillance
Surveillez ces métriques :
- Tentatives d'authentification échouées
- Fichiers rejetés par le scanner
- Processus Blender en cours
- Usage CPU/mémoire
- Taille des uploads

## Logs de sécurité

Les événements suivants sont loggés :
- ✅ Fichiers uploadés et validés
- ⚠️ Fichiers suspects détectés et rejetés
- ❌ Tentatives d'authentification échouées
- 🔒 Processus de rendu verrouillés/déverrouillés