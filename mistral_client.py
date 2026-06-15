"""
Client Mistral AI — complet et réutilisable
Prérequis : pip install mistralai
"""

import os
from mistralai import Mistral


class MistralClient:
    """Client Mistral AI avec toutes les fonctionnalités principales."""

    DEFAULT_MODEL = "mistral-large-latest"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Clé API manquante. Passez-la en paramètre ou "
                "définissez la variable d'environnement MISTRAL_API_KEY."
            )
        self.model = model or self.DEFAULT_MODEL
        self._client = Mistral(api_key=self.api_key)

    # ------------------------------------------------------------------
    # Chat completion
    # ------------------------------------------------------------------

    def chat(self, prompt: str, system: str | None = None, **kwargs) -> str:
        """Envoie un message et retourne la réponse en texte."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.complete(
            model=self.model,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content

    def chat_stream(self, prompt: str, system: str | None = None, **kwargs):
        """Envoie un message et retourne un générateur de tokens (streaming)."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        stream = self._client.chat.stream(
            model=self.model,
            messages=messages,
            **kwargs,
        )
        for chunk in stream:
            delta = chunk.data.choices[0].delta.content
            if delta:
                yield delta

    def conversation(self, messages: list[dict], **kwargs) -> str:
        """Envoie un historique de messages complet (multi-turn)."""
        response = self._client.chat.complete(
            model=self.model,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Retourne les embeddings pour une liste de textes."""
        response = self._client.embeddings.create(
            model="mistral-embed",
            inputs=texts,
        )
        return [item.embedding for item in response.data]

    # ------------------------------------------------------------------
    # Modèles disponibles
    # ------------------------------------------------------------------

    def list_models(self) -> list[str]:
        """Retourne la liste des IDs de modèles disponibles."""
        response = self._client.models.list()
        return [m.id for m in response.data]

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def set_model(self, model: str):
        """Change le modèle par défaut du client."""
        self.model = model


# ------------------------------------------------------------------
# Démonstration rapide
# ------------------------------------------------------------------

if __name__ == "__main__":
    client = MistralClient()

    print("=== Modèles disponibles ===")
    for m in client.list_models():
        print(" -", m)

    print("\n=== Chat simple ===")
    reponse = client.chat(
        prompt="Explique-moi le machine learning en 2 phrases.",
        system="Tu es un expert pédagogue qui répond en français.",
    )
    print(reponse)

    print("\n=== Streaming ===")
    for token in client.chat_stream("Raconte-moi une blague courte."):
        print(token, end="", flush=True)
    print()

    print("\n=== Conversation multi-tour ===")
    historique = [
        {"role": "user", "content": "Quel est le capital de la France ?"},
        {"role": "assistant", "content": "Le capital de la France est Paris."},
        {"role": "user", "content": "Et sa population ?"},
    ]
    print(client.conversation(historique))

    print("\n=== Embeddings ===")
    vecteurs = client.embed(["Bonjour le monde", "Hello world"])
    print(f"Dimension : {len(vecteurs[0])} — {len(vecteurs)} vecteurs générés")
