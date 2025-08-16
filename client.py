import socket
import threading
import tkinter.messagebox as messagebox
import json
import os
import sys
import customtkinter as ctk

FORMATT = "utf-8"

# ---------- Utilitaire ----------
def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ---------- Client réseau ----------
class ChatClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect()

    def connect(self):
        try:
            self.sock.close()
        except Exception:
            pass
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))

    def send(self, text: str):
        self.sock.send(text.encode(FORMATT))

    def recv(self, size: int = 1024) -> str:
        return self.sock.recv(size).decode(FORMATT)

    def detach(self):
        try:
            self.sock.detach()
        except Exception:
            pass

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

# ---------- Application ----------
class ModernChatApp(ctk.CTk):
    def __init__(self, server_host: str, server_port: int):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Instant Messaging")
        self.geometry("1100x640")
        self.minsize(980, 600)

        try:
            self.iconbitmap(resource_path("messager.ico"))
        except Exception:
            pass

        self.client = ChatClient(server_host, server_port)
        self.username = ""
        self.all_users = []
        self.group_buffer = []
        self.group_add_buffer = []
        self.recv_thread = None
        self.stop_recv = threading.Event()

        self.signin_frame = None
        self.signup_frame = None
        self.chat_frame = None

        self.show_signin()

    # ---- navigation écrans ----
    def clear_main(self):
        for w in self.winfo_children():
            w.destroy()

    def show_signin(self):
        self.clear_main()
        self.signin_frame = SignInFrame(self, on_signin=self.handle_signin, on_switch_signup=self.show_signup)
        self.signin_frame.pack(fill="both", expand=True)

    def show_signup(self):
        self.clear_main()
        self.signup_frame = SignUpFrame(self, on_signup=self.handle_signup, on_switch_signin=self.show_signin)
        self.signup_frame.pack(fill="both", expand=True)

    def show_chat(self):
        self.clear_main()
        self.chat_frame = ChatFrame(
            self,
            on_send_direct=self.send_direct_message,
            on_send_group_text=self.send_group_text,
            on_request_history=self.request_history,
            on_logout=self.logout,
            on_clear_chat=self.clear_group_area,
            on_create_group=self.create_group,
            on_add_members=self.add_members_to_group,
            on_refresh_users=self.refresh_users,
            on_change_name=self.change_username
        )
        self.chat_frame.pack(fill="both", expand=True)

        # pousser la liste connue (DM + picker de droite)
        self.chat_frame.update_user_list(self.all_users or [" "])

        self.stop_recv.clear()
        self.recv_thread = threading.Thread(target=self.recv_loop, daemon=True)
        self.recv_thread.start()

    # ---- auth ----
    def handle_signin(self, username: str, password: str):
        try:
            self.username = username
            self.client.send(f"{username}/{password}")

            resp = self.client.recv()
            rows = resp.split("/")
            if username in rows:
                rows.remove(username)
            self.all_users = rows

            if username not in resp:
                if messagebox.askretrycancel("Erreur", "Vous n'avez pas de compte. Cliquez sur Sign Up."):
                    self.client.detach()
                    self.client = ChatClient(self.client.host, self.client.port)
                else:
                    self.client.detach()
                    self.show_signin()
                return

            server_password = self.client.recv()
            if password != server_password:
                if messagebox.askretrycancel("Erreur", "Mot de passe incorrect. Réessayer ?"):
                    self.client.detach()
                    self.client = ChatClient(self.client.host, self.client.port)
                else:
                    self.client.detach()
                    self.show_signin()
                return

            self.group_buffer = [username]
            self.show_chat()

        except Exception as e:
            messagebox.showerror("Connexion", f"Échec de connexion: {e}")

    def handle_signup(self, username: str, email: str, password: str, password_confirm: str):
        try:
            self.client.send(f"{username}/{password}/{email}/{password_confirm}")
            info = self.client.recv()
            noms = info.split("/")

            if username in noms:
                if messagebox.askretrycancel("Erreur", "Compte déjà existant. Cliquez sur Sign In ou changez le username."):
                    self.client.detach()
                    self.client = ChatClient(self.client.host, self.client.port)
                else:
                    self.client.detach()
                    self.show_signin()
                return

            if password != password_confirm:
                messagebox.showwarning("Erreur", "La confirmation du mot de passe est incorrecte.")
                self.client.detach()
                self.client = ChatClient(self.client.host, self.client.port)
                return

            self.username = username
            self.group_buffer = [username]
            self.show_chat()

        except Exception as e:
            messagebox.showerror("Inscription", f"Erreur: {e}")

    # ---- réception ----
    def recv_loop(self):
        while not self.stop_recv.is_set():
            try:
                raw = self.client.recv()
                if not raw:
                    continue
                parts = raw.split("/")

                if len(parts) == 1:
                    if self.chat_frame:
                        self.chat_frame.append_global(parts[0])

                elif len(parts) == 5:
                    if self.chat_frame:
                        self.chat_frame.ensure_group_mode(admin=(parts[1] == self.username))

                elif len(parts) == 2:
                    if self.chat_frame:
                        self.chat_frame.append_group(parts[0])

                elif len(parts) == 3:
                    try:
                        users_json = json.loads(parts[0])
                        names = [u[0] for u in users_json]
                    except Exception:
                        names = []
                    if self.username in names:
                        try:
                            names.remove(self.username)
                        except ValueError:
                            pass
                    if not names:
                        names = [" "]
                    self.all_users = names
                    if self.chat_frame:
                        self.chat_frame.update_user_list(names)

                elif len(parts) == 4:
                    try:
                        messages = json.loads(parts[0])
                    except Exception:
                        messages = []
                    if self.chat_frame:
                        for line in messages:
                            val = line[0] if isinstance(line, (list, tuple)) else str(line)
                            self.chat_frame.append_group(str(val))

            except Exception:
                continue

    # ---- actions chat ----
    def send_direct_message(self, text: str, target: str):
        if not text.strip() or target.strip() == "":
            return
        self.client.send(f"{text}/{target}")

    def send_group_text(self, text: str):
        if not text.strip():
            return
        self.client.send(text)

    def request_history(self):
        self.client.send("Historique")

    def clear_group_area(self):
        if self.chat_frame:
            self.chat_frame.clear_group_area()

    def refresh_users(self):
        self.client.send("list/new/list")

    def create_group(self):
        if self.username not in self.group_buffer:
            self.group_buffer.insert(0, self.username)
        if len(self.group_buffer) < 2:
            messagebox.showinfo("Groupe", "Ajoute au moins un membre.")
            return
        group_json = json.dumps(self.group_buffer)
        self.client.send(f"{group_json}@addgroup")
        self.group_buffer = [self.username]

    def add_members_to_group(self):
        if not self.group_add_buffer:
            messagebox.showinfo("Groupe", "Aucun membre à ajouter.")
            return
        group_json = json.dumps(self.group_add_buffer)
        self.client.send(f"{group_json}@addgroup@new")
        self.group_add_buffer.clear()

    def change_username(self, new_name: str):
        if not new_name.strip():
            return
        old = self.username
        self.username = new_name.strip()
        self.client.send(f"{self.username}!changerlenom")
        if self.chat_frame:
            self.chat_frame.set_profile_name(self.username)
        if self.username not in self.group_buffer:
            self.group_buffer.insert(0, self.username)

    # ---- sortie ----
    def logout(self):
        if messagebox.askyesno("Déconnexion", "Voulez-vous vous déconnecter ?"):
            self.stop_recv.set()
            try:
                self.client.detach()
            except Exception:
                pass
            self.show_signin()

    def on_closing(self):
        self.stop_recv.set()
        try:
            self.client.close()
        except Exception:
            pass
        self.destroy()

