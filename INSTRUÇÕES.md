# Instruções de Instalação e Execução do Worker Local

Este documento descreve os pré-requisitos e os passos necessários para configurar o ambiente virtual do Python na sua máquina de desenvolvimento local ou corporativa e rodar o Worker que executa a emissão automatizada das certidões negativas (CNDs).

---

## 1. Versão Recomendada do Python
Recomendamos a instalação do **Python 3.10.x** ou **Python 3.11.x**.
> [!IMPORTANT]
> A biblioteca de OCR utilizada (`ddddocr`) possui dependências pré-compiladas do runtime do ONNX que podem apresentar incompatibilidades ou exigir compilação manual complexa no Python 3.12 ou superior no Windows.

---

## 2. Bibliotecas Python Requeridas

Aqui está a lista de bibliotecas necessárias para o projeto. Elas estão mapeadas abaixo com seus respectivos propósitos:

1. **`playwright`**: Automação de navegador (Chromium/Stealth) para navegação nos portais.
2. **`ddddocr`**: Biblioteca de rede neural (CNN/RNN) para decodificação rápida de CAPTCHAs de imagem locais.
3. **`Pillow`** (PIL): Manipulação e conversão de imagens/screenshots.
4. **`supabase`**: Integração oficial com o banco de dados e fila de tarefas do Supabase.
5. **`python-dotenv`**: Carregamento automático de credenciais a partir do arquivo `.env`.
6. **`requests`**: Cliente HTTP síncrono para validações de rede auxiliares.
7. **`httpx`**: Cliente HTTP assíncrono moderno exigido pelo Supabase.
8. **`opencv-python`** (`cv2`): Biblioteca de visão computacional para tratamento de imagem do reCAPTCHA e captchas de imagem.
9. **`numpy`**: Processamento numérico e manipulação de arrays de imagens.
10. **`SpeechRecognition`**: Biblioteca de reconhecimento de fala usada no bypass de áudio do reCAPTCHA.
11. **`pydub`**: Biblioteca de processamento de áudio usada para converter áudios do CAPTCHA de `.mp3` para `.wav`.
12. **`urllib3`**: Dependência HTTP para controle de conexões de rede corporativa.

---

## 3. Passo a Passo de Configuração no Windows

Siga os comandos abaixo no seu terminal (PowerShell ou Prompt de Comando) na pasta raiz do projeto:

### Passo 1: Criar o Ambiente Virtual (Virtual Environment)
Crie uma pasta dedicada para isolar as bibliotecas do projeto da sua instalação global do Windows:
```powershell
python -m venv venv
```

### Passo 2: Ativar o Ambiente Virtual
* **No PowerShell**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
* **No Prompt de Comando (cmd)**:
  ```cmd
  .\venv\Scripts\activate.bat
  ```

### Passo 3: Atualizar o Gerenciador de Pacotes (`pip`)
```powershell
python -m pip install --upgrade pip
```

### Passo 4: Instalar as Bibliotecas Python
Instale todas as dependências necessárias de uma única vez executando:
```powershell
pip install playwright ddddocr Pillow supabase python-dotenv requests httpx opencv-python numpy SpeechRecognition pydub urllib3
```

### Passo 5: Instalar os Navegadores do Playwright
O Playwright necessita instalar os binários específicos do Chromium no seu computador. Execute:
```powershell
playwright install chromium
```

---

## 4. Requisito Adicional do Sistema: FFmpeg (Bypass de Áudio)

A biblioteca `pydub` exige que o **FFmpeg** esteja instalado no seu sistema operacional e configurado na variável de ambiente `PATH` para realizar a conversão de áudio dos desafios sonoros (necessário para quebrar o reCAPTCHA da Receita Federal e do portal Estadual).

### Como instalar o FFmpeg no Windows:
1. Baixe os executáveis pré-compilados do FFmpeg para Windows (Builds da comunidade, ex: gyan.dev ou BogoToBogo).
2. Extraia a pasta baixada em um diretório permanente (ex: `C:\ffmpeg`).
3. Adicione o caminho da pasta `bin` (ex: `C:\ffmpeg\bin`) ao `PATH` do seu sistema operacional Windows:
   - Abra o menu iniciar do Windows e busque por: *"Editar as variáveis de ambiente do sistema"*.
   - Clique no botão **Variáveis de Ambiente...** no rodapé.
   - Na lista "Variáveis do Sistema", selecione **Path** e clique em **Editar...**.
   - Clique em **Novo** e cole o caminho completo da pasta `bin` do FFmpeg (ex: `C:\ffmpeg\bin`).
   - Clique em **OK** em todas as janelas para salvar.
4. Reinicie seu terminal para recarregar as variáveis de ambiente e digite `ffmpeg -version` para testar se foi reconhecido com sucesso.

---

## 5. Como Executar o Worker Local
Uma vez concluída a instalação de todos os passos anteriores e com o arquivo `.env` configurado na raiz do projeto com as chaves corretas do Supabase, você pode iniciar o Worker local com:
```powershell
python worker.py
```
O console exibirá o log e aguardará por novas tarefas marcadas como `pendente` no painel do Supabase.
