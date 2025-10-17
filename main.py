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

def enable_github_pages(repo_name: str):
    """Enable GitHub Pages with GitHub Actions as the source"""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    # Configure Pages to use GitHub Actions
    payload = {
        "build_type": "workflow"
    }
    
    # First, try to create/update pages configuration
    response = requests.post(
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/pages",
        headers=headers,
        json=payload
    )
    
    if response.status_code == 409:
        # Pages already exists, update it
        response = requests.put(
            f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/pages",
            headers=headers,
            json=payload
        )
    
    if response.status_code not in [200, 201, 204, 409]:
        print(f"Warning: Failed to configure pages: {response.status_code}, {response.text}")
        # Don't raise exception, as the workflow will still trigger


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
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    for file in files:
        file_name = file.get("name")
        file_content = file.get("content")
        
        # Encode content to base64 if not already
        if not file_content.startswith("data:"):
            file_content_b64 = base64.b64encode(file_content.encode()).decode()
        else:
            file_content_b64 = file_content
        
        # Always try to get the current file SHA first
        file_sha = None
        try:
            check_response = requests.get(
                f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/{file_name}",
                headers=headers,
                timeout=10
            )
            if check_response.status_code == 200:
                file_sha = check_response.json().get("sha")
                print(f"Found existing {file_name} with SHA: {file_sha[:7]}...")
        except Exception as e:
            print(f"No existing {file_name} found, creating new: {str(e)}")
        
        payload = {
            "message": f"Add/Update {file_name} (Round {round_num})",
            "content": file_content_b64,
            "branch": "main"
        }
        
        if file_sha:
            payload["sha"] = file_sha
        
        response = requests.put(
            f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/{file_name}",
            headers=headers,
            json=payload
        )
        
        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to push {file_name}: {response.status_code}, {response.text}")
        else:
            print(f"Successfully pushed {file_name}")
        
        # Small delay between file pushes
        time.sleep(0.5)


def write_code_with_llm(brief: str, checks: List[str], attachments: List[Dict], task: str) -> List[Dict[str, str]]:
    """Generate code using Google Gemini API"""
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
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
    
    print(f"Attempting to notify evaluation endpoint: {evaluation_url}")
    print(f"Notification data: {data}")
    
    for attempt in range(retries):
        try:
            print(f"Attempt {attempt + 1}/{retries}...")
            response = requests.post(
                evaluation_url, 
                json=data, 
                headers=headers, 
                timeout=30,
                verify=True  # Verify SSL certificates
            )
            
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
            
            if response.status_code == 200:
                print("Notification successful!")
                return response.json()
            elif response.status_code in [201, 202, 204]:
                # Some APIs return these for successful operations
                print(f"Notification accepted with status {response.status_code}")
                return {"status": "success"}
            else:
                print(f"Evaluation API returned {response.status_code}: {response.text}")
                
        except requests.exceptions.Timeout as e:
            print(f"Attempt {attempt + 1} timed out: {str(e)}")
        except requests.exceptions.ConnectionError as e:
            print(f"Attempt {attempt + 1} connection error: {str(e)}")
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} request failed: {str(e)}")
        except Exception as e:
            print(f"Attempt {attempt + 1} unexpected error: {str(e)}")
        
        if attempt < retries - 1:
            delay = 2 ** attempt  # Exponential backoff: 1, 2, 4, 8, 16 seconds
            print(f"Waiting {delay} seconds before retry...")
            time.sleep(delay)
    
    # If all retries fail, log the error but don't crash the entire process
    error_msg = f"Failed to notify evaluation endpoint after {retries} retries. URL: {evaluation_url}"
    print(error_msg)
    raise Exception(error_msg)

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
    
    # Add GitHub Actions workflow for Pages deployment
    workflow_content = """name: Deploy static content to Pages

on:
  push:
    branches: ["main"]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Pages
        uses: actions/configure-pages@v5
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: '.'
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
"""
    
    files.append({
        "name": ".github/workflows/static.yml",
        "content": workflow_content
    })
    
    # Push files to repo
    push_to_repo(repo_name, files, round_num=1)
    
    # Wait for commit to be processed
    time.sleep(2)
    
    # Enable GitHub Pages with GitHub Actions as source
    enable_github_pages_with_actions(repo_name)
    
    # Get latest commit SHA
    commit_sha = get_latest_commit_sha(repo_name)
    
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
    
    try:
        result = notify_evaluation(data['evaluation_url'], notification_data)
        print(f"Notification result: {result}")
    except Exception as e:
        # Log the error but don't fail the entire process
        print(f"Notification failed but deployment was successful: {str(e)}")
        # You might want to store this in a database for manual retry later

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
def handle_task(data: dict):
    if not validate_secret(data.get("secret", "")):
        return {"error": "Invalid Secret"}, 403
    
    try:
        if data.get("round") == 1:
            round1(data)
            return {"status": "Round 1 completed"}
        elif data.get("round") == 2:
            round2(data)
            return {"status": "Round 2 completed"}
        else:
            return {"error": "Invalid round"}
    except Exception as e:
        return {"error": str(e)}, 500

        

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