# ---------- Écrans ----------
class SignInFrame(ctk.CTkFrame):
    def __init__(self, master: ModernChatApp, on_signin, on_switch_signup):
        super().__init__(master)
        self.on_signin = on_signin
        self.on_switch_signup = on_switch_signup

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=2)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(self, corner_radius=16)
        left.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(24, 12), pady=24)
        left.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="Instant Messaging", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(24, 8))
        ctk.CTkLabel(left, text="Connecte-toi pour discuter", font=ctk.CTkFont(size=14)).pack()

        right = ctk.CTkFrame(self, corner_radius=16)
        right.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=(12, 24), pady=24)
        right.grid_columnconfigure(0, weight=1)

        self.username = ctk.CTkEntry(right, placeholder_text="User name", height=44)
        self.username.grid(row=0, column=0, padx=24, pady=(48, 12), sticky="ew")

        self.password = ctk.CTkEntry(right, placeholder_text="Password", show="•", height=44)
        self.password.grid(row=1, column=0, padx=24, pady=12, sticky="ew")

        ctk.CTkButton(right, text="Se connecter", height=44, command=self._do_signin)\
            .grid(row=2, column=0, padx=24, pady=(12, 6), sticky="ew")

        ctk.CTkButton(right, text="Sign up", height=40, fg_color="transparent", border_width=1,
                      command=self.on_switch_signup)\
            .grid(row=3, column=0, padx=24, pady=(6, 24), sticky="ew")

        self.username.bind("<Return>", lambda e: self._do_signin())
        self.password.bind("<Return>", lambda e: self._do_signin())

    def _do_signin(self):
        self.on_signin(self.username.get().strip(), self.password.get().strip())

