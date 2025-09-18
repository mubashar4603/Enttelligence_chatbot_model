# 🤖 Enttelligence_chatbot_model

This project is a **Django REST Framework backend** integrated with an **AI Agent** for answering questions about movies, theaters, showtimes, seating, and ticketing.  
It combines a traditional API (conversations, messages) with a CSV-powered AI agent that uses **LangChain** and **phi**.

---

## 🚀 Features

✅ User authentication (via DRF)  
✅ Conversation & message storage  
✅ AI chatbot API endpoint (`/chat/`)  
✅ Integration with CSV dataset (`Movie_shows_2023.csv`)  
✅ Supports queries about:
- Movies (availability, runtime, release date, genre, etc.)
- Theaters (location, amenities, circuit name, DMA region)
- Showtimes (dates, times, formats, availability)
- Ticket pricing (adult, child, senior)
- Seating & reservation status

---

## 📂 Project Structure

```
Enttelligence_chatbot_model/
│── ai/                        # AI agent logic (LangChain, phi, OpenAI)
│   └── agent.py
│── data/                      # CSV dataset (Movie_shows_2023.csv)
│── env/                       # Virtual environment
│── hvac_assist_backend-main/  # Django backend
│   ├── accounts/              # User accounts & authentication
│   ├── admin_dashboard/       # Admin-related modules
│   ├── chat/                  # Chat API (conversations, messages)
│   └── hvac_assist_backend/   # Core Django project settings
│── requirements.txt           # Python dependencies
│── readme.md                  # This README
```

---

## ⚙️ Installation

### 1️⃣ Clone the repo
```bash
git clone <your-repo-url>
cd Enttelligence_chatbot_model
```

### 2️⃣ Create & activate virtual environment
**Windows (PowerShell):**
```powershell
python -m venv env
.\env\Scriptsctivate
```

**Linux/Mac:**
```bash
python -m venv env
source env/bin/activate
```

### 3️⃣ Install dependencies
```bash
pip install -r requirements.txt
```

### 4️⃣ Setup Django
```bash
cd hvac_assist_backend-main
python manage.py migrate
```

---

## ▶️ Running the Project

### Start Django backend
```bash
cd hvac_assist_backend-main
python manage.py runserver
```
Server will start at **http://127.0.0.1:8000/**

---

## 💬 Chat API

### Endpoint
`POST /chat/`

### Request body:
```json
{
  "message": "What movies are playing at AMC Lincoln Square?"
}
```

### Response:
```json
{
  "user_message": "What movies are playing at AMC Lincoln Square?",
  "bot_reply": "The movies playing are: A Man Called Otto ..."
}
```

---

## 🔑 Authentication

- Endpoints like `/chat/` require **JWT / Token Authentication** (via DRF).
- Include your token in requests:

```http
Authorization: Bearer <your_token>
```

---

## 🛠 Tech Stack

- **Backend:** Django, Django REST Framework  
- **AI/LLM:** LangChain, phi, OpenAI / Ollama models  
- **Data:** CSV dataset (movies & showtimes)  
- **Auth:** DRF authentication system  
- **Extras:** django-cors-headers for cross-origin requests  

---


## 👨‍💻 Developer Notes

- Place your dataset in `data/Movie_shows_2023.csv`  
- Update your **API keys** in `ai/agent.py`:

- For local Ollama or custom model, adjust the `base_url` and `host`.

---
