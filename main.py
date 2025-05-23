from fastapi import FastAPI, HTTPException
import requests
from fastapi.middleware.cors import CORSMiddleware
import os
import sqlite3
from passlib.hash import pbkdf2_sha256
from contextlib import contextmanager

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


API_KEY =os.environ["API_K"]
API_URL = 'https://openrouter.ai/api/v1/chat/completions'
OMDB_API_KEY =  os.environ["OMDB_API_K"]
OMDB_API_URL = 'http://www.omdbapi.com/'

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}

prefix = """give me a serie or movie to watch , return just the movie name , the movie story, the story, the movie cover link. always try to get different movies, the response has to be like this:
*Movie Name:* the name.
*Movie Story:* the story.
*Movie Cover Link*: the link (make sure it's one link and use IMDb to get the cover link)
"""

@app.get("/get_movie")
async def get_movie(user_prompt: str):
    data = {
        "model": "deepseek/deepseek-chat:free",
        "messages": [{"role": "user", "content": user_prompt + prefix}]
    }
    
    response = requests.post(API_URL, json=data, headers=headers)
    
    if response.status_code == 200:
        response_data = response.json()
        content = response_data['choices'][0]['message']['content']
        
        if content:
            movie_details = extract_movie_details(content)
            movie_cover_url = get_movie_cover_from_omdb(movie_details['movie_name'])

            return {
                "movie_name": movie_details['movie_name'],
                "movie_story": movie_details['movie_story'],
                "movie_cover_url": movie_cover_url
            }
        else:
            raise HTTPException(status_code=404, detail="Movie details not found.")
    else:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch movie details from external API.")

def extract_movie_details(content: str):
    movie_name_pattern = r"\*Movie Name:\* (.*?)\n"
    movie_story_pattern = r"\*Movie Story:\* (.*?)\n"
    movie_cover_pattern = r"\*Movie Cover Link\*:\s*(https?:\/\/[^\s]+)"

    movie_name = None
    movie_story = None
    movie_cover_link = None
    
    import re
    movie_name_match = re.search(movie_name_pattern, content)
    movie_story_match = re.search(movie_story_pattern, content)
    movie_cover_match = re.search(movie_cover_pattern, content)

    if movie_name_match:
        movie_name = movie_name_match.group(1)
    if movie_story_match:
        movie_story = movie_story_match.group(1)
    if movie_cover_match:
        movie_cover_link = movie_cover_match.group(1)
    
    return {
        "movie_name": movie_name,
        "movie_story": movie_story,
        "movie_cover_link": movie_cover_link
    }


def get_movie_cover_from_omdb(movie_name: str):
    omdb_url = f"{OMDB_API_URL}?t={movie_name}&apikey={OMDB_API_KEY}"
    response = requests.get(omdb_url)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('Response') == 'True' and 'Poster' in data:
            return data['Poster'] 
        else:
            return None
    else:
        return None 

# --- Database Setup ---
@contextmanager
def get_db_connection():
    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def create_user_table():
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')
        conn.commit()

create_user_table()

# --- Auth Endpoints ---
from fastapi import Form

@app.post("/signup")
async def signup(username: str = Form(...), password: str = Form(...)):
    hashed_password = pbkdf2_sha256.hash(password)
    try:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            conn.commit()
        return {"message": "User created successfully"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists.")

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    with get_db_connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user and pbkdf2_sha256.verify(password, user["password"]):
        return {"message": "Login successful"}
    else:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
