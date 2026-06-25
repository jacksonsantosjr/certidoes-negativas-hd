import os
import ssl
import httpx

# Disable SSL verification globally for httpx (used by supabase-py)
original_init = httpx.Client.__init__
def custom_init(self, *args, **kwargs):
    kwargs['verify'] = False
    original_init(self, *args, **kwargs)
httpx.Client.__init__ = custom_init

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_errors():
    res = supabase.table("fila_execucao")\
        .select("*, certidoes_matriz(*, empresas(*))")\
        .order("data_agendamento", desc=True)\
        .limit(10)\
        .execute()
    
    print("=== LATEST TASKS IN QUEUE BY DATE ===")
    for row in res.data:
        empresa_nome = "Desconhecida"
        tipo = "Desconhecido"
        if row.get("certidoes_matriz"):
            tipo = row["certidoes_matriz"].get("tipo_certidao", "Desconhecido")
            if row["certidoes_matriz"].get("empresas"):
                empresa_nome = row["certidoes_matriz"]["empresas"].get("apelido", "Desconhecido")
        
        print(f"ID: {row['id']} | Empresa: {empresa_nome} | Tipo: {tipo} | Status: {row['status']} | Tentativas: {row['tentativas']} | Agendamento: {row['data_agendamento']}")
        print(f"  Log erro: {row['log_erro']}")
        print("-" * 50)

if __name__ == "__main__":
    check_errors()
