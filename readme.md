
# Cura — Emotionally Aware Virtual Clinician


Cura is an emotionally intelligent **virtual clinician**, built to explore how AI can communicate with warmth, awareness, and presence. It blends **local AI models**, **affect sensing**, and a **dynamically expressive avatar** to create conversations that feel more human than typical chatbots.

Cura is a research prototype — not a medical tool — but it demonstrates how future digital helpers might offer support in a calmer, more emotionally attuned way.

![Screenshot](./public/screenshot.png)


---

## 🌟 What Makes Cura Special?

### **1. It senses emotional tone**
As you type, Cura uses a local LLM to infer your emotional state (e.g., *tense*, *curious*, *sad*, *hopeful*).  
This shapes the clinician’s responses and overall presence.

### **2. It replies with short, warm, supportive messages**
The virtual clinician is designed to sound human, gentle, and focused — not like a robotic assistant.  
It gives medical advice, but you should not follow it. It is straight from the LLM without any oversight. LLMs make mistakes.


Still, its pretty good. 


### **3. The avatar reacts to you**
Cura’s on-screen avatar changes expression depending on:
- your emotional state  
- the clinician’s reply  
- the flow of the conversation  

Images like *listening*, *thinking*, *concerned*, even *phone-checking* give the assistant some personality.

### **4. Everything runs locally**
No cloud services.  
No data leaves your machine.  
All intelligence comes from **Ollama running Llama 3 locally**, for cost and speed.

### **5. Sub‑second responses through parallel LLM calls**
The app runs two AI tasks in parallel:
- affect estimation  
- clinician reply generation  

This keeps the experience fast and natural.

---

## 🧠 How Cura Works (Simple Version)

- You type a message.  
- The backend estimates how you’re feeling.  
- At the same time, it generates a clinician reply.  
- Then it chooses the best avatar expression for the moment.
- Everything updates in conversational speed.

A small debug panel lets you see how the system works.

---

## 💻 Technologies Behind Cura

- **React** — chat interface + avatar display  
- **FastAPI** — backend server + state management  
- **Ollama + Llama 3** — local AI models  
- **Dynamic avatar loader** — scans the avatar folder automatically  
- **Threaded parallel inference** — keeps the system responsive  

---

## 🚀 Future Possibilities

Cura lays the groundwork for more advanced ideas:
- webcam-based emotion detection  
- adaptive clinician personalities  
- richer expressive avatars  
- VR integration  
- training tools for communication skills  

---

## ⚠️ Important

Cura is **not** a clinical device.  
It is a **research experiment** exploring how emotionally attuned AI interactions might improve user experience.

