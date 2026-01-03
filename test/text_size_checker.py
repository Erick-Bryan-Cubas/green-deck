import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report

# 1. Dados de Treino: Texto + Demanda -> Resultado
# Note que o MESMO texto pode ter rótulos diferentes dependendo da demanda!
data = [
    # Texto, Num_Cards_Pedidos, Label (0=OK, 1=Alucinação/Escasso)
    ("A mitocôndria produz ATP por fosforilação", 1, 0),  # OK (Cloze único)
    ("A mitocôndria produz ATP por fosforilação", 4, 1),  # Escasso (Vai inventar coisa)
    ("O sol é uma estrela", 1, 0),                        # OK
    ("O sol é uma estrela", 5, 1),                        # Escasso
    ("História do Brasil: O Brasil foi descoberto em 1500 por Pedro Álvares Cabral. Antes disso, era habitado por indígenas...", 3, 0), # OK
    ("Sim", 1, 1),                                        # Escasso (Zero info)
    ("Não sei", 1, 1),                                    # Escasso
]

df = pd.DataFrame(data, columns=['text', 'n_cards', 'label'])

# 2. Transformador Customizado para Engenharia de Features
class DensityFeatureExtractor(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self
    
    def transform(self, X):
        # X espera ser um DataFrame com colunas 'text' e 'n_cards'
        features = []
        for _, row in X.iterrows():
            text = row['text']
            n_req = row['n_cards']
            
            # Heurística simples de tokens (pode usar spaCy aqui para ser melhor)
            tokens = [w for w in text.split() if len(w) > 3] 
            n_tokens = len(tokens)
            
            # Feature principal: Razão Tokens/Cards
            # Adicionamos 1e-5 para evitar divisão por zero
            ratio = n_tokens / (n_req + 1e-5)
            
            features.append([n_tokens, n_req, ratio])
            
        return np.array(features)

# 3. Pipeline
pipe = Pipeline([
    ("extractor", DensityFeatureExtractor()),
    ("clf", LogisticRegression(class_weight='balanced')) # Balanced ajuda se tiver poucas alucinações no treino
])

# 4. Treino
X_train = df[['text', 'n_cards']]
y_train = df['label']

pipe.fit(X_train, y_train)

# 5. Teste Realista
test_cases = [
    ("A mitocôndria produz ATP", 1), # Deve ser OK (0)
    ("A mitocôndria produz ATP", 10), # Deve ser Escasso (1)
]
df_test = pd.DataFrame(test_cases, columns=['text', 'n_cards'])

preds = pipe.predict(df_test)
probs = pipe.predict_proba(df_test)

print("Teste de Sanidade:")
for (txt, n), pred, prob in zip(test_cases, preds, probs):
    status = "ALUCINAÇÃO PROVÁVEL (Bloquear)" if pred == 1 else "OK (Gerar)"
    print(f"Texto: '{txt}' | Pedidos: {n} -> {status} (Confiança de erro: {prob[1]:.2f})")
