# Instant Messaging Application — v0.2

Une application de messagerie **temps réel** en Python.  
Client graphique en **(Custom)Tkinter**, serveur TCP en Python, persistance **SQLite**.  
Elle gère l’authentification, les messages privés, les groupes, l’historique et plus.

---

## ✨ Features

- **User Authentication** : inscription / connexion (username, password, email).
- **Private Messaging (DM)** : envoyez des messages directs à un utilisateur.
- **Group Chats** : créez des groupes, ajoutez des membres, rôle admin/membre.
- **Message History** : récupérez l’historique de groupe à la demande.
- **Profile Management** : changez votre nom d’utilisateur pendant la session.
- **Real-Time Communication** : sockets + threads pour un affichage instantané.
- **UI Moderne (v0.2)** : client en *CustomTkinter* (thème sombre, champs avec placeholders, boutons arrondis).
- **Migration DB Auto** : ajout des colonnes `ts` si absentes (compat anciens schémas).

---

## 🔧 Prérequis

### Core
- **Python 3.11+** recommandé  
  *(3.13 fonctionne, mais 3.11/3.12 sont plus stables côté écosystème)*

### Librairies
| Catégorie                   | Librairies                        | Installation                         |
|----------------------------|-----------------------------------|--------------------------------------|
| **UI**                     | Tkinter (standard), CustomTkinter | `pip install customtkinter`          |
| **Images (optionnel)**     | Pillow                            | `pip install pillow`                 |
| **DB**                     | SQLite3                           | *(inclus avec Python)*               |
| **Réseau / Threads**       | socket, threading                 | *(inclus avec Python)*               |

> **Windows / Tkinter** : si `python -m tkinter` ne lance pas une petite fenêtre de test, réinstalle Python en **Customize installation** avec **Tcl/Tk** coché, puis clique **Disable path length limit** à la fin.

---

## 📦 Installation

1) **Cloner le dépôt**
```bash
git clone https://github.com/aalaliayoub/instaChat.git
cd instaChat
```
2) **(Optionnel) Environnement virtuel**
```bash
python -m venv venv
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate
```
3) **Installer les dépendances UI**
```bash
pip install -U pip
pip install customtkinter pillow
```
4) **Lancer le serveur (terminal 1)**
```bash
python server.py
```
5) **Lancer le client (terminal 2)**
```bash
python client.py
```
6)** Astuces & Dépannage**

- Tkinter / init.tcl introuvable (Windows)
Réinstalle Python → Customize installation → Tcl/Tk and IDLE coché → Disable path length limit.

- Port occupé (WinError 10048)
Change SERVER_PORT (ex. 12346) ou libère le port.

- Ancienne DB (erreur colonne ts)
La v0.2 applique une migration auto ; sinon supprime MyData1.db (réinitialise les données).

- Pare-feu Windows
Autorise Python sur réseau privé pour connexion client↔serveur.
## 7) Roadmap (v0.3)

- Sélection/switch entre plusieurs groupes par utilisateur

- Chiffrement basique des messages (transport)

- Envoi de fichiers / images

- Statut en ligne / “en train d’écrire”

- Tests + CI

