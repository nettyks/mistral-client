"""
Mistral AI — 3 onglets : Chat | Travail | Code
"""

import os, json, threading, subprocess
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from mistralai.client import Mistral

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = Path.home() / ".mistral-client" / "config.json"
CONV_DIR    = Path.home() / ".mistral-client" / "conversations"
SKILLS_DIR  = Path.home() / ".mistral-client" / "skills"

DEFAULT_SKILLS = [
    {"id":"assistant",  "icon":"🤖", "name":"Assistant",    "model":"mistral-large-latest",  "system":"Tu es un assistant intelligent et concis. Réponds en français."},
    {"id":"coder",      "icon":"⌨️",  "name":"Dev",          "model":"codestral-latest",      "system":"Tu es un expert en programmation. Génère du code propre et commenté. Mets toujours le code dans des blocs ```."},
    {"id":"redactor",   "icon":"✍️",  "name":"Rédacteur",    "model":"mistral-large-latest",  "system":"Tu es un expert en rédaction. Écris des textes clairs, structurés et professionnels en français."},
    {"id":"translator", "icon":"🌍", "name":"Traducteur",   "model":"mistral-medium-latest", "system":"Tu es un traducteur expert. Traduis fidèlement les textes en gardant le ton et le style. Demande la langue cible si elle n'est pas précisée."},
    {"id":"analyst",    "icon":"📊", "name":"Analyste",     "model":"mistral-large-latest",  "system":"Tu es un analyste expert. Décompose les problèmes, identifie les tendances et fournis des insights actionnables."},
    {"id":"coach",      "icon":"🎯", "name":"Coach",        "model":"mistral-large-latest",  "system":"Tu es un coach bienveillant et motivant. Aide l'utilisateur à atteindre ses objectifs avec des conseils pratiques."},
]

MODELS = [
    "mistral-large-latest", "mistral-medium-latest", "mistral-small-latest",
    "codestral-latest", "open-mistral-nemo", "open-mixtral-8x22b",
]
LIMITS = {
    "mistral-large-latest":  {"tpm": 50_000,  "tpm_mois": 4_000_000, "rps": 1.00},
    "mistral-medium-latest": {"tpm": 375_000, "tpm_mois": None,      "rps": 0.42},
    "mistral-small-latest":  {"tpm": 50_000,  "tpm_mois": None,      "rps": 0.83},
    "codestral-latest":      {"tpm": 625_000, "tpm_mois": None,      "rps": 2.08},
    "open-mistral-nemo":     {"tpm": 937_500, "tpm_mois": None,      "rps": 0.50},
    "open-mixtral-8x22b":    {"tpm": 50_000,  "tpm_mois": 4_000_000, "rps": 1.00},
}

def load_config():
    try: return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
    except: return {}
def save_config(d):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(d, indent=2))
def list_conversations():
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(CONV_DIR.glob("*.json"), reverse=True)
def load_conv(p): return json.loads(p.read_text())
def load_skills() -> list:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skills = []
    for f in sorted(SKILLS_DIR.glob("*.json")):
        try: skills.append(json.loads(f.read_text()))
        except: pass
    if not skills:
        # Créer les skills par défaut
        for s in DEFAULT_SKILLS:
            (SKILLS_DIR / f"{s['id']}.json").write_text(json.dumps(s, indent=2))
        skills = list(DEFAULT_SKILLS)
    return skills

def save_skill(skill: dict):
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    sid = skill.get("id", skill["name"].lower().replace(" ","_"))
    skill["id"] = sid
    (SKILLS_DIR / f"{sid}.json").write_text(json.dumps(skill, indent=2))

def delete_skill(skill_id: str):
    p = SKILLS_DIR / f"{skill_id}.json"
    if p.exists(): p.unlink()

def fmt(n):
    if n is None: return "∞"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.0f}k"
    return str(n)
def bar_color(p):
    if p < 0.6: return "#2ecc71"
    if p < 0.85: return "#f39c12"
    return "#e74c3c"

def read_file_content(path: str) -> str:
    """Lit un fichier texte et retourne son contenu."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[Erreur lecture {path}: {e}]"

def read_folder_content(folder: str, exts=None) -> str:
    """Lit tous les fichiers texte d'un dossier."""
    exts = exts or {".txt",".md",".py",".js",".ts",".json",".yaml",".yml",".html",".css",".sh"}
    parts = []
    for f in sorted(Path(folder).rglob("*")):
        if f.is_file() and f.suffix.lower() in exts and not any(
            p.startswith(".") for p in f.parts):
            content = read_file_content(str(f))
            parts.append(f"=== {f.relative_to(folder)} ===\n{content}")
    return "\n\n".join(parts) if parts else "[Dossier vide ou aucun fichier compatible]"


