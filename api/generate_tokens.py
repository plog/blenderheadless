#!/usr/bin/env python3
"""
Script de génération de tokens sécurisés pour l'API Blender
Usage: python generate_tokens.py
"""

import secrets

def generate_secure_tokens():
    """Génère des tokens sécurisés pour l'authentification et les sessions"""
    
    print("=== Générateur de tokens sécurisés ===\n")
    
    # Token d'authentification
    auth_token = secrets.token_urlsafe(32)
    print(f"AUTH_TOKEN={auth_token}")
    
    # Clé secrète pour les sessions
    secret_key = secrets.token_hex(32)
    print(f"SECRET_KEY={secret_key}")
    
    print("\n=== Instructions ===")
    print("1. Copiez ces variables dans votre fichier .env")
    print("2. Ou définissez-les comme variables d'environnement")
    print("3. Redémarrez votre application")
    print("\nExemple pour .env:")
    print(f"AUTH_TOKEN={auth_token}")
    print(f"SECRET_KEY={secret_key}")
    
    print("\nExemple pour variables d'environnement:")
    print(f"export AUTH_TOKEN='{auth_token}'")
    print(f"export SECRET_KEY='{secret_key}'")

if __name__ == "__main__":
    generate_secure_tokens()