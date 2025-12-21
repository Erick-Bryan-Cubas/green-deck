import os
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_DATASETS_DOWNLOAD_PARALLELISM"] = "false"
os.environ["UNSLOTH_DISABLE_TRITON"] = "1"
os.environ["TRITON_PTXAS_PATH"] = ""
os.environ["XFORMERS_DISABLED"] = "1"

import sys
if sys.platform == 'win32':
    import multiprocessing
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"

from unsloth import FastLanguageModel
import torch
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments
import gc

def main():
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA disponível: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        total_vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"VRAM Total: {total_vram:.2f} GB")

    # ========================================================================
    # CONFIGURAÇÃO
    # ========================================================================
    
    MODEL_NAME = "unsloth/Qwen2.5-1.5B-Instruct"
    MAX_SEQ_LENGTH = 1024
    OUTPUT_DIR = "qwen_flashcard_finetuned"
    GGUF_DIR = "qwen_flashcard_gguf"
    
    BATCH_SIZE = 1
    GRADIENT_ACCUMULATION_STEPS = 8
    MAX_STEPS = 60
    LEARNING_RATE = 2e-4
    
    HF_TOKEN = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    token_kw = {"token": HF_TOKEN} if HF_TOKEN else {}
    
    # ========================================================================
    # FUNÇÕES
    # ========================================================================
    def clear_gpu():
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        gc.collect()
    
    def print_vram():
        if torch.cuda.is_available():
            used = torch.cuda.memory_allocated(0) / 1024**3
            reserved = torch.cuda.memory_reserved(0) / 1024**3
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            free = total - reserved
            print(f"🎮 VRAM: {used:.2f}GB usado | {reserved:.2f}GB reservado | {free:.2f}GB livre")
            return used, reserved, free
        return 0, 0, 0
    
    # ========================================================================
    # CARREGAR MODELO
    # ========================================================================
    print("\n" + "="*80)
    print(f"CARREGANDO {MODEL_NAME.upper()}")
    print("="*80)
    print(f"⚙️  Modo: PyTorch puro (Triton/Xformers DESABILITADOS)")
    
    clear_gpu()
    
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
        device_map="auto",
        trust_remote_code=True,
        **token_kw,
    )
    
    print("✓ Modelo carregado!")
    print_vram()
    
    # ========================================================================
    # CONFIGURAR LoRA
    # ========================================================================
    print("\n" + "="*80)
    print("CONFIGURANDO LoRA")
    print("="*80)
    
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj"
        ],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
        use_rslora=False,
        loftq_config=None,
    )
    
    print("✓ LoRA configurado!")
    print_vram()
    
    # ========================================================================
    # CARREGAR DATASET
    # ========================================================================
    print("\n" + "="*80)
    print("CARREGANDO DATASET")
    print("="*80)
    
    dataset = load_dataset(
        "json",
        data_files="training_data_formatted.jsonl",
        split="train",
    )
    
    num_examples = len(dataset)
    print(f"✓ {num_examples} exemplos carregados")
    
    if num_examples > 0:
        print(f"\n📋 Exemplo (primeiros 200 chars):")
        print(dataset[0]['text'][:200] + "...")
    
    # ========================================================================
    # CHUNKING: Quebrar textos longos
    # ========================================================================
    print("\n" + "="*80)
    print(f"CHUNKING: QUEBRANDO TEXTOS EM BLOCOS DE ATÉ {MAX_SEQ_LENGTH} TOKENS")
    print("="*80)
    
    def chunk_text(example):
        """Quebra textos longos em chunks menores"""
        text = example['text']
        # Aproximação: 4 chars = 1 token
        max_chars = MAX_SEQ_LENGTH * 4
        
        chunks = []
        for i in range(0, len(text), max_chars):
            chunk = text[i:i + max_chars]
            if len(chunk) > 100:  # Ignorar chunks muito pequenos
                chunks.append({"text": chunk})
        
        return chunks if chunks else [{"text": text}]
    
    # Aplicar chunking
    chunked_data = []
    for example in dataset:
        chunked_data.extend(chunk_text(example))
    
    # Criar novo dataset
    from datasets import Dataset
    dataset = Dataset.from_list(chunked_data)
    
    print(f"✓ Dataset após chunking: {len(dataset)} chunks")
    
    # ========================================================================
    # CONFIGURAR TREINAMENTO
    # ========================================================================
    print("\n" + "="*80)
    print("CONFIGURANDO TREINAMENTO")
    print("="*80)
    
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        max_steps=MAX_STEPS,
        warmup_steps=5,
        learning_rate=LEARNING_RATE,
        lr_scheduler_type="cosine",
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        optim="adamw_8bit",
        gradient_checkpointing=True,
        weight_decay=0.01,
        max_grad_norm=1.0,
        logging_steps=10,
        logging_first_step=True,
        save_strategy="steps",
        save_steps=30,
        save_total_limit=1,
        seed=42,
        data_seed=42,
        report_to="none",
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        eval_strategy="no",
    )
    
    print(f"  Modelo: {MODEL_NAME}")
    print(f"  Exemplos (chunks): {len(dataset)}")
    print(f"  Batch size: {BATCH_SIZE}")
    print(f"  Grad acc: {GRADIENT_ACCUMULATION_STEPS} (batch efetivo = {BATCH_SIZE * GRADIENT_ACCUMULATION_STEPS})")
    print(f"  Max steps: {MAX_STEPS}")
    print(f"  Max seq length: {MAX_SEQ_LENGTH}")
    print(f"  Triton/Xformers: DESABILITADOS (modo seguro Windows)")
    print_vram()
    
    # ========================================================================
    # CRIAR TRAINER (API ATUALIZADA)
    # ========================================================================
    print("\n🔧 Criando trainer...")
    
    # ✅ API corrigida - SFTTrainer recente não aceita mais 'tokenizer' diretamente
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        packing=False,
        tokenizer=tokenizer,  # ✅ Volta o tokenizer, mas sem dataset_kwargs
    )
    
    print("✓ Trainer criado!")
    
    # ========================================================================
    # TREINAR
    # ========================================================================
    print("\n" + "="*80)
    print("🚀 INICIANDO TREINAMENTO")
    print("="*80)
    print(f"⏱️  Tempo estimado: 5-8 minutos")
    print("="*80)
    
    try:
        trainer.train()
        print("\n✅ Treinamento concluído!")
        
    except RuntimeError as e:
        error_msg = str(e).lower()
        
        if "out of memory" in error_msg:
            print(f"\n❌ MEMÓRIA INSUFICIENTE!")
            print(f"\n💡 SOLUÇÕES:")
            print(f"  1. Reduza MAX_SEQ_LENGTH para 768")
            print(f"  2. Aumente GRADIENT_ACCUMULATION_STEPS para 16")
        elif "compiler" in error_msg or "triton" in error_msg:
            print(f"\n❌ ERRO DE COMPILADOR (ainda)!")
            print(f"Isso não deveria acontecer no Developer Command Prompt...")
        else:
            print(f"❌ Erro: {e}")
        raise
    
    except KeyboardInterrupt:
        print("\n⚠️ Interrompido pelo usuário")
    
    # ========================================================================
    # SALVAR MODELO
    # ========================================================================
    print("\n" + "="*80)
    print("💾 SALVANDO MODELO")
    print("="*80)
    
    clear_gpu()
    
    try:
        print("Salvando modelo fine-tuned...")
        model.save_pretrained(OUTPUT_DIR)
        tokenizer.save_pretrained(OUTPUT_DIR)
        print(f"✓ Salvo em: {OUTPUT_DIR}/")
    except Exception as e:
        print(f"❌ Erro ao salvar: {e}")
    
    # ========================================================================
    # EXPORTAR GGUF
    # ========================================================================
    print("\n" + "="*80)
    print("🔧 EXPORTANDO GGUF")
    print("="*80)
    
    clear_gpu()
    
    try:
        print("Convertendo para GGUF q4_k_m...")
        print("⏱️  Isso pode levar 2-3 minutos...")
        
        model.save_pretrained_gguf(
            GGUF_DIR,
            tokenizer,
            quantization_method="q4_k_m"
        )
        print(f"✓ GGUF exportado: {GGUF_DIR}/")
    except Exception as e:
        print(f"⚠️ Erro ao exportar: {e}")
    
    # ========================================================================
    # INSTRUÇÕES FINAIS
    # ========================================================================
    print("\n" + "="*80)
    print("✅ CONCLUÍDO!")
    print("="*80)
    
    used, reserved, free = print_vram()
    
    print(f"""
📋 Próximos Passos para Ollama:

1. Navegar até o diretório:
   cd {GGUF_DIR}

2. Criar Modelfile:
   echo FROM unsloth.Q4_K_M.gguf > Modelfile

3. Adicionar system prompt:
   echo SYSTEM "Você é especialista em criar flashcards SuperMemo." >> Modelfile

4. Criar modelo no Ollama:
   ollama create qwen-flashcard -f Modelfile

5. Testar:
   ollama run qwen-flashcard "Gere um flashcard sobre Python"

📊 Estatísticas:
  Chunks treinados: {len(dataset)}
  Steps: {MAX_STEPS}
  VRAM usada: {used:.2f}GB / 4.00GB

🎉 Modelo pronto para o Ollama!
""")
    
    clear_gpu()


if __name__ == '__main__':
    if sys.platform == 'win32':
        import multiprocessing
        multiprocessing.freeze_support()
    
    main()