class UsageBar(ctk.CTkFrame):
    def __init__(self, parent, label, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text=label, font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w")
        self.lbl = ctk.CTkLabel(top, text="0/∞", font=ctk.CTkFont(size=11), text_color="gray")
        self.lbl.grid(row=0, column=1, sticky="e")
        self.bar = ctk.CTkProgressBar(self, height=10, corner_radius=5)
        self.bar.grid(row=1, column=0, sticky="ew", pady=(3,0))
        self.bar.set(0)
    def update(self, used, limit):
        if not limit:
            self.lbl.configure(text=f"{fmt(used)} / ∞")
            self.bar.set(0); self.bar.configure(progress_color="#555")
        else:
            pct = min(used/limit, 1.0)
            self.lbl.configure(text=f"{fmt(used)} / {fmt(limit)}")
            self.bar.set(pct); self.bar.configure(progress_color=bar_color(pct))


# ════════════════════════════════════════════════════════════════════════
class MistralApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Mistral AI")
        self.geometry("1060x760")
        self.minsize(800, 560)
        self.config_data = load_config()
        # État commun
        self.client = None
        self.usage: dict = {}
        self._conv_buttons = []
        # Chat
        self.chat_history: list = []
        self.chat_file: Path | None = None
        # Travail
        self.work_history: list = []
        self.work_files: list[str] = []         # chemins fichiers/dossiers
        self.work_folder: str | None = None
        # Code
        self.code_proc = None
        self.work_file    = None
        self.code_file    = None
        self.active_skill = None   # skill actif
        self._cancel_stream = threading.Event()  # annuler stream en cours
        self._ssh_client    = None
        self._ssh_channel   = None
        self._ssh_connected = False
        self._ssh_host_str  = ""
        self._build_ui()
        self._refresh_conv_list()

    # ── Layout principal ──────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self._build_sidebar()

        # Zone principale
        self.main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        # Barre d'onglets
        self._build_tabbar()

        # Frames des onglets
        self.tab_chat     = self._build_chat_tab()
        self.tab_travail  = self._build_travail_tab()
        self.tab_code     = self._build_code_tab()
        self.tab_settings = self._build_settings_tab()
        self.tab_skills   = self._build_skills_tab()

        self._switch_tab("chat")

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=210, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(3, weight=1)
        sb.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(sb, text="✦ Mistral",
                     font=ctk.CTkFont(size=20, weight="bold")
        ).grid(row=0, column=0, padx=16, pady=(18,6), sticky="w")

        ctk.CTkButton(sb, text="＋  Nouveau chat", height=34,
                      corner_radius=8, command=self._new_chat,
        ).grid(row=1, column=0, padx=10, pady=(0,4), sticky="ew")

        ctk.CTkButton(sb, text="⚡  Skills", height=30,
                      corner_radius=8,
                      fg_color=("#1e3a5f","#1e3a5f"),
                      hover_color=("#1a4a7a","#1a4a7a"),
                      command=lambda: self._switch_tab("skills"),
        ).grid(row=2, column=0, padx=10, pady=(0,8), sticky="ew")

        ctk.CTkLabel(sb, text="Conversations",
                     font=ctk.CTkFont(size=11), text_color="gray"
        ).grid(row=3, column=0, padx=16, pady=(4,2), sticky="w")

        self.conv_scroll = ctk.CTkScrollableFrame(sb, corner_radius=0, fg_color="transparent")
        self.conv_scroll.grid(row=4, column=0, sticky="nsew", padx=4)
        self.conv_scroll.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(4, weight=1)

        self.skill_indicator = ctk.CTkLabel(
            sb, text="Aucun skill actif",
            font=ctk.CTkFont(size=11), text_color="gray",
            wraplength=180, justify="left"
        )
        self.skill_indicator.grid(row=5, column=0, padx=12, pady=(4,2), sticky="w")

        ctk.CTkButton(sb, text="⚙️  Paramètres", anchor="w", height=32,
                      fg_color="transparent", hover_color=("#2b2b2b","#333"),
                      command=lambda: self._switch_tab("settings"),
        ).grid(row=6, column=0, padx=10, pady=(0,12), sticky="ew")

    def _build_tabbar(self):
        bar = ctk.CTkFrame(self.main, height=44, corner_radius=0,
                           fg_color=("#1a1a1a","#1a1a1a"))
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure((0,1,2,3), weight=1)

        self._tab_btns = {}
        tabs = [("chat","💬  Chat"), ("travail","🗂  Travail"), ("code","⌨️  Code")]
        for col, (key, label) in enumerate(tabs):
            btn = ctk.CTkButton(
                bar, text=label, height=44, corner_radius=0,
                fg_color="transparent", hover_color=("#2a2a2a","#2a2a2a"),
                font=ctk.CTkFont(size=13),
                command=lambda k=key: self._switch_tab(k),
            )
            btn.grid(row=0, column=col, sticky="ew")
            self._tab_btns[key] = btn

    def _switch_tab(self, key):
        # Cacher tous
        for f in [self.tab_chat, self.tab_travail, self.tab_code, self.tab_settings, self.tab_skills]:
            if hasattr(self, f.__class__.__name__) or True:
                try: f.grid_remove()
                except: pass
        # Surbrillance bouton actif
        for k, b in self._tab_btns.items():
            b.configure(fg_color=("#2563eb","#1d4ed8") if k==key else "transparent")
        # Afficher l'onglet
        frame = {"chat": self.tab_chat, "travail": self.tab_travail,
                 "code": self.tab_code, "settings": self.tab_settings,
                 "skills": self.tab_skills}.get(key)
        if frame:
            frame.grid(row=1, column=0, sticky="nsew")
            self.main.grid_rowconfigure(1, weight=1)
            self.main.grid_columnconfigure(0, weight=1)
        self.current_tab = key
        self._refresh_conv_list()


    # ════════════════════════════════════════════════════════════════════
    # ONGLET CHAT
    # ════════════════════════════════════════════════════════════════════

    def _build_chat_tab(self):
        f = ctk.CTkFrame(self.main, corner_radius=0, fg_color="transparent")
        f.grid_rowconfigure(1, weight=1)
        f.grid_columnconfigure(0, weight=1)

        # Barre modèle
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(10,0))
        ctk.CTkLabel(top, text="Modèle :", font=ctk.CTkFont(size=12),
                     text_color="gray").grid(row=0, column=0, padx=(0,8))
        self.chat_model_var = ctk.StringVar(value=self.config_data.get("model", MODELS[0]))
        ctk.CTkOptionMenu(top, values=MODELS, variable=self.chat_model_var,
                          width=210, height=30, font=ctk.CTkFont(size=12),
                          command=self._save_model,
        ).grid(row=0, column=1, sticky="w")

        self.chat_textbox = ctk.CTkTextbox(f, wrap="word", state="disabled",
                                           font=ctk.CTkFont(size=13), corner_radius=12)
        self.chat_textbox.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=16, pady=(8,8))

        # ── Barre détection skill (cachée par défaut) ──────────────────
        self._skill_detect_bar = ctk.CTkFrame(f, corner_radius=10,
            fg_color=("#0f2d0f","#0f2d0f"), border_width=1, border_color="#15803d")
        self._skill_detect_bar.grid_columnconfigure(1, weight=1)
        self._skill_detect_lbl = ctk.CTkLabel(self._skill_detect_bar,
            text="🎯 Skill détecté :", font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#4ade80")
        self._skill_detect_lbl.grid(row=0, column=0, padx=(12,6), pady=8)
        self._skill_detect_name = ctk.CTkLabel(self._skill_detect_bar,
            text="", font=ctk.CTkFont(size=12), text_color="#86efac")
        self._skill_detect_name.grid(row=0, column=1, padx=(0,8), pady=8, sticky="w")
        ctk.CTkButton(self._skill_detect_bar, text="➕ Ajouter à la bibliothèque",
            width=190, height=28, corner_radius=6,
            fg_color="#15803d", hover_color="#166534",
            font=ctk.CTkFont(size=11),
            command=self._import_detected_skill,
        ).grid(row=0, column=2, padx=(0,4), pady=8)
        ctk.CTkButton(self._skill_detect_bar, text="✕", width=28, height=28,
            corner_radius=6, fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=11),
            command=self._hide_skill_detect_bar,
        ).grid(row=0, column=3, padx=(0,8), pady=8)
        self._pending_skill = None
        # Barre cachée au démarrage (grid_remove appelé dynamiquement)


        self.chat_entry = ctk.CTkEntry(f, placeholder_text="Écris ton message…",
                                       font=ctk.CTkFont(size=13), height=44, corner_radius=12)
        self.chat_entry.grid(row=3, column=0, sticky="ew", padx=(16,8), pady=(0,16))
        self.chat_entry.bind("<Return>", lambda e: self._chat_send())

        self.chat_send_btn = ctk.CTkButton(f, text="Envoyer", width=100,
                                           height=44, corner_radius=12,
                                           command=self._chat_send)
        self.chat_send_btn.grid(row=3, column=1, padx=(0,16), pady=(0,16))
        return f

    def _chat_send(self):
        msg = self.chat_entry.get().strip()
        if not msg: return
        key = self._get_api_key()
        if not key:
            self._chat_append("⚠️  Clé API manquante. Va dans Paramètres.\n\n"); return
        self.client = Mistral(api_key=key)
        # Ajouter le message d'abord
        self.chat_history.append({"role":"user","content":msg})
        self._chat_append(f"Tu : {msg}\n\n")
        # Construire messages_to_send avec skill en préfixe (une seule fois)
        messages_to_send = list(self.chat_history)
        if self.active_skill:
            sys_msg = {"role":"user","content":f"[SKILL: {self.active_skill['name']}]\n{self.active_skill['system']}"}
            sys_ack = {"role":"assistant","content":"Compris, je suis prêt."}
            messages_to_send = [sys_msg, sys_ack] + messages_to_send
        self.chat_entry.delete(0,"end")
        self.chat_send_btn.configure(state="disabled", text="…")
        # Capturer les références au moment du lancement pour éviter la race condition
        # Connexion SSH directe si le message contient les infos
        _parsed = self._parse_ssh_from_msg(msg)
        if _parsed:
            self._chat_append(
                f"🔌 Connexion SSH vers {_parsed['user']}@{_parsed['host']}:{_parsed.get('port',22)}...\n\n"
            )
            self.after(100, lambda p=_parsed: self._auto_ssh_connect(p))
            self.chat_send_btn.configure(state="normal", text="Envoyer")
            return
        self._cancel_stream.clear()
        current_textbox = self.chat_textbox
        current_history = self.chat_history
        threading.Thread(
            target=self._chat_stream,
            args=(messages_to_send, current_textbox, current_history),
            daemon=True).start()

    def _chat_stream(self, messages, textbox, history):
        model = self.active_skill["model"] if self.active_skill else self.chat_model_var.get()
        def append(t):
            textbox.configure(state="normal")
            textbox.insert("end", t)
            textbox.see("end")
            textbox.configure(state="disabled")
        try:
            stream = self.client.chat.stream(model=model, messages=messages)
            append("Mistral : ")
            full = ""
            for chunk in stream:
                if self._cancel_stream.is_set():
                    append("\n[arrêté]\n\n")
                    return
                d = chunk.data.choices[0].delta.content or ""
                full += d; append(d)
            append("\n\n")
            history.append({"role":"assistant","content":full})
            u = self._get_usage(model)
            u["tokens"] = sum(len(m["content"]) for m in history) // 4
            u["requests"] += 1
            self._autosave_chat()
            self._check_skill_in_response(full)
        except Exception as e:
            if not self._cancel_stream.is_set():
                append(f"\n⚠️  {e}\n\n")
        finally:
            self.chat_send_btn.configure(state="normal", text="Envoyer")


    def _check_skill_in_response(self, text: str):
        """Cherche un bloc ssh-connect ou un JSON de skill dans la réponse."""
        import re as _re, json as _json

        # ── Détection connexion SSH automatique ──────────────────────────
        m = _re.search(r"```ssh-connect\s*(\{.*?\})\s*```", text, _re.DOTALL)
        if m:
            try:
                params = _json.loads(m.group(1))
                if "host" in params and "user" in params:
                    self.after(0, lambda p=params: self._auto_ssh_connect(p))
                    return
            except Exception:
                pass

        # ── Détection skill JSON ──────────────────────────────────────────
        candidates = _re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.DOTALL)
        if not candidates:
            candidates = _re.findall(r"(\{[^{}]{30,}\})", text, _re.DOTALL)
        for raw in candidates:
            try:
                d = _json.loads(raw)
                if isinstance(d, dict) and "name" in d and "system" in d:
                    self._pending_skill = d
                    self.after(0, lambda s=d: self._show_skill_detect_bar(s))
                    return
            except Exception:
                pass



    def _parse_ssh_from_msg(self, text: str) -> dict:
        """
        Parse les infos SSH depuis un message naturel.
        Reconnaît : user@host, host X user Y, mdp/password Z, port N
        Retourne dict ou None si pas d'intention SSH détectée.
        """
        import re
        t = text.lower()

        # Intention SSH ?
        ssh_kws = ["ssh", "connecte", "connexion ssh", "connect to"]
        if not any(k in t for k in ssh_kws):
            return None

        result = {}

        # Format user@host[:port]
        m = re.search(r'([\w.-]+)@([\w.-]+(?:\.[\w]+)+|(?:\d{1,3}\.){3}\d{1,3})(?::(\d+))?', text)
        if m:
            result["user"] = m.group(1)
            result["host"] = m.group(2)
            if m.group(3):
                result["port"] = int(m.group(3))
        else:
            # IP ou hostname seul
            mh = re.search(r'(?:^|\s)((?:\d{1,3}\.){3}\d{1,3}|[\w-]+\.[\w.-]+)(?:\s|$)', text)
            if mh:
                result["host"] = mh.group(1).strip()
            # user
            mu = re.search(r'\buser(?:name)?\s+([\w.-]+)', t)
            if mu:
                result["user"] = text.split()[
                    len(t[:mu.start()].split()) + 1
                ] if False else re.search(r'\buser(?:name)?\s+([\w.-]+)', text, re.IGNORECASE).group(1)

        # Port explicite
        mp = re.search(r'\bport\s+(\d{2,5})', t)
        if mp and "port" not in result:
            result["port"] = int(mp.group(1))

        # Password
        mpw = re.search(
            r'(?:mot\s+de\s+passe|password|mdp|pass(?:word)?)\s*[:\s]\s*(\S+)',
            t
        )
        if mpw:
            # Récupérer la valeur dans le texte original (casse préservée)
            idx = mpw.start(1)
            result["password"] = text[idx:idx+len(mpw.group(1))]

        # Clé SSH
        mk = re.search(r'(?:cl[ée]|key)\s*[:\s]\s*(\S+)', text, re.IGNORECASE)
        if mk:
            result["key"] = mk.group(1)

        # Valide seulement si host + user trouvés
        if "host" in result and "user" in result:
            result.setdefault("port", 22)
            return result
        return None

    def _auto_ssh_connect(self, params: dict):
        """Remplit les champs SSH et lance la connexion depuis la réponse IA."""
        host     = params.get("host", "")
        user     = params.get("user", "")
        port     = str(params.get("port", 22))
        password = params.get("password", "")

        def fill(entry, val):
            entry.delete(0, "end")
            if val:
                entry.insert(0, val)

        # Remplir champs Code tab
        fill(self.ssh_host, host)
        fill(self.ssh_user, user)
        fill(self.ssh_port, port)
        fill(self.ssh_pass, password)

        # Remplir champs Travail tab
        fill(self.work_ssh_host, host)
        fill(self.work_ssh_user, user)
        fill(self.work_ssh_port, port)
        fill(self.work_ssh_pass, password)

        if self._ssh_connected:
            self._chat_append("SSH deja connecte. Deconnecte d abord pour changer de serveur.\n\n")
            return

        self._chat_append(f"Connexion SSH vers {user}@{host}:{port}...\n\n")
        threading.Thread(target=self._ssh_connect, daemon=True).start()

    def _show_skill_detect_bar(self, skill: dict):
        name = skill.get("name", "Sans nom")
        icon = skill.get("icon", "🤖")
        self._skill_detect_name.configure(text=f"{icon}  {name}")
        self._skill_detect_bar.grid(row=2, column=0, columnspan=2,
            sticky="ew", padx=16, pady=(0,4))

    def _hide_skill_detect_bar(self):
        self._skill_detect_bar.grid_remove()
        self._pending_skill = None

    def _import_detected_skill(self):
        if not self._pending_skill:
            return
        skill = dict(self._pending_skill)
        if "model" not in skill:
            skill["model"] = "mistral-large-latest"
        if "icon" not in skill:
            skill["icon"] = "🤖"
        save_skill(skill)
        self._refresh_skills_grid()
        self._hide_skill_detect_bar()
        self._chat_append(f"✅ Skill «{skill['name']}» ajouté à la bibliothèque !\n\n")

    def _chat_append(self, t):
        self.chat_textbox.configure(state="normal")
        self.chat_textbox.insert("end", t)
        self.chat_textbox.see("end")
        self.chat_textbox.configure(state="disabled")

    def _new_chat(self):
        self.chat_history = []; self.chat_file = None
        self.chat_textbox.configure(state="normal")
        self.chat_textbox.delete("1.0","end")
        self.chat_textbox.configure(state="disabled")
        self.title("Mistral AI")
        self._switch_tab("chat")

    def _autosave_work(self):
        if not self.work_history: return
        CONV_DIR.mkdir(parents=True, exist_ok=True)
        title = next((m["content"][:40] for m in self.work_history if m["role"]=="user"), "Sans titre")
        if not hasattr(self, "work_file") or self.work_file is None:
            self.work_file = CONV_DIR / f"work_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            self.after(0, self._refresh_conv_list)
        sys_prompt = self.work_system.get("1.0","end").strip() if hasattr(self,"work_system") else ""
        self.work_file.write_text(json.dumps({"title":title,"messages":self.work_history,"tab":"travail","files":self.work_files,"system":sys_prompt}, indent=2))
        self.after(0, self._refresh_conv_list)

    def _autosave_code(self):
        if not self.code_chat_history: return
        CONV_DIR.mkdir(parents=True, exist_ok=True)
        title = next((m["content"][:40] for m in self.code_chat_history if m["role"]=="user"), "Sans titre")
        if not hasattr(self, "code_file") or self.code_file is None:
            self.code_file = CONV_DIR / f"code_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            self.after(0, self._refresh_conv_list)
        self.code_file.write_text(json.dumps({"title":title,"messages":self.code_chat_history,"tab":"code"}, indent=2))
        self.after(0, self._refresh_conv_list)

    def _autosave_chat(self):
        if not self.chat_history: return
        CONV_DIR.mkdir(parents=True, exist_ok=True)
        title = next((m["content"][:40] for m in self.chat_history if m["role"]=="user"), "Sans titre")
        if self.chat_file is None:
            self.chat_file = CONV_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            self.after(0, self._refresh_conv_list)
        self.chat_file.write_text(json.dumps({"title":title,"messages":self.chat_history,"tab":"chat"}, indent=2))
        self.after(0, self._refresh_conv_list)

    def _refresh_conv_list(self):
        for b in self._conv_buttons: b.destroy()
        self._conv_buttons = []
        active_tab = getattr(self, "current_tab", "chat")
        for path in list_conversations():
            try:
                data  = load_conv(path)
                tab   = data.get("tab", "chat")
                title = data.get("title", path.stem)[:32]
            except:
                tab = "chat"; title = path.stem[:32]
            if tab != active_tab: continue
            is_cur = (path == self.chat_file)
            btn = ctk.CTkButton(
                self.conv_scroll, text=("● " if is_cur else "") + title,
                anchor="w", height=30, corner_radius=6,
                fg_color=("#1a5f9e","#1a4a7a") if is_cur else "transparent",
                hover_color=("#2b2b2b","#333"), font=ctk.CTkFont(size=12),
                command=lambda p=path: self._load_chat_conv(p),
            )
            btn.grid(sticky="ew", pady=1); self._conv_buttons.append(btn)

    def _load_chat_conv(self, path):
        self._cancel_stream.set()  # annuler tout stream en cours
        try: data = load_conv(path)
        except Exception as e: self._chat_append(f"⚠️ {e}\n\n"); return
        tab = data.get("tab", "chat")
        messages = data.get("messages", [])

        if tab == "chat":
            self.chat_history = messages; self.chat_file = path
            box = self.chat_textbox
        elif tab == "travail":
            self.work_history = messages; self.work_file = path
            box = self.work_textbox
        else:
            self.code_chat_history = messages; self.code_file = path
            box = self.code_chat_box

        box.configure(state="normal")
        box.delete("1.0","end")
        for m in messages:
            if m["role"]=="user": box.insert("end", f"Tu : {m['content']}\n\n")
            elif m["role"]=="assistant": box.insert("end", f"Mistral : {m['content']}\n\n")
        box.see("end")
        box.configure(state="disabled")

        # Restaurer fichiers et instruction pour l'onglet Travail
        if tab == "travail":
            saved_files = data.get("files", [])
            saved_system = data.get("system", "")
            self.work_files = [f for f in saved_files if Path(f).exists()]
            self._update_work_files_label()
            if saved_system and hasattr(self, "work_system"):
                self.work_system.configure(state="normal")
                self.work_system.delete("1.0", "end")
                self.work_system.insert("1.0", saved_system)

        # Restaurer _last_code_response depuis le dernier message assistant
        if tab == "code":
            last_assistant = next(
                (m["content"] for m in reversed(messages) if m["role"] == "assistant"), "")
            self._last_code_response = last_assistant
            if "```" in last_assistant:
                self.code_inject_btn.configure(
                    state="normal",
                    text="⬅  Injecter dans l'éditeur",
                    fg_color="#7c3aed",
                )
            else:
                self.code_inject_btn.configure(state="disabled")

        self._switch_tab(tab)


    # ════════════════════════════════════════════════════════════════════
    # ONGLET TRAVAIL
    # ════════════════════════════════════════════════════════════════════

    def _build_travail_tab(self):
        f = ctk.CTkFrame(self.main, corner_radius=0, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(2, weight=1)

        # ── Panneau haut : instruction + fichiers ──────────────────────
        top = ctk.CTkFrame(f, corner_radius=10)
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(12,6))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text="📋  Instruction globale",
                     font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(12,4), sticky="w")
        ctk.CTkLabel(top, text="Le modèle lit cette instruction avant chaque échange.",
                     font=ctk.CTkFont(size=11), text_color="gray",
        ).grid(row=1, column=0, padx=16, pady=(0,6), sticky="w")

        self.work_system = ctk.CTkTextbox(top, height=80,
                                          font=ctk.CTkFont(size=12), corner_radius=8)
        self.work_system.grid(row=2, column=0, padx=16, pady=(0,6), sticky="ew")
        saved_sys = self.config_data.get("work_system", "")
        if saved_sys: self.work_system.insert("1.0", saved_sys)

        # Fichiers/dossier
        file_bar = ctk.CTkFrame(top, fg_color="transparent")
        file_bar.grid(row=3, column=0, padx=16, pady=(0,12), sticky="ew")

        ctk.CTkButton(file_bar, text="＋ Fichiers", width=110, height=30,
                      corner_radius=8, command=self._work_add_files,
        ).grid(row=0, column=0, padx=(0,6))
        ctk.CTkButton(file_bar, text="📁 Dossier", width=110, height=30,
                      corner_radius=8, command=self._work_add_folder,
        ).grid(row=0, column=1, padx=(0,6))
        ctk.CTkButton(file_bar, text="✕ Tout retirer", width=110, height=30,
                      corner_radius=8, fg_color="transparent", border_width=1,
                      command=self._work_clear_files,
        ).grid(row=0, column=2)

        self.work_files_label = ctk.CTkLabel(top, text="Aucun fichier ajouté.",
                                             font=ctk.CTkFont(size=11),
                                             text_color="gray", wraplength=600, justify="left")
        self.work_files_label.grid(row=4, column=0, padx=16, pady=(0,12), sticky="w")

        # Modèle
        mbar = ctk.CTkFrame(f, fg_color="transparent")
        mbar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0,4))
        ctk.CTkLabel(mbar, text="Modèle :", font=ctk.CTkFont(size=12),
                     text_color="gray").grid(row=0, column=0, padx=(0,8))
        self.work_model_var = ctk.StringVar(value=self.config_data.get("model", MODELS[0]))
        ctk.CTkOptionMenu(mbar, values=MODELS, variable=self.work_model_var,
                          width=210, height=30, font=ctk.CTkFont(size=12),
        ).grid(row=0, column=1, sticky="w")

        # Zone de chat travail
        self.work_textbox = ctk.CTkTextbox(f, wrap="word", state="disabled",
                                           font=ctk.CTkFont(size=13), corner_radius=12)
        self.work_textbox.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0,8))

        # ── Barre SSH ─────────────────────────────────────────────
        f.grid_rowconfigure(3, weight=0)
        f.grid_rowconfigure(4, weight=0)

        wssh = ctk.CTkFrame(f, corner_radius=8, fg_color=("#1a1a2e","#1a1a2e"))
        wssh.grid(row=3, column=0, sticky="ew", padx=16, pady=(0,4))
        wssh.grid_columnconfigure(1, weight=1)
        wssh.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(wssh, text="🔌 SSH", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#60a5fa").grid(row=0, column=0, padx=(10,6), pady=6)
        self.work_ssh_host = ctk.CTkEntry(wssh, width=130, height=26,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=("#111","#111"), border_width=1, placeholder_text="host / IP")
        self.work_ssh_host.grid(row=0, column=1, padx=(0,2), pady=6, sticky="ew")
        ctk.CTkLabel(wssh, text=":", font=ctk.CTkFont(size=12)).grid(row=0, column=2)
        self.work_ssh_port = ctk.CTkEntry(wssh, width=44, height=26,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=("#111","#111"), border_width=1)
        self.work_ssh_port.insert(0, "22")
        self.work_ssh_port.grid(row=0, column=3, padx=(2,6), pady=6)
        self.work_ssh_user = ctk.CTkEntry(wssh, width=90, height=26,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=("#111","#111"), border_width=1, placeholder_text="user")
        self.work_ssh_user.grid(row=0, column=4, padx=(0,4), pady=6)
        self.work_ssh_pass = ctk.CTkEntry(wssh, width=100, height=26,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=("#111","#111"), border_width=1,
            placeholder_text="mot de passe", show="*")
        self.work_ssh_pass.grid(row=0, column=5, padx=(0,4), pady=6)
        self.work_ssh_key_btn = ctk.CTkButton(wssh, text="🔑 Clé", width=60, height=26,
            corner_radius=6, fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=11), command=self._work_ssh_pick_key)
        self.work_ssh_key_btn.grid(row=0, column=6, padx=(0,4), pady=6)
        self._work_ssh_key_path = None
        self.work_ssh_connect_btn = ctk.CTkButton(wssh, text="Connecter", width=85, height=26,
            corner_radius=6, fg_color="#0369a1", hover_color="#0284c7",
            font=ctk.CTkFont(size=11), command=self._work_ssh_toggle)
        self.work_ssh_connect_btn.grid(row=0, column=7, padx=(0,4), pady=6)
        self.work_ssh_status = ctk.CTkLabel(wssh, text="⚫", font=ctk.CTkFont(size=13))
        self.work_ssh_status.grid(row=0, column=8, padx=(0,10), pady=6)

        # Saisie
        bot = ctk.CTkFrame(f, fg_color="transparent")
        bot.grid(row=4, column=0, sticky="ew", padx=16, pady=(0,16))
        bot.grid_columnconfigure(0, weight=1)
        self.work_entry = ctk.CTkEntry(bot, placeholder_text="Ta question ou ta tâche…",
                                       font=ctk.CTkFont(size=13), height=44, corner_radius=12)
        self.work_entry.grid(row=0, column=0, sticky="ew", padx=(0,8))
        self.work_entry.bind("<Return>", lambda e: self._work_send())
        self.work_send_btn = ctk.CTkButton(bot, text="Envoyer", width=100,
                                           height=44, corner_radius=12,
                                           command=self._work_send)
        self.work_send_btn.grid(row=0, column=1)
        return f


    def _work_ssh_pick_key(self):
        path = filedialog.askopenfilename(
            title="Choisir une clé privée SSH",
            initialdir=str(Path.home() / ".ssh"),
            filetypes=[("Tous les fichiers", "*")]
        )
        if path:
            self._work_ssh_key_path = path
            self.work_ssh_key_btn.configure(
                text=f"🔑 {Path(path).name[:10]}", fg_color="#15803d")
        else:
            self._work_ssh_key_path = None
            self.work_ssh_key_btn.configure(text="🔑 Clé", fg_color="transparent")

    def _work_ssh_toggle(self):
        if self._ssh_connected:
            self._ssh_disconnect_all()
        else:
            threading.Thread(target=self._work_ssh_connect, daemon=True).start()

    def _work_ssh_connect(self):
        """Connexion SSH depuis Travail (partage le même état que Code)."""
        host = self.work_ssh_host.get().strip()
        port_str = self.work_ssh_port.get().strip()
        port = int(port_str) if port_str.isdigit() else 22
        user = self.work_ssh_user.get().strip()
        password = self.work_ssh_pass.get().strip() or None
        key_path = self._work_ssh_key_path

        if not host or not user:
            self._work_append("⚠️  Host et user SSH requis.\n\n"); return

        try:
            import paramiko
        except ImportError:
            self._work_append("📦 Installation de paramiko...\n\n")
            import subprocess as sp
            venv_pip = str(Path.home() / "mistral-client" / "venv" / "bin" / "pip")
            sp.run([venv_pip, "install", "paramiko"], capture_output=True)
            try: import paramiko
            except ImportError:
                self._work_append("❌ Impossible d'installer paramiko.\n\n"); return

        self._work_append(f"🔌 Connexion SSH {user}@{host}:{port}...\n\n")
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs = {"hostname": host, "port": port, "username": user, "timeout": 10}
            if key_path:
                kwargs["key_filename"] = key_path
                if password: kwargs["passphrase"] = password
            elif password: kwargs["password"] = password
            else:          kwargs["look_for_keys"] = True; kwargs["allow_agent"] = True
            try:
                client.connect(**kwargs)
            except Exception as _exc:
                if "encrypted" in str(_exc).lower() or "PasswordRequired" in type(_exc).__name__:
                    _pp = [None]; _done = threading.Event()
                    def _ask_pp():
                        import tkinter.simpledialog as _sd
                        _pp[0] = _sd.askstring("Cle SSH chiffree",
                            "Passphrase de ta cle SSH :", show="*", parent=self)
                        _done.set()
                    self.after(0, _ask_pp)
                    _done.wait(timeout=60)
                    if _pp[0]:
                        kwargs["passphrase"] = _pp[0]
                        client.connect(**kwargs)
                    else:
                        self._work_append("Passphrase annulee.\n\n\n"); return
                else:
                    raise
            channel = client.invoke_shell(width=200, height=50)
            channel.settimeout(0.1)
            self._ssh_client    = client
            self._ssh_channel   = channel
            self._ssh_connected = True
            self._ssh_host_str  = f"{user}@{host}"
            self._update_ssh_ui(connected=True)
            self._work_append(f"✅ Connecté à {user}@{host}\n\n")
            threading.Thread(target=self._ssh_read_loop, daemon=True).start()
        except Exception as e:
            self._work_append(f"❌ Erreur SSH : {e}\n\n")
            self.after(0, lambda: self.work_ssh_status.configure(text="🔴"))

    def _update_ssh_ui(self, connected: bool):
        """Met à jour les indicateurs SSH dans Code ET Travail."""
        if connected:
            self.after(0, lambda: self.ssh_status_lbl.configure(text="🟢"))
            self.after(0, lambda: self.ssh_connect_btn.configure(
                text="Déconnecter", fg_color="#dc2626", hover_color="#b91c1c"))
            lbl = self._ssh_host_str + "$"
            self.after(0, lambda: self.term_prompt_lbl.configure(
                text=lbl, text_color="#f59e0b"))
            self.after(0, lambda: self.work_ssh_status.configure(text="🟢"))
            self.after(0, lambda: self.work_ssh_connect_btn.configure(
                text="Déconnecter", fg_color="#dc2626", hover_color="#b91c1c"))
        else:
            self.after(0, lambda: self.ssh_status_lbl.configure(text="⚫"))
            self.after(0, lambda: self.ssh_connect_btn.configure(
                text="Connecter", fg_color="#0369a1", hover_color="#0284c7"))
            self.after(0, lambda: self.term_prompt_lbl.configure(
                text="$", text_color="#4ade80"))
            self.after(0, lambda: self.work_ssh_status.configure(text="⚫"))
            self.after(0, lambda: self.work_ssh_connect_btn.configure(
                text="Connecter", fg_color="#0369a1", hover_color="#0284c7"))

    def _ssh_disconnect_all(self):
        """Déconnecte SSH et met à jour les deux onglets."""
        self._ssh_connected = False
        try:
            if self._ssh_channel: self._ssh_channel.close()
            if self._ssh_client:  self._ssh_client.close()
        except: pass
        self._ssh_channel = None
        self._ssh_client  = None
        self._update_ssh_ui(connected=False)

    def _work_add_files(self):
        paths = filedialog.askopenfilenames(title="Choisir des fichiers")
        for p in paths:
            if p not in self.work_files: self.work_files.append(p)
        self._update_work_files_label()

    def _work_add_folder(self):
        folder = filedialog.askdirectory(title="Choisir un dossier")
        if folder and folder not in self.work_files:
            self.work_files.append(folder)
        self._update_work_files_label()

    def _work_clear_files(self):
        self.work_files = []; self._update_work_files_label()

    def _update_work_files_label(self):
        if not self.work_files:
            self.work_files_label.configure(text="Aucun fichier ajouté.")
        else:
            names = [Path(p).name for p in self.work_files]
            self.work_files_label.configure(text="📎 " + " · ".join(names))

    def _build_work_context(self) -> str:
        """Construit le contexte : instruction + contenus fichiers."""
        parts = []
        sys_prompt = self.work_system.get("1.0","end").strip()
        if sys_prompt:
            parts.append(f"=== INSTRUCTION GLOBALE ===\n{sys_prompt}")
        for p in self.work_files:
            path = Path(p)
            if path.is_dir():
                content = read_folder_content(str(path))
                parts.append(f"=== DOSSIER : {path.name} ===\n{content}")
            else:
                content = read_file_content(str(path))
                parts.append(f"=== FICHIER : {path.name} ===\n{content}")
        return "\n\n".join(parts) if parts else ""

    def _work_send(self):
        msg = self.work_entry.get().strip()
        if not msg: return
        key = self._get_api_key()
        if not key:
            self._work_append("⚠️  Clé API manquante. Va dans Paramètres.\n\n"); return
        self.client = Mistral(api_key=key)
        # Construire les messages avec contexte en system
        context = self._build_work_context()
        if self._ssh_connected and self._ssh_host_str:
            ssh_note = f"[SERVEUR SSH ACTIF : {self._ssh_host_str}] Tu as accès à ce serveur via SSH. Suggère des commandes shell si utile."
            context = (context + "\n\n" + ssh_note).strip() if context else ssh_note
        messages = []
        if context:
            messages.append({"role":"user","content": f"[CONTEXTE]\n{context}"})
            messages.append({"role":"assistant","content":"Contexte bien reçu. Je suis prêt."})
        messages += self.work_history
        messages.append({"role":"user","content":msg})
        self.work_history.append({"role":"user","content":msg})
        self._work_append(f"Tu : {msg}\n\n")
        self.work_entry.delete(0,"end")
        self.work_send_btn.configure(state="disabled", text="…")
        # Sauvegarder l'instruction
        self.config_data["work_system"] = self.work_system.get("1.0","end").strip()
        save_config(self.config_data)
        _parsed = self._parse_ssh_from_msg(msg)
        if _parsed:
            self._work_append(
                f"🔌 Connexion SSH vers {_parsed['user']}@{_parsed['host']}:{_parsed.get('port',22)}...\n\n"
            )
            self.after(100, lambda p=_parsed: self._auto_ssh_connect(p))
            self.work_send_btn.configure(state="normal", text="Envoyer")
            return
        self._cancel_stream.clear()
        current_work_box = self.work_textbox
        current_work_hist = self.work_history
        threading.Thread(
            target=self._work_stream,
            args=(messages, current_work_box, current_work_hist),
            daemon=True).start()

    def _work_stream(self, messages, textbox, history):
        model = self.work_model_var.get()
        def append(t):
            textbox.configure(state="normal")
            textbox.insert("end", t)
            textbox.see("end")
            textbox.configure(state="disabled")
        try:
            stream = self.client.chat.stream(model=model, messages=messages)
            append("Mistral : ")
            full = ""
            for chunk in stream:
                if self._cancel_stream.is_set():
                    append("\n[arrêté]\n\n")
                    return
                d = chunk.data.choices[0].delta.content or ""
                full += d; append(d)
            append("\n\n")
            history.append({"role":"assistant","content":full})
            self._autosave_work()
        except Exception as e:
            if not self._cancel_stream.is_set():
                append(f"\n⚠️  {e}\n\n")
        finally:
            self.work_send_btn.configure(state="normal", text="Envoyer")

    def _work_append(self, t):
        self.work_textbox.configure(state="normal")
        self.work_textbox.insert("end", t)
        self.work_textbox.see("end")
        self.work_textbox.configure(state="disabled")


    # ════════════════════════════════════════════════════════════════════
    # ONGLET CODE — split : éditeur+terminal | chat IA
    # ════════════════════════════════════════════════════════════════════

    def _build_code_tab(self):
        f = ctk.CTkFrame(self.main, corner_radius=0, fg_color="transparent")
        f.grid_columnconfigure(0, weight=3)
        f.grid_columnconfigure(1, weight=2)
        f.grid_rowconfigure(0, weight=1)

        # ── COLONNE GAUCHE : éditeur + terminal ──────────────────────
        left = ctk.CTkFrame(f, corner_radius=0, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(12,4), pady=12)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=3)
        left.grid_rowconfigure(2, weight=1)

        ed_frame = ctk.CTkFrame(left, corner_radius=10)
        ed_frame.grid(row=0, column=0, sticky="nsew", pady=(0,4))
        ed_frame.grid_rowconfigure(1, weight=1)
        ed_frame.grid_columnconfigure(0, weight=1)

        ed_bar = ctk.CTkFrame(ed_frame, fg_color="transparent")
        ed_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(8,4))
        ed_bar.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(ed_bar, text="⌨️  Éditeur",
                     font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, padx=(0,12))
        self.code_model_var = ctk.StringVar(value="codestral-latest")
        ctk.CTkOptionMenu(ed_bar, values=MODELS, variable=self.code_model_var,
                          width=170, height=26, font=ctk.CTkFont(size=11),
        ).grid(row=0, column=1, padx=(0,8))
        ctk.CTkButton(ed_bar, text="▶  Exécuter", height=26, width=100,
                      corner_radius=6, fg_color="#16a34a", hover_color="#15803d",
                      command=self._code_run,
        ).grid(row=0, column=3, padx=(0,4))
        ctk.CTkButton(ed_bar, text="⚡ Installer deps", height=26, width=130,
                      corner_radius=6, fg_color="#0369a1", hover_color="#0284c7",
                      command=self._code_install_deps,
        ).grid(row=0, column=4)

        self.code_editor = ctk.CTkTextbox(
            ed_frame, font=ctk.CTkFont(family="Menlo", size=13),
            corner_radius=8, wrap="none")
        self.code_editor.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0,12))
        self.code_editor.insert("1.0", "# Ton code apparaîtra ici\n")

        ctk.CTkLabel(left, text="▼  Terminal",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color="gray",
        ).grid(row=1, column=0, sticky="w", pady=(2,2))

        term_frame = ctk.CTkFrame(left, corner_radius=10, fg_color=("#111","#111"))
        term_frame.grid(row=2, column=0, sticky="nsew")
        term_frame.grid_rowconfigure(0, weight=1)
        term_frame.grid_rowconfigure(1, weight=0)
        term_frame.grid_rowconfigure(2, weight=0)
        term_frame.grid_columnconfigure(0, weight=1)

        self.term_output = ctk.CTkTextbox(
            term_frame, font=ctk.CTkFont(family="Menlo", size=12),
            fg_color=("#111","#111"), text_color="#e5e5e5",
            state="disabled", corner_radius=0)
        self.term_output.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8,0))

        # ── Barre SSH ──────────────────────────────────────────────
        ssh_bar = ctk.CTkFrame(term_frame, fg_color=("#1a1a1a","#1a1a1a"))
        ssh_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=(1,0))
        ssh_bar.grid_columnconfigure(1, weight=1)
        ssh_bar.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(ssh_bar, text="🔌", font=ctk.CTkFont(size=14),
        ).grid(row=0, column=0, padx=(8,4), pady=4)
        self.ssh_host = ctk.CTkEntry(ssh_bar, width=130, height=26,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=("#222","#222"), border_width=1,
            placeholder_text="host / IP")
        self.ssh_host.grid(row=0, column=1, padx=(0,2), pady=4, sticky="ew")
        ctk.CTkLabel(ssh_bar, text=":", font=ctk.CTkFont(size=12)).grid(row=0, column=2)
        self.ssh_port = ctk.CTkEntry(ssh_bar, width=44, height=26,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=("#222","#222"), border_width=1)
        self.ssh_port.insert(0, "22")
        self.ssh_port.grid(row=0, column=3, padx=(2,4), pady=4)
        self.ssh_user = ctk.CTkEntry(ssh_bar, width=90, height=26,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=("#222","#222"), border_width=1,
            placeholder_text="user")
        self.ssh_user.grid(row=0, column=4, padx=(0,4), pady=4)
        self.ssh_pass = ctk.CTkEntry(ssh_bar, width=100, height=26,
            font=ctk.CTkFont(family="Menlo", size=11),
            fg_color=("#222","#222"), border_width=1,
            placeholder_text="mot de passe", show="*")
        self.ssh_pass.grid(row=0, column=5, padx=(0,4), pady=4)
        self.ssh_key_btn = ctk.CTkButton(ssh_bar, text="🔑 Clé", width=60, height=26,
            corner_radius=6, fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=11), command=self._ssh_pick_key)
        self.ssh_key_btn.grid(row=0, column=6, padx=(0,4), pady=4)
        self._ssh_key_path = None
        self.ssh_connect_btn = ctk.CTkButton(ssh_bar, text="Connecter", width=85, height=26,
            corner_radius=6, fg_color="#0369a1", hover_color="#0284c7",
            font=ctk.CTkFont(size=11), command=self._ssh_toggle)
        self.ssh_connect_btn.grid(row=0, column=7, padx=(0,4), pady=4)
        self.ssh_status_lbl = ctk.CTkLabel(ssh_bar, text="⚫", font=ctk.CTkFont(size=13))
        self.ssh_status_lbl.grid(row=0, column=8, padx=(0,8), pady=4)

        # ── Entrée terminal ─────────────────────────────────────────
        tib = ctk.CTkFrame(term_frame, fg_color="transparent")
        tib.grid(row=2, column=0, sticky="ew", padx=8, pady=(4,8))
        tib.grid_columnconfigure(1, weight=1)
        self.term_prompt_lbl = ctk.CTkLabel(tib, text="$",
            font=ctk.CTkFont(family="Menlo", size=13), text_color="#4ade80")
        self.term_prompt_lbl.grid(row=0, column=0, padx=(0,6))
        self.term_entry = ctk.CTkEntry(tib, font=ctk.CTkFont(family="Menlo", size=12),
                                       fg_color=("#1a1a1a","#1a1a1a"), border_width=0,
                                       placeholder_text="commande shell…", height=32)
        self.term_entry.grid(row=0, column=1, sticky="ew")
        self.term_entry.bind("<Return>", lambda e: self._term_run_cmd())
        ctk.CTkButton(tib, text="Entrée", width=65, height=32, corner_radius=6,
                      command=self._term_run_cmd,
        ).grid(row=0, column=2, padx=(6,0))
        ctk.CTkButton(tib, text="Clear", width=60, height=32, corner_radius=6,
                      fg_color="transparent", border_width=1, command=self._term_clear,
        ).grid(row=0, column=3, padx=(4,0))

        # ── COLONNE DROITE : Chat IA ──────────────────────────────────
        right = ctk.CTkFrame(f, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,12), pady=12)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        rh = ctk.CTkFrame(right, fg_color="transparent")
        rh.grid(row=0, column=0, sticky="ew", padx=12, pady=(10,4))
        rh.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(rh, text="✨  Assistant code",
                     font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(rh, text="Décris ce que tu veux créer — le code ira dans l'éditeur",
                     font=ctk.CTkFont(size=11), text_color="gray",
        ).grid(row=1, column=0, sticky="w")

        self.code_chat_box = ctk.CTkTextbox(right, wrap="word", state="disabled",
                                            font=ctk.CTkFont(size=12), corner_radius=8)
        self.code_chat_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4,4))

        self.code_inject_btn = ctk.CTkButton(
            right, text="⬅  Injecter dans l'éditeur", height=30,
            corner_radius=8, fg_color="#7c3aed", hover_color="#6d28d9",
            state="disabled", command=self._code_inject_last,
        )
        self.code_inject_btn.grid(row=2, column=0, padx=12, pady=(0,6), sticky="ew")

        cb = ctk.CTkFrame(right, fg_color="transparent")
        cb.grid(row=3, column=0, sticky="ew", padx=12, pady=(0,12))
        cb.grid_columnconfigure(0, weight=1)
        self.code_chat_entry = ctk.CTkEntry(
            cb, placeholder_text="Ex: crée un script Python qui trie des fichiers…",
            font=ctk.CTkFont(size=12), height=40, corner_radius=10)
        self.code_chat_entry.grid(row=0, column=0, sticky="ew", padx=(0,8))
        self.code_chat_entry.bind("<Return>", lambda e: self._code_chat_send())
        self.code_chat_send_btn = ctk.CTkButton(
            cb, text="→", width=40, height=40, corner_radius=10,
            command=self._code_chat_send)
        self.code_chat_send_btn.grid(row=0, column=1)

        self.code_chat_history = []
        self._last_code_response = ""
        return f

    def _code_chat_send(self):
        msg = self.code_chat_entry.get().strip()
        if not msg: return
        key = self._get_api_key()
        if not key:
            self._code_chat_append("⚠️  Clé API manquante.\n\n"); return

        # Contexte automatique : éditeur + terminal
        parts = [msg]
        current_code = self.code_editor.get("1.0","end").strip()
        if current_code and "Ton code apparaîtra" not in current_code:
            parts.append(f"[Code actuel dans l'éditeur]\n```\n{current_code}\n```")
        terminal_out = self.term_output.get("1.0","end").strip()
        if terminal_out:
            # Garder les 60 dernières lignes max
            lines = terminal_out.split("\n")
            if len(lines) > 60: lines = lines[-60:]
            parts.append(f"[Sortie du terminal]\n{chr(10).join(lines)}")

        content = "\n\n".join(parts)
        self.code_chat_history.append({"role":"user","content":content})
        self._code_chat_append(f"Tu : {msg}\n\n")
        self.code_chat_entry.delete(0,"end")
        self.code_chat_send_btn.configure(state="disabled", text="…")
        self._cancel_stream.clear()
        current_code_box  = self.code_chat_box
        current_code_hist = self.code_chat_history
        threading.Thread(
            target=self._code_chat_stream,
            args=(current_code_box, current_code_hist),
            daemon=True).start()

    def _code_chat_stream(self, textbox, history):
        model = self.code_model_var.get()
        system = [
            {"role":"user","content":
             "Tu es un expert en programmation. Règles OBLIGATOIRES :\n"
             "1. Mets TOUJOURS le code dans un bloc ``` avec le langage indiqué.\n"
             "2. Si le projet nécessite des packages externes, commence par un bloc ```bash avec les commandes d'installation (pip install, npm install, etc.).\n"
             "3. Pour les apps web, précise le port utilisé et la commande pour lancer le serveur.\n"
             "4. Réponds en français sauf pour le code.\n"
             "5. Si tu génères plusieurs fichiers, mets chaque fichier dans un bloc séparé avec un commentaire # === nom_du_fichier ==="},
            {"role":"assistant","content":"Compris, je suis prêt."}
        ]
        def append(t):
            textbox.configure(state="normal")
            textbox.insert("end", t)
            textbox.see("end")
            textbox.configure(state="disabled")
        try:
            client = Mistral(api_key=self._get_api_key())
            stream = client.chat.stream(model=model, messages=system + history)
            append("Mistral : ")
            full = ""
            for chunk in stream:
                if self._cancel_stream.is_set():
                    append("\n[arrêté]\n\n")
                    return
                d = chunk.data.choices[0].delta.content or ""
                full += d; append(d)
            append("\n\n")
            history.append({"role":"assistant","content":full})
            self._last_code_response = full
            self._autosave_code()
            if "```" in full:
                self.after(0, self._mark_inject_ready)
        except Exception as e:
            append(f"\n⚠️  {e}\n\n")
        finally:
            self.code_chat_send_btn.configure(state="normal", text="→")

    def _code_chat_append(self, t):
        self.code_chat_box.configure(state="normal")
        self.code_chat_box.insert("end", t)
        self.code_chat_box.see("end")
        self.code_chat_box.configure(state="disabled")

    def _mark_inject_ready(self):
        self.code_inject_btn.configure(
            state="normal",
            text="⬅  Nouveau code prêt — cliquer pour injecter",
            fg_color="#7c3aed",
        )

    def _code_inject_last(self):
        full = self._last_code_response
        if not full or "```" not in full:
            self._term_print("⚠️  Aucun bloc de code à injecter.\n"); return
        # Extraire TOUS les blocs et prendre le plus long
        parts = full.split("```")
        candidates = []
        for i in range(1, len(parts), 2):
            block = parts[i]
            lines = block.split("\n")
            if lines and lines[0].strip().lower() in (
                    "python","py","js","javascript","bash","sh","ts","typescript",""):
                block = "\n".join(lines[1:])
            candidates.append(block.strip())
        if not candidates:
            self._term_print("⚠️  Impossible d'extraire le code.\n"); return
        best = max(candidates, key=len)
        self.code_editor.delete("1.0","end")
        self.code_editor.insert("1.0", best)
        self._term_print(f"✅ Code injecté ({len(best.splitlines())} lignes).\n")
        self.code_inject_btn.configure(
            text="⬅  Injecter dans l'éditeur",
            fg_color="#7c3aed",
            state="normal",   # reste actif pour ré-injecter si besoin
        )

    def _code_run(self):
        code = self.code_editor.get("1.0","end").strip()
        if not code: return
        lang = "python3"
        if code.startswith("//") or "console.log" in code: lang = "node"
        if code.startswith("#!"): lang = ""
        tmp = Path.home() / ".mistral-client" / "_tmp_code.py"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(code)
        cmd = f"{lang} {tmp}" if lang else str(tmp)
        self._term_print(f"$ {cmd}\n")
        threading.Thread(target=self._run_with_autoinstall, args=(cmd, lang, tmp), daemon=True).start()

    def _run_with_autoinstall(self, cmd, lang, tmp_path):
        """Exécute le code et auto-installe les modules manquants (Python seulement)."""
        import re, subprocess as sp
        venv_pip = str(Path.home() / "mistral-client" / "venv" / "bin" / "pip")
        max_retries = 5
        for attempt in range(max_retries):
            output_lines = []
            try:
                proc = sp.Popen(cmd, shell=True,
                    stdout=sp.PIPE, stderr=sp.STDOUT,
                    text=True, cwd=str(Path.home()))
                for line in proc.stdout:
                    self._term_print(line)
                    output_lines.append(line)
                proc.wait()
                output = "".join(output_lines)
                # Détecter ModuleNotFoundError
                m = re.search(r"ModuleNotFoundError: No module named '([^']+)'", output)
                if m and lang == "python3":
                    pkg = m.group(1).split(".")[0]
                    # Mapping import → package pip
                    pip_map = {
                        "cv2":"opencv-python", "PIL":"Pillow", "sklearn":"scikit-learn",
                        "bs4":"beautifulsoup4", "yaml":"PyYAML", "dotenv":"python-dotenv",
                        "Crypto":"pycryptodome", "gi":"PyGObject", "wx":"wxPython",
                        "serial":"pyserial", "usb":"pyusb",
                    }
                    pip_pkg = pip_map.get(pkg, pkg)
                    self._term_print(f"\n📦 Module '{pkg}' manquant — installation de '{pip_pkg}'...\n")
                    install = sp.run([venv_pip, "install", pip_pkg],
                        capture_output=True, text=True)
                    if install.returncode == 0:
                        self._term_print(f"✅ '{pip_pkg}' installé — relance...\n\n")
                        continue  # retry
                    else:
                        self._term_print(f"❌ Échec installation : {install.stderr}\n")
                        break
                else:
                    self._term_print(f"[Terminé — code {proc.returncode}]\n\n")
                    break
            except Exception as e:
                self._term_print(f"[Erreur : {e}]\n")
                break

    def _code_install_deps(self):
        """Analyse le code de l'éditeur et installe tous les packages externes."""
        import re, subprocess as sp
        code = self.code_editor.get("1.0", "end")
        # Extraire les imports Python
        imports = set()
        for m in re.finditer(r'^(?:import|from)\s+([\w]+)', code, re.MULTILINE):
            imports.add(m.group(1))
        # Stdlib à ignorer
        stdlib = {
            "os","sys","re","json","math","time","datetime","pathlib","typing",
            "collections","itertools","functools","string","random","hashlib",
            "threading","subprocess","shutil","copy","io","abc","enum","dataclasses",
            "logging","argparse","unittest","traceback","inspect","contextlib",
            "base64","struct","socket","http","urllib","email","html","xml",
            "csv","sqlite3","queue","array","heapq","bisect","weakref","gc",
            "platform","signal","tempfile","glob","fnmatch","textwrap","pprint",
            "decimal","fractions","statistics","cmath","numbers","ctypes",
        }
        pip_map = {
            "cv2":"opencv-python", "PIL":"Pillow", "sklearn":"scikit-learn",
            "bs4":"beautifulsoup4", "yaml":"PyYAML", "dotenv":"python-dotenv",
            "Crypto":"pycryptodome", "serial":"pyserial",
            "flask":"flask", "django":"django", "fastapi":"fastapi",
            "uvicorn":"uvicorn", "requests":"requests", "httpx":"httpx",
            "aiohttp":"aiohttp", "sqlalchemy":"SQLAlchemy", "pydantic":"pydantic",
            "numpy":"numpy", "pandas":"pandas", "matplotlib":"matplotlib",
            "seaborn":"seaborn", "plotly":"plotly", "scipy":"scipy",
            "torch":"torch", "tensorflow":"tensorflow", "transformers":"transformers",
            "openai":"openai", "anthropic":"anthropic", "mistralai":"mistralai",
            "paramiko":"paramiko", "cryptography":"cryptography",
            "qrcode":"qrcode", "barcode":"python-barcode",
            "customtkinter":"customtkinter",
        }
        to_install = []
        for imp in imports:
            if imp not in stdlib:
                pkg = pip_map.get(imp, imp)
                to_install.append((imp, pkg))
        if not to_install:
            self._term_print("ℹ️  Aucun package externe détecté.\n"); return
        venv_pip = str(Path.home() / "mistral-client" / "venv" / "bin" / "pip")
        self._term_print(f"📦 Installation de {len(to_install)} package(s)...\n")
        threading.Thread(target=self._install_packages, args=(to_install, venv_pip), daemon=True).start()

    def _install_packages(self, packages, venv_pip):
        import subprocess as sp
        for imp, pkg in packages:
            self._term_print(f"  ➤ pip install {pkg}... ")
            r = sp.run([venv_pip, "install", pkg], capture_output=True, text=True)
            if r.returncode == 0:
                self._term_print("✅\n")
            else:
                self._term_print(f"❌ ({r.stderr.strip()[:80]})\n")
        self._term_print("\n🎉 Installation terminée.\n\n")


    # ════════════════════════════════════════════════════════════════════
    # SSH
    # ════════════════════════════════════════════════════════════════════

    def _ssh_pick_key(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Choisir une clé privée SSH",
            initialdir=str(Path.home() / ".ssh"),
            filetypes=[("Tous les fichiers", "*")]
        )
        if path:
            self._ssh_key_path = path
            name = Path(path).name
            self.ssh_key_btn.configure(text=f"🔑 {name[:10]}", fg_color="#15803d")
        else:
            self._ssh_key_path = None
            self.ssh_key_btn.configure(text="🔑 Clé", fg_color="transparent")

    def _ssh_toggle(self):
        if self._ssh_connected:
            self._ssh_disconnect()
        else:
            threading.Thread(target=self._ssh_connect, daemon=True).start()

    def _ssh_connect(self):
        host = self.ssh_host.get().strip()
        port_str = self.ssh_port.get().strip()
        port = int(port_str) if port_str.isdigit() else 22
        user = self.ssh_user.get().strip()
        password = self.ssh_pass.get().strip() or None
        key_path = self._ssh_key_path

        if not host or not user:
            self._term_print("⚠️  Host et user requis.\n"); return

        try:
            import paramiko
        except ImportError:
            self._term_print("📦 Installation de paramiko...\n")
            import subprocess as sp
            venv_pip = str(Path.home() / "mistral-client" / "venv" / "bin" / "pip")
            sp.run([venv_pip, "install", "paramiko"], capture_output=True)
            try:
                import paramiko
            except ImportError:
                self._term_print("❌ Impossible d'installer paramiko.\n"); return

        self._term_print(f"\n🔌 Connexion SSH {user}@{host}:{port}...\n")
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs = {"hostname": host, "port": port, "username": user, "timeout": 10}
            if key_path:
                kwargs["key_filename"] = key_path
                if password: kwargs["passphrase"] = password
            elif password:
                kwargs["password"] = password
            else:
                kwargs["look_for_keys"] = True
                kwargs["allow_agent"] = True
            try:
                client.connect(**kwargs)
            except Exception as _exc:
                if "encrypted" in str(_exc).lower() or "PasswordRequired" in type(_exc).__name__:
                    _pp = [None]; _done = threading.Event()
                    def _ask_pp():
                        import tkinter.simpledialog as _sd
                        _pp[0] = _sd.askstring("Cle SSH chiffree",
                            "Passphrase de ta cle SSH :", show="*", parent=self)
                        _done.set()
                    self.after(0, _ask_pp)
                    _done.wait(timeout=60)
                    if _pp[0]:
                        kwargs["passphrase"] = _pp[0]
                        client.connect(**kwargs)
                    else:
                        self._term_print("Passphrase annulee.\n\n"); return
                else:
                    raise
            channel = client.invoke_shell(width=200, height=50)
            channel.settimeout(0.1)
            self._ssh_client  = client
            self._ssh_channel = channel
            self._ssh_connected = True
            self._ssh_host_str = f"{user}@{host}"
            self._update_ssh_ui(connected=True)
            self._term_print(f"✅ Connecté à {user}@{host}\n\n")
            threading.Thread(target=self._ssh_read_loop, daemon=True).start()
        except Exception as e:
            self._term_print(f"❌ Erreur SSH : {e}\n")
            self.after(0, lambda: self.ssh_status_lbl.configure(text="🔴"))

    def _ssh_read_loop(self):
        """Lit en continu la sortie du canal SSH."""
        import re
        while self._ssh_connected and self._ssh_channel:
            try:
                data = self._ssh_channel.recv(4096)
                if data:
                    text = data.decode("utf-8", errors="replace")
                    text = re.sub(r'\x1b\[[0-9;]*[mABCDHJKfsu]', '', text)
                    text = re.sub(r'\x1b\[\?[0-9;]*[hl]', '', text)
                    text = re.sub(r'\x1b[=>]', '', text)
                    self._term_print(text)
                elif self._ssh_channel.exit_status_ready():
                    break
            except Exception:
                import time; time.sleep(0.05)
        if self._ssh_connected:
            self._ssh_disconnect()

    def _ssh_disconnect(self):
        self._ssh_disconnect_all()
        self._term_print("\n🔌 SSH déconnecté.\n")

    def _term_run_cmd(self):
        cmd = self.term_entry.get().strip()
        if not cmd: return
        self.term_entry.delete(0,"end")
        if self._ssh_connected and self._ssh_channel:
            self._term_print(f"{cmd}\n")
            try:
                self._ssh_channel.send(cmd + "\n")
            except Exception as e:
                self._term_print(f"\u274c SSH : {e}\n")
                self._ssh_disconnect()
        else:
            self._term_exec(cmd)

    def _term_exec(self, cmd):
        self._term_print(f"$ {cmd}\n")
        threading.Thread(target=self._run_subprocess, args=(cmd,), daemon=True).start()


    def _run_subprocess(self, cmd):
        try:
            proc = subprocess.Popen(cmd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=str(Path.home()))
            for line in proc.stdout:
                self._term_print(line)
            proc.wait()
            self._term_print(f"[Terminé — code {proc.returncode}]\n\n")
        except Exception as e:
            self._term_print(f"[Erreur : {e}]\n")

    def _term_print(self, text):
        self.term_output.configure(state="normal")
        self.term_output.insert("end", text)
        self.term_output.see("end")
        self.term_output.configure(state="disabled")

    def _term_clear(self):
        self.term_output.configure(state="normal")
        self.term_output.delete("1.0","end")
        self.term_output.configure(state="disabled")

    # ════════════════════════════════════════════════════════════════════
    # ONGLET SKILLS
    # ════════════════════════════════════════════════════════════════════

    def _build_skills_tab(self):
        f = ctk.CTkFrame(self.main, corner_radius=0, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        f.grid_columnconfigure(1, weight=1)
        f.grid_rowconfigure(1, weight=1)
        hdr = ctk.CTkFrame(f, fg_color="transparent")
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16,8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="⚡  Skills",
                     font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="＋  Créer un skill", width=140, height=32,
                      corner_radius=8, command=self._skill_create_dialog,
        ).grid(row=0, column=1, sticky="e")
        self.skills_scroll = ctk.CTkScrollableFrame(f, corner_radius=0, fg_color="transparent")
        self.skills_scroll.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=(0,12))
        self.skills_scroll.grid_columnconfigure((0,1), weight=1)
        self._refresh_skills_grid()
        return f

    def _refresh_skills_grid(self):
        for w in self.skills_scroll.winfo_children(): w.destroy()
        skills = load_skills()
        for i, skill in enumerate(skills):
            col = i % 2; row = i // 2
            self._make_skill_card(self.skills_scroll, skill, row, col)

    def _make_skill_card(self, parent, skill, row, col):
        is_active = (self.active_skill and self.active_skill.get("id") == skill.get("id"))
        card = ctk.CTkFrame(parent, corner_radius=12, border_width=2,
                            border_color="#2563eb" if is_active else "#333")
        card.grid(row=row, column=col, padx=8, pady=6, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(12,4))
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text=skill.get("icon","🤖"),
                     font=ctk.CTkFont(size=22)).grid(row=0, column=0, padx=(0,8))
        ctk.CTkLabel(top, text=skill.get("name","?"),
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(card, text=skill.get("model",""),
                     font=ctk.CTkFont(size=11), text_color="gray", anchor="w",
        ).grid(row=1, column=0, padx=14, pady=(0,4), sticky="w")
        preview = skill.get("system","")[:80] + ("…" if len(skill.get("system","")) > 80 else "")
        ctk.CTkLabel(card, text=preview, font=ctk.CTkFont(size=11), text_color="#aaa",
                     wraplength=260, justify="left", anchor="w",
        ).grid(row=2, column=0, padx=14, pady=(0,10), sticky="w")
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", padx=12, pady=(0,10))
        if is_active:
            ctk.CTkButton(btns, text="✓ Actif", width=80, height=28, corner_radius=6,
                          fg_color="#166534", hover_color="#14532d",
                          command=lambda: self._skill_deactivate(),
            ).grid(row=0, column=0, padx=(0,6))
        else:
            ctk.CTkButton(btns, text="▶ Activer", width=80, height=28, corner_radius=6,
                          command=lambda s=skill: self._skill_activate(s),
            ).grid(row=0, column=0, padx=(0,6))
        ctk.CTkButton(btns, text="✏️", width=36, height=28, corner_radius=6,
                      fg_color="transparent", border_width=1,
                      command=lambda s=skill: self._skill_edit_dialog(s),
        ).grid(row=0, column=1, padx=(0,4))
        ctk.CTkButton(btns, text="🗑", width=36, height=28, corner_radius=6,
                      fg_color="transparent", border_width=1,
                      command=lambda s=skill: self._skill_delete(s),
        ).grid(row=0, column=2)

    def _skill_activate(self, skill):
        self.active_skill = skill
        self.chat_model_var.set(skill.get("model", MODELS[0]))
        self.skill_indicator.configure(
            text=f"{skill.get('icon','')} {skill['name']} actif", text_color="#60a5fa")
        self._refresh_skills_grid()
        self._new_chat()
        self._chat_append(f"— Skill «{skill['name']}» activé. Prêt ! —\n\n")

    def _skill_deactivate(self):
        self.active_skill = None
        self.skill_indicator.configure(text="Aucun skill actif", text_color="gray")
        self._refresh_skills_grid()

    def _skill_delete(self, skill):
        delete_skill(skill.get("id",""))
        if self.active_skill and self.active_skill.get("id") == skill.get("id"):
            self._skill_deactivate()
        self._refresh_skills_grid()

    def _skill_create_dialog(self): self._skill_dialog(None)
    def _skill_edit_dialog(self, skill): self._skill_dialog(skill)

    def _skill_dialog(self, skill=None):
        win = ctk.CTkToplevel(self)
        win.title("Créer un skill" if not skill else "Modifier le skill")
        win.geometry("520x500"); win.grab_set()
        win.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(win, text="Icône :").grid(row=0, column=0, padx=24, pady=(20,4), sticky="w")
        e_icon = ctk.CTkEntry(win, width=60)
        e_icon.grid(row=1, column=0, padx=24, pady=(0,10), sticky="w")
        if skill: e_icon.insert(0, skill.get("icon","🤖"))
        ctk.CTkLabel(win, text="Nom :").grid(row=2, column=0, padx=24, pady=(0,4), sticky="w")
        e_name = ctk.CTkEntry(win, width=300)
        e_name.grid(row=3, column=0, padx=24, pady=(0,10), sticky="w")
        if skill: e_name.insert(0, skill.get("name",""))
        ctk.CTkLabel(win, text="Modèle :").grid(row=4, column=0, padx=24, pady=(0,4), sticky="w")
        model_var = ctk.StringVar(value=skill.get("model", MODELS[0]) if skill else MODELS[0])
        ctk.CTkOptionMenu(win, values=MODELS, variable=model_var, width=210,
        ).grid(row=5, column=0, padx=24, pady=(0,10), sticky="w")
        ctk.CTkLabel(win, text="Instruction système :").grid(row=6, column=0, padx=24, pady=(0,4), sticky="w")
        e_sys = ctk.CTkTextbox(win, height=120, font=ctk.CTkFont(size=12))
        e_sys.grid(row=7, column=0, padx=24, pady=(0,16), sticky="ew")
        if skill: e_sys.insert("1.0", skill.get("system",""))
        def save():
            s = {"id": skill["id"] if skill else e_name.get().strip().lower().replace(" ","_"),
                 "icon": e_icon.get().strip() or "🤖",
                 "name": e_name.get().strip() or "Sans nom",
                 "model": model_var.get(),
                 "system": e_sys.get("1.0","end").strip()}
            save_skill(s); self._refresh_skills_grid(); win.destroy()
        ctk.CTkButton(win, text="Sauvegarder", command=save,
        ).grid(row=8, column=0, padx=24, pady=(0,20), sticky="w")

        # ONGLET PARAMÈTRES
    # ════════════════════════════════════════════════════════════════════

    def _build_settings_tab(self):
        f = ctk.CTkScrollableFrame(self.main, corner_radius=0, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(f, text="Paramètres",
                     font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=24, pady=(24,10), sticky="w")

        ctk.CTkLabel(f, text="Clé API Mistral :").grid(row=1, column=0, padx=24, sticky="w")
        self.api_entry = ctk.CTkEntry(f, width=400, show="*", placeholder_text="sk-…")
        self.api_entry.grid(row=2, column=0, padx=24, pady=(4,8), sticky="w")
        saved_key = self.config_data.get("api_key", os.environ.get("MISTRAL_API_KEY",""))
        if saved_key: self.api_entry.insert(0, saved_key)

        ctk.CTkButton(f, text="Sauvegarder", command=self._save_settings,
        ).grid(row=3, column=0, padx=24, pady=(0,4), sticky="w")
        self.settings_status = ctk.CTkLabel(f, text="", text_color="green")
        self.settings_status.grid(row=4, column=0, padx=24, sticky="w")

        # Usage
        hdr = ctk.CTkFrame(f, fg_color="transparent")
        hdr.grid(row=5, column=0, padx=24, pady=(24,8), sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="Utilisation par modèle",
                     font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self.usage_model_var = ctk.StringVar(value=self.config_data.get("model", MODELS[0]))
        ctk.CTkOptionMenu(hdr, values=MODELS, variable=self.usage_model_var,
                          width=190, height=28, font=ctk.CTkFont(size=12),
                          command=lambda v: self._update_usage_display(),
        ).grid(row=0, column=1, padx=(16,0), sticky="e")

        box = ctk.CTkFrame(f, corner_radius=12)
        box.grid(row=6, column=0, padx=24, pady=(0,8), sticky="ew")
        box.grid_columnconfigure(0, weight=1)
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.grid(row=0, column=0, sticky="ew", padx=20, pady=16)
        inner.grid_columnconfigure(0, weight=1)

        self.bar_tpm  = UsageBar(inner, "Tokens / minute (session)")
        self.bar_tpm.grid(row=0, column=0, sticky="ew", pady=(0,14))
        self.bar_mois = UsageBar(inner, "Tokens / mois (session)")
        self.bar_mois.grid(row=1, column=0, sticky="ew", pady=(0,14))

        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.grid(row=2, column=0, sticky="ew")
        info.grid_columnconfigure((0,1,2), weight=1)
        for col, txt in enumerate(["Tokens totaux","Requêtes","Req/sec (limite)"]):
            ctk.CTkLabel(info, text=txt, font=ctk.CTkFont(size=11),
                         text_color="gray").grid(row=0, column=col)
        self.lbl_tokens = ctk.CTkLabel(info, text="0",
                                       font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_tokens.grid(row=1, column=0, pady=(2,0))
        self.lbl_reqs = ctk.CTkLabel(info, text="0",
                                     font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_reqs.grid(row=1, column=1, pady=(2,0))
        self.lbl_rps = ctk.CTkLabel(info, text="—",
                                    font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_rps.grid(row=1, column=2, pady=(2,0))

        ctk.CTkButton(f, text="↺  Réinitialiser ce modèle",
                      width=220, height=30, corner_radius=8,
                      fg_color="transparent", border_width=1,
                      command=self._reset_usage,
        ).grid(row=7, column=0, padx=24, pady=(8,24), sticky="w")
        return f

    def _update_usage_display(self):
        model = self.usage_model_var.get()
        lims  = LIMITS.get(model, {})
        u     = self._get_usage(model)
        self.bar_tpm.update(u["tokens"], lims.get("tpm"))
        self.bar_mois.update(u["tokens"], lims.get("tpm_mois"))
        self.lbl_tokens.configure(text=f"{u['tokens']:,}".replace(",", " "))
        self.lbl_reqs.configure(text=str(u["requests"]))
        rps = lims.get("rps")
        self.lbl_rps.configure(text=f"{rps:.2f}" if rps else "—")

    def _reset_usage(self):
        self.usage[self.usage_model_var.get()] = {"tokens":0,"requests":0}
        self._update_usage_display()

    # ── Utilitaires communs ───────────────────────────────────────────────

    def _get_api_key(self):
        if hasattr(self, "api_entry"): return self.api_entry.get().strip()
        return self.config_data.get("api_key", os.environ.get("MISTRAL_API_KEY",""))

    def _get_usage(self, model):
        if model not in self.usage:
            self.usage[model] = {"tokens":0,"requests":0}
        return self.usage[model]

    def _save_model(self, value):
        self.config_data["model"] = value
        save_config(self.config_data)

    def _save_settings(self):
        self.config_data["api_key"] = self.api_entry.get().strip()
        save_config(self.config_data)
        self.settings_status.configure(text="✓ Clé sauvegardée")
        self.after(2000, lambda: self.settings_status.configure(text=""))


if __name__ == "__main__":
    app = MistralApp()
    app.mainloop()
