import requests
import json

def anki_request(action, params=None):
    url = 'http://127.0.0.1:8765'
    payload = {'action': action, 'version': 6}
    if params:
        payload['params'] = params
    
    response = requests.post(url, json=payload)
    data = response.json()
    
    if data.get('error'):
        raise Exception(data['error'])
    
    return data.get('result')

print('Testing AnkiConnect connection...\n')

# Test 1: Version
try:
    print('1. Testing basic connection...')
    version = anki_request('version')
    print(f'[OK] Connected! AnkiConnect version: {version}')
except Exception as e:
    print(f'[FAIL] Connection failed: {e}')
    exit(1)

# Test 2: Deck names
try:
    print('\n2. Getting deck names...')
    decks = anki_request('deckNames')
    print(f'[OK] Decks: {decks}')
except Exception as e:
    print(f'[FAIL] Failed: {e}')

# Test 3: Model names
try:
    print('\n3. Getting model names...')
    models = anki_request('modelNames')
    print(f'[OK] Models: {models}')
except Exception as e:
    print(f'[FAIL] Failed: {e}')

# Test 4: Fields for first model
try:
    print('\n4. Getting fields for models...')
    models = anki_request('modelNames')
    first_model = models[0]
    fields = anki_request('modelFieldNames', {'modelName': first_model})
    print(f'[OK] Fields for "{first_model}": {fields}')
except Exception as e:
    print(f'[FAIL] Failed: {e}')

# Test 5: Add test card
try:
    print('\n5. Adding test card...')
    note = {
        'deckName': 'Default',
        'modelName': 'Básico',
        'fields': {
            'Frente': 'Test Question',
            'Verso': 'Test Answer'
        },
        'tags': ['test']
    }
    note_id = anki_request('addNote', {'note': note})
    print(f'[OK] Card added with ID: {note_id}')
except Exception as e:
    print(f'[FAIL] Failed: {e}')

print('\n[OK] All tests completed!')
