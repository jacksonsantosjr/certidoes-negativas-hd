import os
import sys
import ssl
import time
from datetime import datetime, timedelta

# Monkeypatch ssl to avoid issues on proxy environment
try:
    original_create_default_context = ssl.create_default_context
    def custom_create_default_context(*args, **kwargs):
        context = original_create_default_context(*args, **kwargs)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    ssl.create_default_context = custom_create_default_context
except Exception:
    pass

from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(workspace_dir, ".env")
load_dotenv(dotenv_path)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERRO: SUPABASE_URL ou SUPABASE_KEY não configurados no .env!")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Config
cnpj = "09440233000180"
empresa_id = "3f5ffd0c-6b4e-4257-8e6b-a1b80b38d9fe"  # ID de PEDIATRIA

cnds_to_sync = [
    {
        "tipo": "FEDERAL",
        "file": f"temp_federal_{cnpj}.pdf",
        "validade_dias": 180
    },
    {
        "tipo": "FGTS",
        "file": f"temp_fgts_{cnpj}.pdf",
        "validade_dias": 30
    },
    {
        "tipo": "CNDT",
        "file": f"temp_cndt_{cnpj}.pdf",
        "validade_dias": 180
    }
]

print("Iniciando sincronização dos PDFs locais para a empresa PEDIATRIA...")

for cnd in cnds_to_sync:
    tipo = cnd["tipo"]
    filename = cnd["file"]
    filepath = os.path.join(workspace_dir, filename)
    
    if not os.path.exists(filepath):
        print(f"AVISO: Arquivo local {filename} não foi encontrado em {workspace_dir}. Pulando...")
        continue
        
    print(f"\n[{tipo}] Localizado: {filename} ({os.path.getsize(filepath)} bytes)")
    
    # 1. Upload para o Supabase Storage
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    storage_path = f"{cnpj}/{tipo}_{timestamp}.pdf"
    
    try:
        with open(filepath, "rb") as f:
            supabase.storage.from_("cnds-arquivos").upload(
                path=storage_path,
                file=f.read(),
                file_options={"content-type": "application/pdf"}
            )
        print(f"[{tipo}] Upload concluído: {storage_path}")
        
        # 2. Obter URL pública
        public_url = supabase.storage.from_("cnds-arquivos").get_public_url(storage_path)
        print(f"[{tipo}] URL pública: {public_url}")
        
        # 3. Calcular datas
        data_emissao = datetime.now().strftime("%Y-%m-%d")
        data_vencimento = (datetime.now() + timedelta(days=cnd["validade_dias"])).strftime("%Y-%m-%d")
        
        # 4. Atualizar certidoes_matriz
        res_matriz = supabase.table("certidoes_matriz") \
            .update({
                "status": "Regular",
                "data_emissao": data_emissao,
                "data_vencimento": data_vencimento,
                "url_pdf": public_url,
                "ultimo_log": "Sincronizado a partir do PDF de teste local."
            }) \
            .eq("empresa_id", empresa_id) \
            .eq("tipo_certidao", tipo) \
            .execute()
            
        if res_matriz.data:
            matriz_id = res_matriz.data[0]["id"]
            print(f"[{tipo}] Matriz atualizada com sucesso.")
            
            # 5. Se houver job na fila de execução com status 'pendente' ou 'processando', atualizar para 'sucesso'
            supabase.table("fila_execucao") \
                .update({
                    "status": "sucesso",
                    "log_erro": "Sincronizado a partir do arquivo local.",
                    "updated_at": datetime.utcnow().isoformat()
                }) \
                .eq("certidao_matriz_id", matriz_id) \
                .in_("status", ["pendente", "processando"]) \
                .execute()
            print(f"[{tipo}] Fila de execução atualizada para sucesso.")
            
    except Exception as e:
        print(f"[{tipo}] ERRO ao sincronizar: {e}")

print("\nProcesso de sincronização concluído!")