class SignUpFrame(ctk.CTkFrame):
    def __init__(self, master: ModernChatApp, on_signup, on_switch_signin):
        super().__init__(master)
        self.on_signup = on_signup
        self.on_switch_signin = on_switch_signin

        self.grid_columnconfigure(0, weight=1)
        card = ctk.CTkFrame(self, corner_radius=16)
        card.grid(row=0, column=0, padx=24, pady=24, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="Authentification", font=ctk.CTkFont(size=22, weight="bold"))\
            .grid(row=0, column=0, pady=(24, 12))

        self.username = ctk.CTkEntry(card, placeholder_text="User name", height=44)
        self.username.grid(row=1, column=0, padx=24, pady=8, sticky="ew")

        self.email = ctk.CTkEntry(card, placeholder_text="Email", height=44)
        self.email.grid(row=2, column=0, padx=24, pady=8, sticky="ew")

        self.password = ctk.CTkEntry(card, placeholder_text="Password", show="•", height=44)
        self.password.grid(row=3, column=0, padx=24, pady=8, sticky="ew")

        self.password2 = ctk.CTkEntry(card, placeholder_text="Password confirmation", show="•", height=44)
        self.password2.grid(row=4, column=0, padx=24, pady=8, sticky="ew")

        ctk.CTkButton(card, text="Enregistrer", height=44, command=self._do_signup)\
            .grid(row=5, column=0, padx=24, pady=(12, 6), sticky="ew")

        ctk.CTkButton(card, text="Sign in", height=40, fg_color="transparent", border_width=1,
                      command=self.on_switch_signin)\
            .grid(row=6, column=0, padx=24, pady=(6, 24), sticky="ew")

        for w in (self.username, self.email, self.password, self.password2):
            w.bind("<Return>", lambda e: self._do_signup())

    def _do_signup(self):
        self.on_signup(self.username.get().strip(),
                       self.email.get().strip(),
                       self.password.get().strip(),
                       self.password2.get().strip())

