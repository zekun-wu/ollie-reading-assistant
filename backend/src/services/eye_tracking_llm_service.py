"""
Eye-Tracking LLM Service - Separate from Manual Assistance
Handles LLM analysis for curiosity guidance triggered by eye-tracking
Uses different prompts focused on acknowledging active gaze behavior
"""
import logging
import json
import requests
from typing import Dict, Optional, Any, List
from pathlib import Path
import sys

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)

try:
    from config.api_keys import get_api_config
except ImportError as e:
    print(f"❌ Failed to import API config: {e}")
    def get_api_config():
        return None

from services.llm_prompt_logger import emit_llm_prompt

class EyeTrackingLLMService:
    """LLM service for eye-tracking curiosity guidance"""
    
    def __init__(self):
        self.api_config = get_api_config()
        self.base_url = "https://api.openai.com/v1/chat/completions"
        
        # System prompt - non-negotiable rules (never changes between calls)
        self.SYSTEM_PROMPT = """Du bist ein Kinder-Geschichtenerzähler in einem Geschichtenketten-Spiel.

Deine Aufgabe ist es, kurze, fesselnde Geschichtenabschnitte (3-5 Sätze) basierend auf Bildern zu schreiben.
Du kannst die Geschichte an JEDEM Punkt in der Kette übernehmen.
Dein Ziel ist es, das Kind (Alter 3-8) engagiert und zuhörbereit zu halten, unabhängig davon, wann du in die Geschichte einsteigst.

KERNREGELN:
- Jeder Geschichtenabschnitt muss hauptsächlich auf den ZWEI lokalen Bildausschnitten basieren.
- KRITISCH: Der erste Bildausschnitt (hervorgehobener lokaler Ausschnitt) MUSS im Hauptinhalt der Geschichte beschrieben werden. Ignoriere ihn niemals.
- Der zweite Bildausschnitt (naher lokaler Ausschnitt) wird für den Haken verwendet, aber der erste Ausschnitt MUSS den Hauptinhalt der Geschichte bilden.
- Das vollständige Bild dient nur zur Orientierung.
- Geschichten müssen realistisch sein. Keine Magie, keine unmöglichen Ereignisse.
- Geschichten müssen unvollendet bleiben. Löse die Situation niemals vollständig auf.
- Jeder Abschnitt sollte sich wie ein Moment innerhalb eines größeren sich entfaltenden Ereignisses anfühlen.

GESCHICHTEN-SETTING-REGELN:
- Der SITUATION-Kontext definiert das Geschichtensetting und die Weltregeln.
- Deine Geschichte muss sich immer auf Elemente aus diesem Setting beziehen und sie einbeziehen.
- Widerspreche niemals etwas, was im Geschichtensetting steht, oder verletze es.
- Nutze die Setting-Details voll aus—mache sie sichtbar und aktiv in deinem Geschichtenerzählen.
- Das Setting ist nicht nur Hintergrund—es prägt, was passiert und wie Charaktere handeln.

ANFANGSGESCHICHTEN-REGELN (wenn VORGESCHICHTE "NONE" ist):
- Wenn VORGESCHICHTE "NONE" ist, werden dir die Eröffnungssätze aus SITUATION bereitgestellt, die der Anfang der Geschichte sein werden.
- Setze die Geschichte von diesen Eröffnungssätzen fort und zeige, wie sich die Geschichte basierend auf dem Kontext entfaltet.
- KRITISCH: Beschreibe BEIDE Bildausschnitte in deiner Geschichte:
  * Der erste Ausschnitt (hervorgehobener lokaler Ausschnitt) MUSS den Hauptinhalt der Geschichte bilden - beschreibe, was dort sichtbar ist, was passiert, oder was die Figuren dort tun.
  * Der zweite Ausschnitt (naher lokaler Ausschnitt) wird für den Haken am Ende verwendet.
- Verwende konkrete visuelle Details aus BEIDEN Ausschnitten, nicht nur ein Minimum.
- Erstelle einen sofortigen Haken, der Leser neugierig macht, was als Nächstes passiert. Dieser Haken MUSS nur auf dem zweiten Bildausschnitt (naher lokaler Ausschnitt) basieren, nicht auf dem ersten Bildausschnitt. Der Haken sollte natürlich eine kurze Fortsetzungsaufforderung enthalten, um das Kind zum Weiterhören zu ermutigen.
- Wenn SITUATION leer ist, erfinde KEINE neue Situation. Verlasse dich nur auf die Bilder.

ABHÄNGIGKEITSREGEL (KRITISCH):
- Wenn VORGESCHICHTE existiert, MUSS das neue Segment direkt ein spezifisches ungelöstes Element daraus vorantreiben.
- Es muss unmöglich sein, eine andere vorherige Geschichte einzutauschen, ohne dass das neue Segment verwirrend wird.
- Verweise nicht nur auf den alten Haken—ändere ihn (kläre ihn, kompliziere ihn oder bewege ihn in Richtung Konsequenz).

FINALE QUALITÄTSPRÜFUNG (OBLIGATORISCH):
Bevor du deine Geschichte zurückgibst, MUSST du sie überprüfen und anpassen, um sicherzustellen:
- BEIDE AUSSCHNITTE BESCHRIEBEN: Überprüfe, dass deine Geschichte Elemente aus BEIDEN Bildausschnitten enthält. Der erste Ausschnitt muss im Hauptinhalt beschrieben sein, der zweite im Haken. Wenn einer der Ausschnitte fehlt, überarbeite die Geschichte.
- KINDGERECHT: Sprache und Konzepte sind für Alter 3-8 angemessen. Verwende einfache, klare Wörter. Vermeide komplexes Vokabular oder abstrakte Konzepte, die Kinder nicht verstehen können.
- FASZINIEREND: Die Geschichte schafft echte Neugier und Engagement. Sie sollte das Kind dazu bringen, wissen zu wollen, was als Nächstes passiert. Beziehe Elemente ein, die Staunen oder Fragen hervorrufen.
- LEBENDIG: Beziehe konkrete sensorische Details ein (Sehenswürdigkeiten, Geräusche, Texturen, Bewegungen). Lass die Szene mit spezifischen, greifbaren Beschreibungen lebendig werden, die sich Kinder vorstellen können.
Wenn deiner Geschichte eine dieser Qualitäten fehlt, überarbeite sie, bevor du das JSON zurückgibst.

Gib gültiges JSON mit einem 'child_story' Feld zurück."""

        # System prompt for FIRST segment only (no "if NONE" branching)
        self.SYSTEM_PROMPT_FIRST = """ROLLE:
Du bist ein Kinder-Geschichtenerzähler in einem Geschichtenketten-Spiel (Alter 3–8).

ZIEL:
Schreibe einen kurzen, fesselnden Geschichtenabschnitt, der die Zuhörenden neugierig und aufmerksam hält.

BILDABHÄNGIGKEIT (KRITISCH):
Verwende genau zwei lokale Bildausschnitte.

Bildausschnitt 1 (hervorgehoben) = Hauptinhalt der Geschichte, zuerst und detailliert beschrieben.

Bildausschnitt 2 (naher Ausschnitt) = ausschließlich der abschließende Haken.

Das vollständige Bild dient nur zur Orientierung.

Wenn für die beiden Ausschnitte Listen von Objekten angegeben sind: Beschreibe für jeden Ausschnitt nur Objekte, die sowohl in der Liste für diesen Ausschnitt stehen als auch im Bildausschnitt sichtbar sind. Erwähne keine Objekte, die nur in der Liste oder nur im Bild vorkommen.

GESCHICHTEN-SETTING:
SITUATION definiert die Welt und ihre Regeln.

Widersprich ihr niemals.

Nutze die Setting-Details aktiv.

REGELN FÜR DEN ERSTEN ABSCHNITT:
child_story MUSS mit den Eröffnungssätzen aus SITUATION beginnen, wortgleich oder nahezu wortgleich.

Setze die Geschichte danach wie folgt fort:

Beschreibe Bildausschnitt 1 als Hauptinhalt.

Stelle eine klare erzählerische Verbindung von Bildausschnitt 1 zu Bildausschnitt 2 her.

Beschreibe Bildausschnitt 2.

Beende den Abschnitt mit einem Haken, der nur auf Bildausschnitt 2 basiert und zur Fortsetzung einlädt.

SATZLIMIT (STRENG):
Die gesamte child_story (einschließlich der SITUATION-Sätze) darf höchstens 5 Sätze enthalten.

Sätze werden anhand von Punkten (.), Fragezeichen (?) oder Ausrufezeichen (!) gezählt.

HAKEN-FORMAT:
Der letzte Satz muss Unsicherheit erzeugen und zur Fortsetzung anregen.

AUSGABE:
Gib gültiges JSON mit einem Feld "child_story" zurück."""

        # System prompt for CONTINUATION only (no "if NONE" branching)
        self.SYSTEM_PROMPT_CONTINUATION = """ROLLE:
Du bist ein Kinder-Geschichtenerzähler in einem Geschichtenketten-Spiel (Alter 3–8).

Deine Aufgabe ist es, eine kurze, fesselnde Fortsetzung der Geschichte auf Basis von Bildern zu schreiben.
Dein Ziel ist es, das Kind aufmerksam zu halten und neugierig auf das Weiterhören zu machen.

GESCHICHTENKONTEXT (IMMER BEREITGESTELLT)

SITUATION definiert die Welt, das Setting und die Regeln der Geschichte.

PREVIOUS_STORY enthält die bisherige Geschichte und endet mit einem ungelösten Haken.

Deine Geschichte MUSS:

der SITUATION folgen und sie respektieren,

eine direkte Fortsetzung der PREVIOUS_STORY sein,

weder der SITUATION noch der PREVIOUS_STORY widersprechen.

BILDABHÄNGIGKEIT (KRITISCH)

Verwende genau zwei lokale Bildausschnitte.

Bildausschnitt 1 (hervorgehoben) = Hauptinhalt der Geschichte und MUSS zuerst und detailliert beschrieben werden.

Bildausschnitt 2 (naher Ausschnitt) = wird verwendet, um am Ende den neuen Haken einzuführen.

Das vollständige Bild dient nur zur Orientierung.

Führe keine Elemente ein, die nicht in Bildausschnitt 1 oder 2 sichtbar sind.

Wenn für die beiden Ausschnitte Listen von Objekten angegeben sind: Beschreibe für jeden Ausschnitt nur Objekte, die sowohl in der Liste für diesen Ausschnitt stehen als auch im Bildausschnitt sichtbar sind. Erwähne keine Objekte, die nur in der Liste oder nur im Bild vorkommen.

FORTSETZUNGSSTRUKTUR (VERPFLICHTEND)

Dein child_story muss dieser dreiteiligen Struktur folgen:

Teil 1 – Auflösung des vorherigen Hakens (Anfang):

Gehe zu Beginn direkt auf den ungelösten Haken am Ende von PREVIOUS_STORY ein und löse ihn auf.

Zeige, was als Folge dieses Hakens passiert.

Teil 2 – Bildbasierter Geschichteninhalt (Mitte):

Beschreibe zuerst Bildausschnitt 1 als Hauptinhalt der Szene.

Stelle eine klare erzählerische Verbindung von Bildausschnitt 1 zu Bildausschnitt 2 her.

Beschreibe Bildausschnitt 2 mit konkreten visuellen Details.

Teil 3 – Neuer Haken (Ende):

Beende die Geschichte mit einem neuen Haken, der ausschließlich auf Bildausschnitt 2 basiert.

Der Haken muss Unsicherheit oder Erwartung erzeugen und zur Fortsetzung einladen.

Die Gesamtgeschichte muss unvollendet bleiben.

LÄNGEN- & STILVORGABEN

Satzlimit (STRENG): Die gesamte child_story darf höchstens 4 Sätze enthalten.
Sätze werden anhand von Punkten (.), Fragezeichen (?) oder Ausrufezeichen (!) gezählt.

Verwende einfache, konkrete Sprache, geeignet für Kinder im Alter von 3–8 Jahren.

Sprich das Kind nicht direkt an.

Verwende den Namen des Kindes nicht.

FINALE QUALITÄTSPRÜFUNG (OBLIGATORISCH)

Bevor du deine Geschichte zurückgibst, stelle sicher, dass:

der vorherige Haken zu Beginn klar aufgelöst wird,

Bildausschnitt 1 zuerst beschrieben wird und den Hauptinhalt bildet,

Bildausschnitt 2 beschrieben wird und nur für den neuen Haken verwendet wird,

das Ende Neugier darauf weckt, was als Nächstes passiert,

sich der Abschnitt wie ein Moment innerhalb eines größeren, sich entfaltenden Ereignisses anfühlt.

AUSGABE

Gib nur gültiges JSON mit einem Feld „child_story“ zurück."""

        # User prompt for FIRST segment only
        self.USER_PROMPT_FIRST = """SITUATION:
{CONTEXT}

KIND HÖRT ZU:
Alter: {CHILD_AGE}
(Verwende den Namen des Kindes nicht in der Geschichte oder sprich das Kind direkt an)

Du bist ein Kinder-Geschichtenerzähler in einem Geschichtenketten-Spiel (Alter 3–8).
ZIEL:
 Schreibe einen kurzen, fesselnden Geschichtenabschnitt, der die Zuhörenden neugierig und aufmerksam hält.
 Verwende einfache, konkrete Sprache, geeignet für Kinder im Alter von 3–8 Jahren.
BILDABHÄNGIGKEIT (KRITISCH):
 Verwende genau zwei lokale Bildausschnitte.
Bildausschnitt 1 (hervorgehoben) = Hauptinhalt der Geschichte, zuerst und detailliert beschrieben.
Bildausschnitt 2 (naher Ausschnitt) = ausschließlich der abschließende Haken.
Das vollständige Bild dient nur zur Orientierung.
Führe keine Elemente ein, die nicht in Bildausschnitt 1 oder 2 sichtbar sind.
Leite keine Handlung aus dem vollständigen Bild ab.
GESCHICHTEN-SETTING:
 SITUATION definiert die Welt und ihre Regeln.
 Widersprich ihr niemals.
 Nutze die Setting-Details aktiv.
REGELN FÜR DEN ERSTEN ABSCHNITT:
 child_story MUSS mit den Eröffnungssätzen aus SITUATION beginnen, wortgleich oder nahezu wortgleich.
 Setze die Geschichte danach wie folgt fort:
Beschreibe Bildausschnitt 1 als Hauptinhalt.
Stelle eine klare erzählerische Verbindung von Bildausschnitt 1 zu Bildausschnitt 2 her, indem sich Handlung, Bewegung oder Aufmerksamkeit in Richtung Bildausschnitt 2 verlagert.
Beschreibe Bildausschnitt 2.
Führe Spannung oder offene Fragen erst ein, nachdem Bildausschnitt 2 beschrieben wurde.
Beende den Abschnitt mit einem Haken, der nur auf Bildausschnitt 2 basiert und zur Fortsetzung einlädt.
SATZLIMIT (STRENG):
 Die gesamte child_story (einschließlich der SITUATION-Sätze) darf höchstens 5 Sätze enthalten.
 Sätze werden anhand von Punkten (.), Fragezeichen (?) oder Ausrufezeichen (!) gezählt.
 Zeilenumbrüche setzen die Satzzählung nicht zurück.
HAKEN-FORMAT:
 Der letzte Satz muss Unsicherheit erzeugen und zur Fortsetzung anregen.
AUSGABE:
 Gib gültiges JSON mit einem Feld „child_story“ zurück."""

        # User prompt for CONTINUATION only
        self.USER_PROMPT_CONTINUATION = """SITUATION (Weltkontext und Regeln):
{CONTEXT}

VORGESCHICHTE (bisherige Geschichte):
{PREVIOUS_STORY}

KIND HÖRT ZU:
Alter: {CHILD_AGE}
(Verwende den Namen des Kindes nicht in der Geschichte und sprich das Kind nicht direkt an.)

BEREITGESTELLTE BILDER:
Hervorgehobener lokaler Ausschnitt (primär) – KRITISCH: MUSS im Hauptinhalt der Geschichte beschrieben werden. Dies ist der Hauptinhalt, NICHT für den Haken.

Naher lokaler Ausschnitt (primär) – Verwende ihn für den Haken am Ende, ABER der erste Ausschnitt MUSS zuerst im Hauptinhalt beschrieben werden.

Vollständiges Bild (Orientierung)

AUFGABE:
Dies ist ein Fortsetzungsabschnitt. Dein child_story muss genau in dieser Reihenfolge aufgebaut sein:
(1) Löse zu Beginn den Haken am Ende der VORGESCHICHTE auf.
(2) Beschreibe anschließend zuerst Bildausschnitt 1 (Hauptinhalt) und danach Bildausschnitt 2, mit einem natürlichen Übergang von Bildausschnitt 1 zu Bildausschnitt 2.
(3) Beende den Abschnitt mit einem neuen Haken, der ausschließlich auf Bildausschnitt 2 basiert (mit Fortsetzungsaufforderung).

Gib nur JSON zurück."""

        # Legacy single USER_PROMPT (kept for reference; two-AOI path uses FIRST/CONTINUATION)
        self.USER_PROMPT = """SITUATION (Eröffnungssätze für die Geschichte, wenn VORGESCHICHTE "NONE" ist):
{CONTEXT}

KIND HÖRT ZU:
Alter: {CHILD_AGE}
(Verwende den Namen des Kindes nicht in der Geschichte oder sprich das Kind direkt an)

VORGESCHICHTE (kann NONE sein):
{PREVIOUS_STORY}

BEREITGESTELLTE BILDER:
1) Hervorgehobener lokaler Ausschnitt (primär) - KRITISCH: MUSS im Hauptinhalt der Geschichte beschrieben werden. Dies ist der Hauptinhalt, NICHT für Haken.
2) Naher lokaler Ausschnitt (primär) - Verwende für den Haken am Ende, ABER der erste Ausschnitt MUSS zuerst im Hauptinhalt beschrieben werden.
3) Vollständiges Bild (Orientierung)

AUFGABE:
Schreibe den nächsten kurzen Geschichtenabschnitt (3-5 Sätze) für den zuhörenden Zuhörer.

Wenn VORGESCHICHTE "NONE" ist:
- Die Eröffnungssätze aus SITUATION sind unten bereitgestellt. Diese Sätze werden der Anfang der Geschichte sein.
- Setze die Geschichte von diesen Eröffnungssätzen fort und zeige, wie sich die Geschichte basierend auf dem Kontext entfaltet.
- KRITISCH: Beschreibe BEIDE Bildausschnitte:
  * Beginne mit dem ersten Ausschnitt (hervorgehobener lokaler Ausschnitt) - beschreibe, was dort sichtbar ist und was passiert. Dies bildet den Hauptinhalt deiner Geschichte.
  * Verwende dann den zweiten Ausschnitt (naher lokaler Ausschnitt) für den Haken am Ende.
- Verwende konkrete visuelle Details aus BEIDEN Ausschnitten.
- Beende mit einem Haken vom zweiten Ausschnitt mit Fortsetzungsaufforderung (z.B. "Was passiert als Nächstes?").

Wenn VORGESCHICHTE existiert:
KONTINUITÄTSAUFGABE:
- Wähle genau EINEN ungelösten Faden aus VORGESCHICHTE (Beispiel: "die leuchtenden Pakete").
- Setze DIESEN Faden in diesem Abschnitt fort (zeige Fortschritt).
- KRITISCH: Beschreibe BEIDE Bildausschnitte:
  * Der erste Ausschnitt (hervorgehobener lokaler Ausschnitt) MUSS im Hauptinhalt beschrieben werden, bevor du den Haken einführst.
  * Der zweite Ausschnitt (naher lokaler Ausschnitt) wird für den Haken verwendet.
- Erst danach führe einen neuen Haken vom zweiten Ausschnitt mit Fortsetzungsaufforderung ein.

Gib nur JSON zurück."""
    
    def _load_context_file(self, image_filename: str) -> str:
        """
        Load context file for a given image.
        
        Args:
            image_filename: The image filename (e.g., "1.jpg", "2.png")
        
        Returns:
            Context string from mini_contexts_de/{image_id}.txt, or empty string if file doesn't exist
        """
        try:
            # Extract image_id from filename (e.g., "1.jpg" -> "1")
            image_id = Path(image_filename).stem
            
            # Load from backend/mini_contexts_de/{image_id}.txt
            context_path = backend_dir / "mini_contexts_de" / f"{image_id}.txt"
            
            if not context_path.exists():
                logger.debug(f"Context file not found: {context_path}")
                return ""
            
            with open(context_path, 'r', encoding='utf-8') as f:
                context_text = f.read().strip()
                return context_text
        except Exception as e:
            logger.warning(f"Error loading context file: {e}")
            return ""
    
    def _load_previous_stories(self, previous_stories: Optional[List[Dict[str, Any]]]) -> str:
        """
        Format previous stories list into prompt text.
        
        Args:
            previous_stories: List of previous story dictionaries, each containing 'child_story' field
        
        Returns:
            Concatenated previous stories with \n\n separator, or "NONE" if list is empty/None
        """
        if not previous_stories or len(previous_stories) == 0:
            return "NONE"
        
        stories = []
        for story_dict in previous_stories:
            # Extract child_story from the dictionary
            # Handle both direct dict and nested 'analysis' dict
            if isinstance(story_dict, dict):
                child_story = story_dict.get('child_story') or story_dict.get('analysis', {}).get('child_story')
                if child_story:
                    stories.append(child_story)
        
        if not stories:
            return "NONE"
        
        return "\n\n".join(stories)
    
    def analyze_two_aoi_images(
        self,
        aoi1_base64: str,
        aoi2_base64: str,
        full_image_base64: str,
        activity: str,
        primary_aoi_index: int,
        secondary_aoi_index: int,
        aoi1_objects: Optional[List[str]] = None,
        aoi2_objects: Optional[List[str]] = None,
        child_name: Optional[str] = None,
        child_age: Optional[str] = None,
        language: str = 'de',  # Language (German only)
        image_filename: Optional[str] = None,  # NEW: For loading context
        previous_stories: Optional[List[Dict[str, Any]]] = None  # NEW: Previous story responses
    ) -> Dict[str, Any]:
        """Analyze two AOI images for storytelling"""
        try:
            logger.debug("Received object lists - AOI1 (%s): %s, AOI2 (%s): %s", primary_aoi_index, aoi1_objects, secondary_aoi_index, aoi2_objects)
            logger.info("Eye-Tracking: Analyzing AOIs %s and %s for %s", primary_aoi_index, secondary_aoi_index, activity)
            
            if not self.api_config or not self.api_config.is_chatgpt_configured():
                return {
                    "success": False,
                    "error": "ChatGPT API not configured"
                }
            
            # Load context file if image_filename provided
            context_text = ""
            if image_filename:
                context_text = self._load_context_file(image_filename)
                logger.debug("Loaded context: %s characters", len(context_text))
            
            # Load previous stories
            previous_story_text = self._load_previous_stories(previous_stories)
            logger.debug("Previous stories: %s...", previous_story_text[:100] if previous_story_text != 'NONE' else 'NONE')
            
            # Decide in code: first segment vs continuation (no LLM branching)
            is_first_segment = not previous_stories or len(previous_stories) == 0
            child_age_value = child_age or "not specified"
            if is_first_segment:
                system_content = self.SYSTEM_PROMPT_FIRST
                user_template = self.USER_PROMPT_FIRST
                formatted_user_prompt = user_template.format(
                    CONTEXT=context_text,
                    CHILD_AGE=child_age_value
                )
            else:
                system_content = self.SYSTEM_PROMPT_CONTINUATION
                user_template = self.USER_PROMPT_CONTINUATION
                formatted_user_prompt = user_template.format(
                    CONTEXT=context_text,
                    PREVIOUS_STORY=previous_story_text,
                    CHILD_AGE=child_age_value
                )
            
            # Add object info if available
            if aoi1_objects or aoi2_objects:
                object_info = [
                    "INHALTE DER BILDAUSSCHNITTE (nur Objekte beschreiben, die in der Liste UND im Bildausschnitt vorkommen):"
                ]
                if aoi1_objects:
                    object_info.append(f"Bildausschnitt 1 (Hauptinhalt): {', '.join(aoi1_objects)}")
                if aoi2_objects:
                    object_info.append(f"Bildausschnitt 2 (Haken): {', '.join(aoi2_objects)}")
                object_info.append("Beschreibe bei jedem Ausschnitt nur Objekte, die in der jeweiligen Liste stehen und im jeweiligen Bildausschnitt erkennbar sind.")
                if object_info:
                    formatted_user_prompt = "\n".join(object_info) + "\n\n" + formatted_user_prompt
            
            headers = {
                "Authorization": f"Bearer {self.api_config.get_chatgpt_key()}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "system",
                        "content": system_content
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": formatted_user_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{aoi1_base64}", "detail": "high"}},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{aoi2_base64}", "detail": "high"}},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{full_image_base64}", "detail": "low"}}
                        ]
                    }
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 1000,
                "temperature": 0.7
            }
            
            num_messages = len(payload.get("messages", []))
            text_len = len(formatted_user_prompt) if formatted_user_prompt else 0
            user_content = payload["messages"][1].get("content", []) if num_messages > 1 else []
            num_image_parts = sum(1 for c in user_content if isinstance(c, dict) and c.get("type") == "image_url")
            logger.debug("LLM request: model=%s, messages=%s, prompt_len=%s, image_parts=%s", payload.get('model'), num_messages, text_len, num_image_parts)
            emit_llm_prompt(payload, "eye_tracking_two_aoi")

            response = requests.post(self.base_url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                choices = result.get("choices") or []
                
                if not choices:
                    logger.error(
                        "❌ API returned no choices: result keys=%s, choices_len=%s",
                        list(result.keys()),
                        len(choices)
                    )
                    return {
                        "success": False,
                        "error": "API returned no choices"
                    }
                
                first_choice = choices[0]
                message = first_choice.get("message") or {}
                content = message.get("content")
                
                if content is None:
                    finish_reason = first_choice.get("finish_reason")
                    refusal = message.get("refusal")
                    annotations = message.get("annotations")
                    logger.error(
                        "❌ API returned None content for AOIs %s and %s: choices_len=%s, finish_reason=%s, message_keys=%s, usage=%s, model=%s | refusal=%s, annotations=%s",
                        primary_aoi_index,
                        secondary_aoi_index,
                        len(choices),
                        finish_reason,
                        list(message.keys()),
                        result.get("usage"),
                        result.get("model"),
                        refusal,
                        annotations
                    )
                    return {
                        "success": False,
                        "error": "API returned None content",
                        "refusal": refusal
                    }
                
                content = content.strip()
                
                # Strip markdown code blocks if present
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                analysis = json.loads(content)
                logger.info(f"✅ Eye-tracking LLM analysis completed for AOIs {primary_aoi_index} and {secondary_aoi_index}")
                
                return analysis
                
            else:
                try:
                    err_body = response.json()
                except Exception:
                    err_body = response.text
                logger.error(
                    "❌ Eye-tracking LLM API error: status=%s, body=%s",
                    response.status_code,
                    err_body
                )
                return {
                    "success": False,
                    "error": f"LLM API error: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to analyze two AOI images: {e}")
            raise
    
    def create_voice_texts(self, analysis: Dict[str, Any], activity: str, child_name: str = "little explorer") -> Dict[str, str]:
        """Create voice text for eye-tracking guidance (storytelling only)"""
        try:
            # Storytelling: just use child_story directly (no acknowledgment field anymore)
            main_voice = analysis.get('child_story', '')
            
            return {
                "main_voice": main_voice.strip()
            }
            
        except Exception as e:
            logger.error(f"❌ Error creating eye-tracking voice texts: {e}")
            return {
                "main_voice": "I see you're curious about this part!"
            }

# Global instance
_eye_tracking_llm_service: Optional[EyeTrackingLLMService] = None

def get_eye_tracking_llm_service() -> EyeTrackingLLMService:
    """Get the global eye-tracking LLM service instance"""
    global _eye_tracking_llm_service
    if _eye_tracking_llm_service is None:
        _eye_tracking_llm_service = EyeTrackingLLMService()
    return _eye_tracking_llm_service
