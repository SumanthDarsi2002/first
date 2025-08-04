import os
import speech_recognition as sr
import pyttsx3
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import wikipediaapi
import json
from fpdf import FPDF
import logging
import urllib.parse
import urllib.request
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Text-to-Speech setup
engine = pyttsx3.init()
engine.setProperty("rate", 160)

# Seminar cache
seminar_cache = {}
if os.path.exists("seminars.json"):
    with open("seminars.json", "r") as f:
        try:
            seminar_cache = json.load(f)
        except json.JSONDecodeError:
            seminar_cache = {}

# Wikipedia content

def search_wikipedia(topic):
    wiki = wikipediaapi.Wikipedia(user_agent="AI-Seminar-Assistant/1.0", language="en")
    page = wiki.page(topic)
    if page.exists():
        sections = [page.summary]
        for section in page.sections:
            sections.append(f"{section.title}:\n{section.text}")
        return "\n\n".join(sections)[:8000]  # Include section headings
    return "No Wikipedia page found."

# Google content fallback

def search_google(query):
    try:
        # Remove the unsupported 'stop' argument
        results = list(search(query))  # Get the first few results
        full_content = []
        count = 0
        for url in results:
            try:
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                content = " ".join([p.get_text() for p in soup.find_all("p")])
                if len(content) > 200:
                    full_content.append(content[:3000])
                    count += 1
                if count >= 3:
                    break
            except Exception as e:
                logging.warning(f"Failed to extract from {url}: {e}")
        return "\n".join(full_content) if full_content else "Couldn't extract enough data from Google."
    except Exception as e:
        logging.error(f"Google Search Error: {e}")
    return "Couldn't extract enough data from Google."

# Image fetch

def fetch_images_from_google(topic, num=3):
    try:
        query = urllib.parse.quote(topic)
        url = f"https://www.google.com/search?hl=en&tbm=isch&q={query}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")
        imgs = soup.find_all("img")[1:num+1]
        return [img.get("src") for img in imgs if img.get("src", "").startswith("http")]
    except Exception as e:
        logging.error(f"Image fetching error: {e}")
        return []

# Download images

def download_images(urls, topic):
    paths = []
    folder = f"images_{topic.replace(' ', '_')}"
    os.makedirs(folder, exist_ok=True)
    for i, url in enumerate(urls):
        try:
            path = os.path.join(folder, f"{i+1}.jpg")
            urllib.request.urlretrieve(url, path)
            paths.append(path)
        except Exception as e:
            logging.warning(f"Failed to download image: {e}")
    return paths

# PDF generation

def save_as_pdf(topic, content, images):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Seminar on {topic.title()}", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Introduction", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", size=12)
    safe_text = content.encode("latin-1", "replace").decode("latin-1")
    pdf.multi_cell(0, 10, safe_text)
    pdf.ln(5)
    for path in images:
        try:
            img = Image.open(path)
            w, h = img.size
            aspect = w / h
            pdf_w = 180
            pdf_h = pdf_w / aspect
            pdf.add_page()
            pdf.image(path, x=15, y=40, w=pdf_w, h=pdf_h)
        except Exception as e:
            logging.warning(f"Image error in PDF: {e}")
    pdf.output(f"{topic.replace(' ', '_')}.pdf")

# Speak with explanation

def explain_and_speak(text):
    explain_text = f"Here is an explanation of your seminar topic. {text[:500]}"
    speak(explain_text)

# Speak

def speak(text):
    engine.say(text)
    engine.runAndWait()

# GUI + Voice trigger
class SeminarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Seminar Assistant")
        self.root.geometry("800x600")

        ttk.Label(root, text="Say or Type Seminar Topic:", font=("Arial", 14)).pack(pady=10)
        self.topic_entry = ttk.Entry(root, width=50, font=("Arial", 12))
        self.topic_entry.pack()

        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="🎤 Speak", command=self.speak_threaded).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🔍 Search", command=self.generate).pack(side=tk.LEFT, padx=5)

        self.content_box = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=90, height=15, font=("Arial", 11))
        self.content_box.pack(padx=10, pady=10)

        self.image_frame = ttk.Frame(root)
        self.image_frame.pack()

    def speak_threaded(self):
        threading.Thread(target=self.speak_topic).start()

    def speak_topic(self):
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            speak("Adjusting for ambient noise. Please wait.")
            recognizer.adjust_for_ambient_noise(source, duration=2)
            speak("Listening for seminar topic now. Please speak clearly.")
            try:
                audio = recognizer.listen(source, timeout=20, phrase_time_limit=15)
                try:
                    topic = recognizer.recognize_google(audio, language='en-IN')
                    if topic:
                        self.topic_entry.delete(0, tk.END)
                        self.topic_entry.insert(0, topic)
                        speak(f"You said: {topic}. Generating seminar...")
                        self.generate()
                    else:
                        speak("Sorry, I didn't catch that. Please try again.")
                except sr.UnknownValueError:
                    speak("Speech not recognized clearly. Try again slowly.")
                except sr.RequestError:
                    speak("Could not connect to the recognition service.")
            except sr.WaitTimeoutError:
                speak("Listening timed out. Please speak within 15 seconds.")
            except Exception as e:
                logging.error(f"Speech Recognition Error: {e}")
                speak("Sorry, something went wrong while listening.")

    def generate(self):
        topic = self.topic_entry.get().strip()
        if not topic:
            speak("Please enter or say a topic.")
            return

        self.content_box.delete("1.0", tk.END)
        for widget in self.image_frame.winfo_children():
            widget.destroy()

        if topic in seminar_cache:
            content = seminar_cache[topic]
        else:
            content = search_wikipedia(topic)
            if "No Wikipedia page found" in content:
                content = search_google(topic)
            seminar_cache[topic] = content
            with open("seminars.json", "w") as f:
                json.dump(seminar_cache, f)

        self.content_box.insert(tk.END, content)
        explain_and_speak(content)

        image_urls = fetch_images_from_google(topic)
        image_paths = download_images(image_urls, topic)

        for path in image_paths:
            try:
                img = Image.open(path)
                img.thumbnail((150, 150))
                img_tk = ImageTk.PhotoImage(img)
                lbl = ttk.Label(self.image_frame, image=img_tk)
                lbl.image = img_tk
                lbl.pack(side=tk.LEFT, padx=5)
            except Exception as e:
                logging.warning(f"Image preview failed: {e}")

        save_as_pdf(topic, content, image_paths)
        speak(f"Seminar with images on {topic} saved as PDF.")

if __name__ == "__main__":
    root = tk.Tk()
    app = SeminarApp(root)
    root.mainloop()