class ChatFrame(ctk.CTkFrame):
    def __init__(self, master: ModernChatApp,
                 on_send_direct, on_send_group_text, on_request_history,
                 on_logout, on_clear_chat, on_create_group, on_add_members,
                 on_refresh_users, on_change_name):
        super().__init__(master)
        self.master_app = master
        self.on_send_direct = on_send_direct
        self.on_send_group_text = on_send_group_text
        self.on_request_history = on_request_history
        self.on_logout = on_logout
        self.on_clear_chat = on_clear_chat
        self.on_create_group = on_create_group
        self.on_add_members = on_add_members
        self.on_refresh_users = on_refresh_users
        self.on_change_name = on_change_name

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Top bar
        topbar = ctk.CTkFrame(self, height=56, corner_radius=0)
        topbar.grid(row=0, column=0, columnspan=3, sticky="nsew")
        topbar.grid_columnconfigure(3, weight=1)
        self.profile_label = ctk.CTkLabel(topbar, text=f"Connecté: {self.master_app.username}",
                                          font=ctk.CTkFont(size=14, weight="bold"))
        self.profile_label.grid(row=0, column=0, padx=16)
        ctk.CTkButton(topbar, text="Actualiser", command=self.on_refresh_users, height=36, width=110)\
            .grid(row=0, column=1, padx=8, pady=10)
        ctk.CTkButton(topbar, text="Déconnexion", command=self.on_logout, height=36, width=110)\
            .grid(row=0, column=2, padx=8, pady=10)

        # Panneau gauche (Messages + DM)
        left = ctk.CTkFrame(self, corner_radius=12)
        left.grid(row=1, column=0, padx=16, pady=(12, 16), sticky="nsew")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Messages", font=ctk.CTkFont(size=16, weight="bold"))\
            .grid(row=0, column=0, padx=12, pady=(12, 0), sticky="w")

        self.global_text = ctk.CTkTextbox(left)
        self.global_text.grid(row=1, column=0, padx=12, pady=12, sticky="nsew")
        self.global_text.configure(state="disabled")

        dm_bar = ctk.CTkFrame(left, fg_color="transparent")
        dm_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        dm_bar.grid_columnconfigure(1, weight=1)

        self.dm_target = ctk.CTkOptionMenu(dm_bar, values=self.master_app.all_users or [" "], width=180)
        self.dm_target.grid(row=0, column=0, padx=(0, 8))
        self.dm_entry = ctk.CTkEntry(dm_bar, placeholder_text="Message direct...", height=40)
        self.dm_entry.grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(dm_bar, text="Envoyer", command=lambda: self._send_dm())\
            .grid(row=0, column=2, padx=8)
        self.dm_entry.bind("<Return>", lambda e: self._send_dm())

        # Panneau central (Groupe)
        center = ctk.CTkFrame(self, corner_radius=12)
        center.grid(row=1, column=1, padx=(0, 16), pady=(12, 16), sticky="nsew")
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        self.group_title = ctk.CTkLabel(center, text="Groupe (Admin)", font=ctk.CTkFont(size=16, weight="bold"))
        self.group_title.grid(row=0, column=0, padx=12, pady=(12, 0), sticky="w")

        self.group_text = ctk.CTkTextbox(center)
        self.group_text.grid(row=1, column=0, padx=12, pady=12, sticky="nsew")
        self.group_text.configure(state="disabled")

        group_bar = ctk.CTkFrame(center, fg_color="transparent")
        group_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        # très important: laisser la colonne 0 prendre toute la largeur
        group_bar.grid_columnconfigure(0, weight=1)
        group_bar.grid_columnconfigure(1, weight=0)
        group_bar.grid_columnconfigure(2, weight=0)
        group_bar.grid_columnconfigure(3, weight=0)

        # >>> L'ENTRY DU GROUPE (bien visible)
        self.group_entry = ctk.CTkEntry(
            group_bar,
            placeholder_text="Message au groupe...",
            height=44,
            width=300,
            border_width=1,
            border_color=("gray70", "gray30"),
            fg_color=("gray95", "gray15"),   # un peu plus clair sur thème dark
            text_color=("black", "white")
        )
        self.group_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.group_entry.bind("<Return>", lambda e: self._send_group())

        ctk.CTkButton(group_bar, text="Envoyer", command=lambda: self._send_group())\
            .grid(row=0, column=2, padx=8)
        # ctk.CTkButton(group_bar, text="Effacer", command=self.on_clear_chat)\
        #     .grid(row=0, column=3, padx=8)

        # Panneau droit (Utilisateurs / Groupe)
        right = ctk.CTkFrame(self, corner_radius=12, width=260)
        right.grid(row=1, column=2, padx=(0, 16), pady=(12, 16), sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="Utilisateurs", font=ctk.CTkFont(size=16, weight="bold"))\
            .grid(row=0, column=0, padx=12, pady=(12, 8), sticky="w")

        self.user_picker = ctk.CTkOptionMenu(right, values=self.master_app.all_users or [" "])
        self.user_picker.grid(row=1, column=0, padx=12, pady=6, sticky="ew")

        ctk.CTkButton(right, text="Ajouter à la sélection",
                      command=self._add_selected_to_group)\
            .grid(row=2, column=0, padx=12, pady=(4, 12), sticky="ew")

        self.sel_list = ctk.CTkTextbox(right, height=110)
        self.sel_list.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.sel_list.configure(state="disabled")

        ctk.CTkButton(right, text="Créer le groupe", command=self.on_create_group)\
            .grid(row=4, column=0, padx=12, pady=(0, 8), sticky="ew")

        ctk.CTkButton(right, text="Ajouter ces membres", command=self.on_add_members)\
            .grid(row=5, column=0, padx=12, pady=(0, 12), sticky="ew")

        ctk.CTkLabel(right, text="Changer de nom", font=ctk.CTkFont(size=14, weight="bold"))\
            .grid(row=6, column=0, padx=12, pady=(8, 6), sticky="w")
        self.rename_entry = ctk.CTkEntry(right, placeholder_text="Nouveau nom")
        self.rename_entry.grid(row=7, column=0, padx=12, pady=(0, 6), sticky="ew")
        ctk.CTkButton(right, text="Appliquer",
                      command=lambda: self.on_change_name(self.rename_entry.get().strip()))\
            .grid(row=8, column=0, padx=12, pady=(0, 12), sticky="ew")

    # --- UI helpers ---
    def update_user_list(self, names):
        if not names:
            names = [" "]
        # picker de droite
        self.user_picker.configure(values=names)
        if names:
            self.user_picker.set(names[0])
        # menu DM
        try:
            self.dm_target.configure(values=names)
            if names:
                self.dm_target.set(names[0])
        except Exception:
            pass

    def ensure_group_mode(self, admin: bool):
        self.group_title.configure(text=f"Groupe ({'Admin' if admin else 'Membre'})")

    def append_global(self, text: str):
        self.global_text.configure(state="normal")
        self.global_text.insert("end", text if text.endswith("\n") else text + "\n")
        self.global_text.see("end")
        self.global_text.configure(state="disabled")

    def append_group(self, text: str):
        self.group_text.configure(state="normal")
        self.group_text.insert("end", text if text.endswith("\n") else text + "\n")
        self.group_text.see("end")
        self.group_text.configure(state="disabled")

    def clear_group_area(self):
        self.group_text.configure(state="normal")
        self.group_text.delete("1.0", "end")
        self.group_text.configure(state="disabled")

    def _send_dm(self):
        target = self.dm_target.get().strip()
        msg = self.dm_entry.get().strip()
        if target and target != " " and msg:
            self.on_send_direct(msg, target)
            self.dm_entry.delete(0, "end")

    def _send_group(self):
        msg = self.group_entry.get().strip()
        if msg:
            self.on_send_group_text(msg)
            self.group_entry.delete(0, "end")

    def _add_selected_to_group(self):
        name = self.user_picker.get().strip()
        if not name or name == " ":
            return
        self.master_app.group_buffer.append(name)
        self.master_app.group_add_buffer.append(name)
        self.sel_list.configure(state="normal")
        self.sel_list.insert("end", f"• {name}\n")
        self.sel_list.configure(state="disabled")

    def set_profile_name(self, new_name: str):
        self.profile_label.configure(text=f"Connecté: {new_name}")

# ---------- lancement ----------
if __name__ == "__main__":
    SERVER_HOST = socket.gethostbyname(socket.gethostname())
    SERVER_PORT = 12345

    app = ModernChatApp(SERVER_HOST, SERVER_PORT)
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
