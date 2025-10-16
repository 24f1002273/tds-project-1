# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi[standard]",
#   "uvicorn",
#  "requests",
# ]
# ///
from fastapi import FastAPI, HTTPException
import os
import requests
import uvicorn
import base64
import time
from typing import List, Dict, Any
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "24f1002273")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)



def validate_secret(secret):
    return secret == os.getenv("secret")


def create_github_repo(repo_name):
    #using github api create a repo with name repo_name
    payload = {
        "name": repo_name,
        "private": False,
        "auto_init": True,
        "license_template": "mit"
    }
    # put Setting to application/vnd.github+json is recommended.
    headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    
    response = requests.post(
        "https://api.github.com/user/repos", 
        headers=headers, 
        json=payload
    )
    if response.status_code != 201:
        raise Exception(f"Failed to create repo: {response.status_code}, {response.text}")
    else:
        return response.json()

def enable_github_pages(repo_name):
    #takes repo name as argument and enables github pages for that repo using github api
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    payload = {
        "build_type": "legacy",
        "source": {
            "branch": "main",
            "path": "/"
        }
    }
    response = requests.post(
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/pages",
        headers=headers,
        json=payload
    )
    if response.status_code != 201:
        raise Exception(f"Failed to enable GitHub Pages: {response.status_code}, {response.text}")
    else:
        return response.json()

def get_sha_of_latest_commit(repo_name, branch="main"):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    response = requests.get(
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/commits/{branch}",
        headers=headers
    )
    if response.status_code != 200:
        raise Exception(f"Failed to get latest commit SHA: {response.status_code}, {response.text}")
    else:
        return response.json().get("sha")

def get_file_sha(repo_name: str, file_path: str) -> str:
    """Get SHA of existing file for updates"""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    
    response = requests.get(
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/{file_path}",
        headers=headers
    )
    
    if response.status_code == 200:
        return response.json().get("sha", "")
    return None


def push_to_repo(repo_name: str, files: List[Dict[str, str]], round_num: int):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    
    for file in files:
        file_name = file.get("name")
        file_content = file.get("content")
        
        # Encode content to base64 if not already
        if not file_content.startswith("data:"):
            file_content_b64 = base64.b64encode(file_content.encode()).decode()
        else:
            file_content_b64 = file_content
        
        payload = {
            "message": f"Add/Update {file_name} (Round {round_num})",
            "content": file_content_b64
        }
        
        # For round 2, get existing file SHA to update
        if round_num == 2:
            file_sha = get_file_sha(repo_name, file_name)
            if file_sha:
                payload["sha"] = file_sha
        
        response = requests.put(
            f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/{file_name}",
            headers=headers,
            json=payload
        )
        
        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to push {file_name}: {response.status_code}, {response.text}")

def write_code_with_llm(brief: str, checks: List[str], attachments: List[Dict], task: str) -> List[Dict[str, str]]:
    """Generate code using Google Gemini API"""
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    
    # Prepare attachments info
    attachments_info = ""
    if attachments:
        attachments_info = "\n\nAttachments provided:\n"
        for att in attachments:
            attachments_info += f"- {att['name']}: {att['url'][:100]}...\n"
    
    prompt = f"""You are tasked with creating a complete, functional single-page web application.

Task: {task}

Brief: {brief}

Requirements (checks that will be evaluated):
{chr(10).join(f"- {check}" for check in checks)}

{attachments_info}

Please generate:
1. A complete index.html file with all necessary HTML, CSS (inline or in <style>), and JavaScript (inline or in <script>)
2. A professional README.md file with:
   - Project summary
   - Setup instructions
   - Usage guide
   - Code explanation
   - License information (MIT)

Requirements:
- Single-page application (all in index.html)
- Use CDN links for any external libraries (Bootstrap, marked, highlight.js, etc.)
- Make sure all checks pass
- Clean, well-commented code
- Professional appearance
- Handle attachments by embedding data URIs directly in the code

Respond with two code blocks:
1. index.html
2. README.md"""

    response = model.generate_content(prompt)
    
    # Parse response to extract code blocks
    response_text = response.text
    
    files = []
    
    # Extract index.html
    if "```html" in response_text:
        html_start = response_text.find("```html") + 7
        html_end = response_text.find("```", html_start)
        html_content = response_text[html_start:html_end].strip()
        files.append({"name": "index.html", "content": html_content})
    
    # Extract README.md
    if "```markdown" in response_text or "```md" in response_text:
        if "```markdown" in response_text:
            readme_start = response_text.find("```markdown") + 11
        else:
            readme_start = response_text.find("```md") + 5
        readme_end = response_text.find("```", readme_start)
        readme_content = response_text[readme_start:readme_end].strip()
        files.append({"name": "README.md", "content": readme_content})
    
    return files


