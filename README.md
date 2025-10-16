# tds-project-1
# 🚀 Auto GitHub WebApp Generator using FastAPI + Gemini

This project automates the creation, deployment, and evaluation of web applications directly on **GitHub Pages**, powered by **Google Gemini AI** and **FastAPI**.

It creates a new GitHub repository, generates complete single-page web applications (HTML + CSS + JS), pushes them to GitHub, enables GitHub Pages, and notifies an external evaluation endpoint — all with a single API call.

---

##  Features

-  **AI Code Generation:** Uses Google Gemini to generate complete front-end projects.
-  **Automatic GitHub Repository Creation:** Creates public repos with an MIT license.
-  **One-Click Deployment:** Enables GitHub Pages for automatic hosting.
-  **Two-Round Update System:** Supports initial and updated submissions.
-  **Evaluation Webhook:** Notifies an external endpoint after deployment.
-  **Secret-Based Security:** Validates tasks using a secret key.

---

##  Tech Stack

- **Backend:** FastAPI  
- **AI Model:** Google Gemini (`google-generativeai`)  
- **Version Control:** GitHub REST API  
- **Server:** Uvicorn  
- **Language:** Python 3.11+  

---

##  Setup Instructions

### 1. Clone the Repository 

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>


### 2. Create a Virtual Environment

python -m venv venv
source venv/bin/activate   # For Linux/Mac
venv\Scripts\activate      # For Windows

3. Install Dependencies
pip install -r requirements.txt

4. Configure Environment Variables

Create a .env file in the root directory with:
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_USERNAME=your_github_username
GOOGLE_API_KEY=your_gemini_api_key
secret=your_custom_secret_key


Running the Server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

