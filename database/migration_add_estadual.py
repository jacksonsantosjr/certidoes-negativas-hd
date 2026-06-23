import os
import sys
import ssl

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

print("Iniciando migração de banco de dados para adicionar Certidão Estadual...")

# 1. Obter todas as empresas
empresas = supabase.table("empresas").select("id, cnpj, apelido").execute().data
print(f"Total de empresas encontradas: {len(empresas)}")

for emp in empresas:
    emp_id = emp["id"]
    apelido = emp["apelido"]
    
    # 2. Configurar em certidoes_config
    # Checa se já existe config ESTADUAL
    existing_config = supabase.table("certidoes_config") \
        .select("id") \
        .eq("empresa_id", emp_id) \
        .eq("tipo_certidao", "ESTADUAL") \
        .execute().data
        
    if not existing_config:
        print(f"[{apelido}] Criando certidoes_config para ESTADUAL...")
        supabase.table("certidoes_config").insert({
            "empresa_id": emp_id,
            "tipo_certidao": "ESTADUAL",
            "periodicidade_dias": 28,
            "obrigatoria": True
        }).execute()
    else:
        print(f"[{apelido}] Configuração ESTADUAL já existe.")
        
    # 3. Inicializar em certidoes_matriz
    existing_matriz = supabase.table("certidoes_matriz") \
        .select("id, status") \
        .eq("empresa_id", emp_id) \
        .eq("tipo_certidao", "ESTADUAL") \
        .execute().data
        
    matriz_id = None
    if not existing_matriz:
        print(f"[{apelido}] Criando certidoes_matriz para ESTADUAL...")
        res_matriz = supabase.table("certidoes_matriz").insert({
            "empresa_id": emp_id,
            "tipo_certidao": "ESTADUAL",
            "status": "Pendente",
            "ultimo_log": "Inicializado via script de migração."
        }).execute()
        if res_matriz.data:
            matriz_id = res_matriz.data[0]["id"]
    else:
        print(f"[{apelido}] Matriz ESTADUAL já existe.")
        matriz_id = existing_matriz[0]["id"]
        
    # 4. Inserir na fila de execução se ainda não estiver ativo
    if matriz_id:
        existing_fila = supabase.table("fila_execucao") \
            .select("id") \
            .eq("certidao_matriz_id", matriz_id) \
            .in_("status", ["pendente", "processando"]) \
            .execute().data
            
        if not existing_fila:
            print(f"[{apelido}] Agendando execução na fila para ESTADUAL...")
            supabase.table("fila_execucao").insert({
                "certidao_matriz_id": matriz_id,
                "status": "pendente"
            }).execute()
        else:
            print(f"[{apelido}] Já existe execução ativa na fila.")

print("\nMigração concluída com sucesso!")
