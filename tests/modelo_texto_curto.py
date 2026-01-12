import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline

# 1. Dataset de exemplo (Idealmente, você teria centenas de exemplos)
# 0 = Adequado (Longo/Rico), 1 = Curto (Escasso)
X_train = [
    "A mitocôndria é a organela responsável pela respiração celular.",
    "O algoritmo de aprendizado supervisionado requer dados rotulados.",
    "Python é uma linguagem de programação de alto nível.",
    "A revolução industrial marcou uma grande virada na história.",
    "oi",
    "teste",
    "sim",
    "não sei",
    "ok tudo bem",
    "apenas isso"
]
y_train = [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]

# 2. Criar Pipeline: Vetorização -> Classificação
# CountVectorizer conta a frequência das palavras
# MultinomialNB é excelente para contagens de texto
model = make_pipeline(
    CountVectorizer(ngram_range=(1, 1)), # Unigramas padrão
    MultinomialNB()
)

# 3. Treinar
model.fit(X_train, y_train)

# 4. Testar com novos textos
novos_textos = [
    "O sol é uma estrela",        # Curto/Médio (depende do treino)
    "ok",                         # Curto
    "A fotossíntese converte luz em energia química nas plantas." # Adequado
]

preds = model.predict(novos_textos)
probs = model.predict_proba(novos_textos)

print(f"Classes: {model.classes_} (0=Adequado, 1=Curto)")
for texto, pred, prob in zip(novos_textos, preds, probs):
    status = "CURTO" if pred == 1 else "ADEQUADO"
    confianca = prob[pred]
    print(f"'{texto}' -> {status} ({confianca:.2f})")
