# -*- coding: utf-8 -*-
import json
import socket
import threading
import sqlite3
import time

# ---------- Réseau ----------
SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 12345
ENC = "utf-8"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((SERVER_IP, SERVER_PORT))
server.listen()
print("listening on", SERVER_IP, SERVER_PORT)

# ---------- État en mémoire ----------
clients = []                 # sockets alignées avec "names"
names = []                   # noms alignés avec "clients"

# group_id -> {"admin": str, "members": set[str]}
groups = {}

# user -> current_group_id (pour router les messages "texte brut")
current_group_by_user = {}

lock = threading.Lock()

# ---------- SQLite ----------
DB = "MyData1.db"

def init_db():
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS client(
            nom TEXT PRIMARY KEY,
            password TEXT,
            email TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS messages(
            nomemetteur TEXT,
            nomdestination TEXT,
            message TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS group_messages(
            group_id INTEGER,
            sender TEXT,
            message TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS groups(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS group_members(
            group_id INTEGER,
            member TEXT
        )""")
        conn.commit()

def migrate_add_ts_columns():
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()

        # messages: ajouter ts si manquant
        cur.execute("PRAGMA table_info(messages)")
        cols = [c[1] for c in cur.fetchall()]
        if "ts" not in cols:
            cur.execute("ALTER TABLE messages ADD COLUMN ts REAL")
            cur.execute("UPDATE messages SET ts = rowid")
            conn.commit()

        # group_messages: ajouter ts si manquant
        cur.execute("PRAGMA table_info(group_messages)")
        cols = [c[1] for c in cur.fetchall()]
        if "ts" not in cols:
            cur.execute("ALTER TABLE group_messages ADD COLUMN ts REAL")
            cur.execute("UPDATE group_messages SET ts = rowid")
            conn.commit()

init_db()
migrate_add_ts_columns()

# ---------- Utilitaires envoi ----------
def _send_to_name(dst_name: str, payload: str):
    """envoie payload à UN utilisateur (si connecté)"""
    with lock:
        for i, c in enumerate(clients):
            if names[i] == dst_name:
                try:
                    c.send(payload.encode(ENC))
                except Exception:
                    pass
                return

def _broadcast_to_names(dst_names: set[str], payload: str):
    """envoie payload à un ensemble d'utilisateurs connectés"""
    with lock:
        for i, c in enumerate(clients):
            if names[i] in dst_names:
                try:
                    c.send(payload.encode(ENC))
                except Exception:
                    pass

def _send_user_list(to_name: str):
    """len==3 : envoie la liste des utilisateurs au demandeur (format attendu par le client)"""
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT nom FROM client")
        all_names = [row[0] for row in cur.fetchall()]
    payload_json = json.dumps([[n] for n in all_names])  # [[name],[name],...]
    packet = f"{payload_json}/new/list"  # -> len==3 (json / 'new' / 'list')
    _send_to_name(to_name, packet)

# ---------- Groupes ----------
def _create_group(admin: str, members: list[str]) -> int:
    """
    Crée un groupe: admin + members (y compris admin).
    Retourne group_id ; définit le groupe courant pour tous les membres.
    """
    # nettoyer doublons + s’assurer que admin est dedans
    uniq = []
    seen = set()
    for m in members:
        if m and m not in seen:
            uniq.append(m); seen.add(m)
    if admin not in seen:
        uniq.insert(0, admin); seen.add(admin)

    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO groups(admin) VALUES(?)", (admin,))
        gid = cur.lastrowid
        for m in uniq:
            cur.execute("INSERT INTO group_members(group_id, member) VALUES(?,?)", (gid, m))
        conn.commit()

    # enregistrer en mémoire
    with lock:
        groups[gid] = {"admin": admin, "members": set(uniq)}
        for m in uniq:
            current_group_by_user[m] = gid

    return gid

def _add_members_to_group(admin: str, new_members: list[str]):
    """Ajoute des membres au groupe courant de l'admin"""
    gid = current_group_by_user.get(admin)
    if gid is None or gid not in groups:
        return None

    to_add = []
    with lock:
        for m in new_members:
            if m and m not in groups[gid]["members"]:
                groups[gid]["members"].add(m)
                to_add.append(m)

    if not to_add:
        return gid

    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        for m in to_add:
            cur.execute("INSERT INTO group_members(group_id, member) VALUES(?,?)", (gid, m))
        conn.commit()

    # le groupe ajouté devient aussi groupe courant de ces nouveaux membres
    with lock:
        for m in to_add:
            current_group_by_user[m] = gid

    return gid

def _notify_group_role(gid: int):
    """
    Envoie aux membres un paquet len==5 pour que l’UI affiche Admin / Membre.
    Format: f"GROUP/{admin}/{gid}/ok/ok" (5 segments)
    Le client regarde parts[1] pour savoir si c’est lui l’admin.
    """
    with lock:
        if gid not in groups: return
        admin = groups[gid]["admin"]
        members = set(groups[gid]["members"])

    packet = f"GROUP/{admin}/{gid}/ok/ok"  # len == 5
    _broadcast_to_names(members, packet)

def _send_group_history(to_name: str):
    """len==4 : renvoie l’historique du groupe courant de l’utilisateur"""
    gid = current_group_by_user.get(to_name)
    if gid is None:  # pas de groupe courant
        payload = json.dumps([])
        packet = f"{payload}/group/historique/tout"
        _send_to_name(to_name, packet)
        return

    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT sender || ': ' || message
            FROM group_messages
            WHERE group_id=?
            ORDER BY ts ASC
        """, (gid,))
        rows = [r[0] for r in cur.fetchall()]
    payload = json.dumps([[line] for line in rows])  # [[msg],[msg],...]
    packet = f"{payload}/group/historique/tout"  # len==4
    _send_to_name(to_name, packet)

def _broadcast_group_message(sender: str, text: str):
    """Diffuser un message au groupe courant du sender + sauver en DB"""
    gid = current_group_by_user.get(sender)
    if gid is None:  # pas de groupe courant → ignorer
        return
    with lock:
        members = set(groups.get(gid, {}).get("members", set()))
    msg_line = f"{sender}:{text}"
    # enregistrer
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO group_messages(group_id, sender, message, ts) VALUES(?,?,?, strftime('%s','now'))",
                    (gid, sender, text))
        conn.commit()
    # diffuser (len==2 pour les messages live groupe : "msg/group")
    packet = f"{msg_line}/group"
    _broadcast_to_names(members, packet)

# ---------- Handlers ----------
def handle_client(client: socket.socket):
    while True:
        try:
            raw = client.recv(1024).decode(ENC)
            if not raw:
                raise ConnectionError

            # retrouver le nom de l’émetteur
            with lock:
                try:
                    idx = clients.index(client)
                    sender = names[idx]
                except ValueError:
                    sender = None

            # 1) Changement de nom: "nouveauNom!changerlenom"
            if "!" in raw and sender:
                new_name, _ = raw.split("!", 1)
                with sqlite3.connect(DB) as conn:
                    cur = conn.cursor()
                    cur.execute("UPDATE client SET nom=? WHERE nom=?", (new_name, sender))
                    cur.execute("UPDATE messages SET nomemetteur=? WHERE nomemetteur=?", (new_name, sender))
                    cur.execute("UPDATE messages SET nomdestination=? WHERE nomdestination=?", (new_name, sender))
                    conn.commit()
                with lock:
                    names[idx] = new_name
                    # déplacer le groupe courant si existait
                    if sender in current_group_by_user:
                        current_group_by_user[new_name] = current_group_by_user.pop(sender)
                # message d'info visible par le groupe courant (si existe)
                gid = current_group_by_user.get(new_name)
                if gid and gid in groups:
                    _broadcast_group_message(new_name, f"*{sender} → {new_name}*")
                continue

            # 2) Création groupe: JSON + "@addgroup"
            if raw.endswith("@addgroup") and sender:
                json_payload = raw.split("@addgroup")[0]
                try:
                    members = json.loads(json_payload)
                except Exception:
                    members = [sender]
                gid = _create_group(sender, members)
                _notify_group_role(gid)
                _broadcast_group_message(sender, "groupe créé")
                continue

            # 3) Ajout membres: JSON + "@addgroup@new"
            if raw.endswith("@addgroup@new") and sender:
                json_payload = raw.split("@addgroup@new")[0]
                try:
                    new_m = json.loads(json_payload)
                except Exception:
                    new_m = []
                gid = _add_members_to_group(sender, new_m)
                if gid is not None:
                    _notify_group_role(gid)
                    _broadcast_group_message(sender, f"{', '.join(new_m)} ont été ajoutés")
                continue

            # 4) Demande de liste utilisateurs: "list/new/list"
            if raw == "list/new/list" and sender:
                _send_user_list(sender)
                continue

            # 5) Historique groupe
            if raw == "Historique" and sender:
                _send_group_history(sender)
                continue

            # 6) DM : "message/cible"
            if "/" in raw:
                parts = raw.split("/")
                if len(parts) == 2 and sender:
                    msg, target = parts
                    msg = msg.strip()
                    target = target.strip()
                    if msg:
                        with sqlite3.connect(DB) as conn:
                            cur = conn.cursor()
                            cur.execute(
                                "INSERT INTO messages(nomemetteur,nomdestination,message,ts) VALUES(?,?,?, strftime('%s','now'))",
                                (sender, target, msg)
                            )
                            conn.commit()
                        _send_to_name(target, f"{sender}:{msg}\n")
                continue

            # 7) Message de groupe : texte brut
            if sender:
                text = raw.strip()
                if text:
                    _broadcast_group_message(sender, text)

        except ConnectionError:
            # cleanup
            try:
                with lock:
                    if client in clients:
                        i = clients.index(client)
                        dead_name = names[i]
                        clients.pop(i)
                        names.pop(i)
                        # retirer des groupes en mémoire
                        for gid, g in list(groups.items()):
                            if dead_name in g["members"]:
                                g["members"].discard(dead_name)
                        current_group_by_user.pop(dead_name, None)
                client.close()
            except Exception:
                pass
            break
        except Exception:
            # ignorer erreurs transitoires
            continue

# ---------- Auth ----------
def _send_connected_banner(to_name: str):
    _send_to_name(to_name, "You are connected!\n")
    # Rejouer quelques DM en retard (tri par ts)
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT nomemetteur, message FROM messages WHERE nomdestination=? ORDER BY ts ASC", (to_name,))
        for em, m in cur.fetchall():
            _send_to_name(to_name, f"{em}:{m}\n")

def _handle_signup(client: socket.socket, payload: str):
    # payload: "nom/password/email/passwordConfirm"
    parts = payload.split("/")
    if len(parts) != 4:
        client.detach(); return
    nom, password, email, password2 = parts
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM client WHERE nom=?", (nom,))
        exists = cur.fetchone() is not None
        # renvoyer la liste des noms (compat client)
        cur.execute("SELECT DISTINCT nom FROM client")
        alln = [r[0] for r in cur.fetchall()]
        reply = " " + "".join(f"/{n}" for n in alln)
        client.send(reply.encode(ENC))
        if exists or password != password2:
            client.detach()
            return
        # créer
        cur.execute("INSERT INTO client(nom,password,email) VALUES(?,?,?)", (nom, password, email))
        conn.commit()

    # connecter
    with lock:
        clients.append(client)
        names.append(nom)
    _send_connected_banner(nom)

    threading.Thread(target=handle_client, args=(client,), daemon=True).start()

def _handle_signin(client: socket.socket, payload: str):
    # payload: "nom/password"
    parts = payload.split("/")
    if len(parts) != 2:
        client.detach(); return
    nom, password = parts
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        # renvoyer la liste des noms (compat client)
        cur.execute("SELECT DISTINCT nom FROM client")
        alln = [r[0] for r in cur.fetchall()]
        reply = " " + "".join(f"/{n}" for n in alln)
        client.send(reply.encode(ENC))

        if nom in alln:
            cur.execute("SELECT password FROM client WHERE nom=?", (nom,))
            row = cur.fetchone()
            if not row:
                client.detach(); return
            real_pass = row[0]
            client.send(real_pass.encode(ENC))
            if password == real_pass:
                with lock:
                    clients.append(client)
                    names.append(nom)
                _send_connected_banner(nom)
                threading.Thread(target=handle_client, args=(client,), daemon=True).start()
            else:
                try:
                    client.detach()
                except Exception:
                    pass
        else:
            try:
                client.detach()
            except Exception:
                pass

# ---------- Accept loop ----------
def accept_loop():
    while True:
        client, addr = server.accept()
        first = client.recv(1024).decode(ENC)
        if first.count("/") == 3:
            _handle_signup(client, first)
        else:
            _handle_signin(client, first)

accept_loop()