def notify_evaluation(evaluation_url: str, data: Dict[str, Any], retries: int = 5):
    """Notify evaluation endpoint with exponential backoff"""
    headers = {"Content-Type": "application/json"}
    
    for attempt in range(retries):
        try:
            response = requests.post(evaluation_url, json=data, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Evaluation API returned {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
        
        if attempt < retries - 1:
            delay = 2 ** attempt  # Exponential backoff: 1, 2, 4, 8 seconds
            time.sleep(delay)
    
    raise Exception("Failed to notify evaluation endpoint after all retries")

def round1(data: dict):
    """Handle round 1: Create repo, generate code, deploy"""
    task = data['task']
    nonce = data['nonce']
    repo_name = f"{task}"
    
    # Create repository
    repo_info = create_github_repo(repo_name)
    repo_url = repo_info['html_url']
    
    # Wait for repo to be ready
    time.sleep(2)
    
    # Generate code with LLM
    files = write_code_with_llm(
        brief=data['brief'],
        checks=data['checks'],
        attachments=data.get('attachments', []),
        task=task
    )
    
    # Push files to repo
    push_to_repo(repo_name, files, round_num=1)
    
    # Wait for commit to be processed
    time.sleep(2)
    
    # Enable GitHub Pages
    enable_github_pages(repo_name)
    
    # Get latest commit SHA
    commit_sha = get_sha_of_latest_commit(repo_name)
    
    # Construct pages URL
    pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
    
    # Notify evaluation endpoint
    notification_data = {
        "email": data['email'],
        "task": task,
        "round": 1,
        "nonce": nonce,
        "repo_url": repo_url,
        "commit_sha": commit_sha,
        "pages_url": pages_url
    }
    
    notify_evaluation(data['evaluation_url'], notification_data)

def round2(data: dict):
    """Handle round 2: Update existing repo"""
    task = data['task']
    nonce = data['nonce']
    repo_name = f"{task}"
    
    # Generate updated code with LLM
    files = write_code_with_llm(
        brief=data['brief'],
        checks=data['checks'],
        attachments=data.get('attachments', []),
        task=task
    )
    
    # Push updated files to repo
    push_to_repo(repo_name, files, round_num=2)
    
    # Wait for commit to be processed
    time.sleep(2)
    
    # Get latest commit SHA
    commit_sha = get_sha_of_latest_commit(repo_name)
    
    # Construct pages URL
    pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
    
    # Get repo URL
    repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
    
    # Notify evaluation endpoint
    notification_data = {
        "email": data['email'],
        "task": task,
        "round": 2,
        "nonce": nonce,
        "repo_url": repo_url,
        "commit_sha": commit_sha,
        "pages_url": pages_url
    }
    
    notify_evaluation(data['evaluation_url'], notification_data)


app = FastAPI()

#post endpoint to take a json with fields : email, secret, task, round, nounce, brief, checks(array), evaluation of url, attachments(array with fields name and url)
@app.post("/handle_task")
async def handle_task(data: dict):
    if not validate_secret(data.get("secret", "")):
        return {"error": "Invalid secret"}
    else:
        # Process the valid task
        if data.get("round") == 1:
            round1(data)
            return {"message": "Round 1 processing started"}
        elif data.get("round") == 2:
            round2(data)
            return {"message": "Round 2 processing started"}
        else:
            return {"error": "Invalid round"}
        

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
