import json
import shutil
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
model = genai.GenerativeModel("gemini-1.5-flash")

def categorize_note(note: Note, model: genai.GenerativeModel, categories: List[Category]):
    note_text = ""
    
    with open(note.path, "r") as file:
        note_text = file.read()
    
    prompt = f"""Leia o texto abaixo e determine a categoria e a subcategoria mais adequadas com base nas opções fornecidas.

        Para cada categoria, existem subcategorias possíveis. Escolha a subcategoria mais relevante para o texto ou, se nenhuma se aplicar, sugira uma nova subcategoria dentro da categoria escolhida.

        Categoria(s) e Subcategoria(s) disponíveis:
        {', '.join([f"{category.name}: {', '.join(category.subcategories)}" for category in categories])}

        Se nenhuma categoria ou subcategoria se aplicar ao texto, você pode sugerir uma nova categoria e subcategoria que melhor o descrevam.

        Responda apenas com a resposta em formato JSON, sem aspas triplas ou qualquer formatação, com a estrutura abaixo:
        {{
        "category": "<nome da categoria>",
        "subcategory": "<nome da subcategoria>"
        }}

        Texto: {note_text}

        Responda apenas com a resposta JSON, sem explicações adicionais. Não utilize 'Uncategorized' ou variações genéricas como resposta. Escolha ou sugira sempre uma categoria e subcategoria relevantes."""

    response = model.generate_content(prompt)
    print(response.text)
    return json.loads(response.text)

def map_notes():
    notes_dir = Path(INPUT_NOTES_PATH)
    
    for note_file in notes_dir.iterdir():
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