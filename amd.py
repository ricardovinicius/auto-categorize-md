#!/usr/bin/env python3

import json
import shutil
import typing
import unicodedata
import argparse

import google.generativeai as genai

from pydantic import BaseModel
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List

parser = argparse.ArgumentParser(description="Organizador automático de notas em texto")

parser.add_argument('--input_dir', type=str, help="Diretório que armazena as notas")
parser.add_argument('--output_dir', type=str, help="Diretório que as notas deverão ser organizadas")

args = parser.parse_args()

INPUT_NOTES_PATH = Path(args.input_dir)
OUTPUT_NOTES_PATH = Path(args.output_dir)
DATA_PATH = Path(args.input_dir, "metadata.json")

print(args)

class Settings(BaseSettings):
    gen_ai_key: str
    
    class Config:
        env_file = ".env"
    
settings = Settings()


    
class Category(BaseModel):
    name: str = ""
    subcategories: List[str] = []

class Note(BaseModel):
    name: str 
    path: Path
    category_name: str = "Uncategorized"
    subcategory_name: str | None = None

class SystemData(BaseModel):
    categories: List[Category] = [Category(name="Uncategorized")]
    notes: List[Note] = []
    
    def save_to_file(self):
        with open(DATA_PATH, "w") as file:
            file.write(self.model_dump_json(indent=4))
        
data_file = Path(DATA_PATH)

def loads_data_from_json():
    with open(DATA_PATH, "r") as file:
        return json.load(file)

system_data: SystemData = SystemData()

if data_file.exists() and data_file.is_file():
    json_data = loads_data_from_json()
    system_data = SystemData(**json_data)
    

def dumps_note(note_file_path: Path):
    if not note_file_path.is_file():
        raise IsADirectoryError()
    
    note = Note(
            name=Path(note_file_path).name,
            path=note_file_path
        )
        
    return note
    
def check_if_note_already_mapped(data: SystemData, note: Note):
    for existent_note in data.notes:
        if existent_note.path == note.path:
            return True

    return False

genai.configure(api_key=settings.gen_ai_key)
model = genai.GenerativeModel("gemini-2.0-flash-exp")

class OutputSchema(typing.TypedDict):
    category: str
    subcategory: str

def categorize_note(note: Note, model: genai.GenerativeModel, categories: List[Category]):
    note_text = ""
    
    with open(note.path, "r") as file:
        note_text = file.read()
    
    # TODO: fazer com que a formatação resultante do prompt seja formatado direto no modelo
    prompt = f"""Analyze the text below and determine the most appropriate category and subcategory based on the options provided.  

        For each category, there are predefined subcategories. Select the subcategory that best matches the text. Be precise when choosing subcategories, avoiding overgeneralization.  

        Category and Subcategory options:  
        {', '.join([f"{category.name}: {', '.join(category.subcategories)}" for category in categories])}  

        If none of the given options fit, suggest a new category and subcategory that best describe the text.  

        Respond strictly in JSON format using the schema below:  
        {{
            "category": "<chosen category>",
            "subcategory": "<chosen subcategory>"
        }}  

        Text: {note_text}  

        Do not include explanations or additional text outside the JSON response. Avoid generic labels like "Uncategorized." Always provide a specific and relevant category and subcategory, or suggest new ones if necessary.
        """


    response = model.generate_content(prompt, generation_config=genai.GenerationConfig(
        response_mime_type="application/json", response_schema=OutputSchema
    ))
    print(response.text)
    return json.loads(response.text)

def map_notes():
    notes_dir = Path(INPUT_NOTES_PATH)
    
    for note_file in notes_dir.iterdir():
        if note_file.name == "metadata.json":
            continue
        
        note: Note = dumps_note(note_file)
        
        if not check_if_note_already_mapped(system_data, note):
            data = categorize_note(note, model, system_data.categories)
            
            category_name = data["category"]
            subcategory_name = data["subcategory"]
            
            category = Category()
            
            if not any(existent_category.name == category_name for existent_category in system_data.categories):
                category = Category(name=category_name)
                system_data.categories.append(category)
            else:
                category = next(category for category in system_data.categories if category.name == category_name)
                
            note.category_name = category.name
            
            if not subcategory_name in category.subcategories:
                category.subcategories.append(subcategory_name)
                
            note.subcategory_name = subcategory_name
            
            system_data.notes.append(note)

def format_dir(text: str) -> str:
    # Tornar todo o texto minúsculo
    text = text.lower()

    # Remover os acentos
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn'
    )

    # Substituir espaços por underscores
    text = text.replace(' ', '_')

    return text
        
def organize_notes_dir(notes: List[Note]):
    for note in notes:
        category_dir_name = format_dir(note.category_name)
        subcategory_dir_name = format_dir(note.subcategory_name)
        
        dest_note_dir = Path(OUTPUT_NOTES_PATH, category_dir_name, subcategory_dir_name)
        dest_note_dir.mkdir(parents=True, exist_ok=True)
        
        dest_note_path = Path(dest_note_dir, note.name)
        
        if not dest_note_path.exists():
            shutil.copy(note.path, dest_note_path)
    
    
map_notes()
organize_notes_dir(system_data.notes)
system_data.save_to_file()