import os
import ssl
import datetime
from dotenv import load_dotenv

# Bypass SSL
try:
    original_create_default_context = ssl.create_default_context
    def custom_create_default_context(*args, **kwargs):
        context = original_create_default_context(*args, **kwargs)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    ssl.create_default_context = custom_create_default_context
    os.environ["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
except Exception:
    pass

from supabase import create_client, Client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# IDs das certidões matriz da empresa PEDIATRIA
CERTIDOES_IDS = {
    "FGTS": "cd5bde12-c59b-452f-8896-d68fdf26bc2b",
    "FEDERAL": "909b9866-034a-4afc-8174-62c00a76759c",
    "CNDT": "58f84d30-a85c-4d8f-8916-b3ee142118b1",
    "MUNICIPAL": "79755429-c2ea-42ec-bbde-74b55a38ebb4",
    "ESTADUAL": "36ccab88-bcc8-41de-b135-f9d2d9c92ea2"
}

def main():
    print("=" * 60)
    print(" ENFILEIRANDO CERTIDÕES DA PEDIATRIA PARA PROCESSAMENTO ")
    print("=" * 60)
    
    agora = datetime.datetime.now().isoformat()
    
    for tipo, matriz_id in CERTIDOES_IDS.items():
        print(f"\nVerificando {tipo} (ID: {matriz_id})...")
        
        # Verifica se já está na fila
        existentes_res = supabase.table("fila_execucao")\
            .select("*")\
            .eq("certidao_matriz_id", matriz_id)\
            .in_("status", ["pendente", "processando"])\
            .execute()
            
        if existentes_res.data:
            job = existentes_res.data[0]
            print(f" -> Já existe um job ativo na fila: ID={job['id']} | Status={job['status']}")
            continue
            
        # Insere na fila
        print(" -> Inserindo job na fila...")
        insert_res = supabase.table("fila_execucao").insert({
            "certidao_matriz_id": matriz_id,
            "status": "pendente",
            "data_agendamento": agora
        }).execute()
        
        if insert_res.data:
            new_job = insert_res.data[0]
            print(f" -> Job criado: ID={new_job['id']}")
            
            # Atualiza status na matriz
            print(" -> Atualizando status da certidão matriz para 'Em Renovação'...")
            supabase.table("certidoes_matriz").update({
                "status": "Em Renovação",
                "ultimo_log": "Agendamento de teste solicitado via script de automação."
            }).eq("id", matriz_id).execute()
        else:
            print(" -> Falha ao criar job na fila.")

    print("\nPronto! Verifique os logs do Worker em execução para acompanhar.")

if __name__ == "__main__":
    main()
