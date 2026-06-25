import sys
import os
import time
import subprocess
import requests
from playwright.sync_api import sync_playwright
import speech_recognition as sr
from pydub import AudioSegment
import numpy as np
import cv2
import ddddocr
from PIL import Image

def get_chrome_path():
    paths = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return "chrome.exe"

def limpar_chrome_rpa():
    import subprocess
    try:
        # Finaliza qualquer processo chrome.exe que contenha a porta 9222 na linha de comando
        subprocess.run(
            'wmic process where "name=\'chrome.exe\' and CommandLine like \'%remote-debugging-port=9222%\'" call terminate',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(1.0)
    except Exception:
        pass


class PersistentBrowser:
    def __init__(self, context):
        self.context = context
    def close(self):
        try:
            self.context.close()
        except Exception:
            pass


class NetworkError(Exception):
    pass


def verificar_erro_rede(page):
    try:
        body_text = page.locator("body").inner_text().lower()
        if "err_empty_response" in body_text or "não está funcionando" in body_text or "nenhum dado foi enviado" in body_text:
            raise NetworkError("Erro de rede detectado (ERR_EMPTY_RESPONSE / Página não está funcionando).")
    except NetworkError:
        raise
    except Exception:
        pass


def goto_with_retry(page, url, max_retries=3, timeout=30000):
    for i in range(1, max_retries + 1):
        try:
            print(f"Acessando {url} (tentativa {i}/{max_retries})...")
            response = page.goto(url, timeout=timeout)
            if response and response.status < 400:
                body_text = page.locator("body").inner_text().lower()
                if "err_empty_response" in body_text or "não está funcionando" in body_text or "nenhum dado foi enviado" in body_text:
                    raise NetworkError("Erro de página vazia no corpo (ERR_EMPTY_RESPONSE).")
                return response
            else:
                raise Exception(f"Código de status HTTP inválido: {response.status if response else 'Sem Resposta'}")
        except Exception as e:
            print(f"Erro ao acessar {url} (tentativa {i}/{max_retries}): {e}")
            if i < max_retries:
                time.sleep(3)
            else:
                raise e


def iniciar_e_conectar_chrome(p, user_data_dir, headless=False):
    print(f"Iniciando Playwright Chromium Stealth (headless={headless}, user_data_dir={user_data_dir})")
    
    # Garante o encerramento de processos travados
    limpar_chrome_rpa()
    
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    
    context = p.chromium.launch_persistent_context(
        user_data_dir,
        headless=headless,
        user_agent=user_agent,
        viewport={"width": 1280, "height": 800},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        accept_downloads=True
    )
    
    # Injeta propriedades stealth para evitar detecção automatizada
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        window.chrome = { runtime: {} };
    """)
    
    browser = PersistentBrowser(context)
    return browser, context

def testar_federal(cnpj):
    print("\n--- TESTANDO CND FEDERAL (Receita Federal) ---")
    url = "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj"
    print(f"Acessando: {url}")
    
    user_data_dir = os.path.abspath("./user_data_receita")
    with sync_playwright() as p:
        browser, context = iniciar_e_conectar_chrome(p, user_data_dir, headless=False)
        page = context.new_page()
        
        try:
            time.sleep(0.2)
            page.goto(url)
            
            # Seletor do CNPJ (tenta name do input real, placeholder, e fallback do usuário)
            cnpj_selector = 'input[name="niContribuinte"]'
            try:
                page.wait_for_selector(cnpj_selector, timeout=15000)
            except Exception:
                cnpj_selector = 'input[placeholder="Informe o CNPJ"]'
                try:
                    page.wait_for_selector(cnpj_selector, timeout=5000)
                except Exception:
                    cnpj_selector = 'xpath=//*[@id="id3f4c9ab5e7e9d4"]'
                    page.wait_for_selector(cnpj_selector, timeout=10000)
                
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            
            # Adiciona delay antes de interagir com o campo
            time.sleep(1.0)
            page.focus(cnpj_selector)
            time.sleep(0.5)
            page.click(cnpj_selector)
            time.sleep(0.5)
            
            # Digita o CNPJ com delay entre as teclas
            page.type(cnpj_selector, cnpj_limpo, delay=60)
            print("CNPJ preenchido.")
            time.sleep(0.5)
            
            # Dispara evento de blur/mudança de foco (pressionando Tab)
            page.press(cnpj_selector, "Tab")
            time.sleep(0.5)
            
            # Clica no botão de aceitar cookies se estiver visível para não atrapalhar
            try:
                btn_cookies = 'button:has-text("Aceitar")'
                if page.locator(btn_cookies).is_visible():
                    time.sleep(1.0)
                    page.click(btn_cookies)
                    print("Cookies aceitos.")
                    time.sleep(1.5)
            except:
                pass
            
            print("Aguardando o carregamento dos componentes da página...")
            time.sleep(2.0)
            
            btn_selector = 'button:has-text("Emitir Certidão")'
            try:
                page.wait_for_selector(btn_selector, timeout=10000)
            except Exception:
                # Fallback para o xpath fornecido
                btn_selector = 'xpath=/html/body/app-root/mf-portal-layout/portal-main-layout/div/main/ng-component/ng-component/app-coleta-parametros-pj/app-coleta-parametros-template/form/div[2]/div[2]/button[2]'
                page.wait_for_selector(btn_selector, timeout=5000)
                
            time.sleep(0.5)
            page.hover(btn_selector)
            time.sleep(0.3)
            page.click(btn_selector)
            print("Botão Emitir Certidão clicado.")
            time.sleep(1.0)
            
            # Trata o caso de certidão válida já existente (Modal)
            try:
                # O usuário informou o xpath exato do botão "Emitir Nova Certidão"
                btn_xpath = 'xpath=/html/body/modal-container/div[2]/div/div[3]/button[2]'
                btn_texto = 'button:has-text("Emitir Nova Certidão")'
                
                # Aguardamos pelo modal ou botão (espera um dos dois)
                try:
                    page.wait_for_selector('modal-container', timeout=15000)
                except:
                    page.wait_for_selector(btn_xpath, timeout=5000)
                    
                time.sleep(1.0)
                
                if page.locator(btn_xpath).is_visible():
                    page.hover(btn_xpath)
                    time.sleep(0.5)
                    page.click(btn_xpath)
                    print(f"Modal tratado clicando no xpath: {btn_xpath}")
                elif page.locator(btn_texto).is_visible():
                    page.hover(btn_texto)
                    time.sleep(0.5)
                    page.click(btn_texto)
                    print(f"Modal tratado clicando no texto: {btn_texto}")
                else:
                    # Fallback final tentando forçar clique se existir no DOM
                    page.click(btn_xpath, force=True, timeout=5000)
                    print("Modal tratado com clique forçado no xpath.")
                
                time.sleep(1.0)
            except Exception as e:
                print(f"Modal de certidão válida não apareceu ou erro ao clicar: {e}")
            
            # Tratamento de Erros / Verificação do Documento
            sucesso_selector = "iframe:not([src*='hcaptcha']):not([src*='google']), embed, object, [href*='.pdf']"
            erro_selector = ".alert, .error, .message-error, .mensagem-erro, #mensagemErro, .br-message, .feedback, .invalid-feedback"
            
            # Se for a primeira emissão (nunca solicitada antes), a página pode exibir o link de download alternativo direto
            link_download_alternativo = 'a:has-text("download do documento PDF da certidão")'
            if page.locator(link_download_alternativo).is_visible():
                print("Página de emissão de primeira certidão detectada (sem PDF embutido). Clicando no link alternativo...")
                try:
                    temp_pdf_path = f"temp_federal_{cnpj}.pdf"
                    with page.expect_download(timeout=10000) as download_info:
                        page.click(link_download_alternativo)
                    download = download_info.value
                    download.save_as(temp_pdf_path)
                    print(f"PDF real da certidão baixado e salvo com sucesso em: {temp_pdf_path}")
                    # Injeta elemento de sucesso no DOM para que o sucesso_selector seja satisfeito
                    page.evaluate('() => { const embed = document.createElement("embed"); embed.id = "mock-success-pdf"; document.body.appendChild(embed); }')
                except Exception as d_err:
                    print(f"Erro ao baixar o PDF pelo link de download alternativo: {d_err}")
            
            print("Aguardando resultado (sucesso ou erro)...")
            try:
                page.wait_for_selector(f"{sucesso_selector}, {erro_selector}, div:has-text('insuficientes')", timeout=5000)
            except Exception:
                # Se der timeout, faz uma verificação rápida de textos de erro no body
                body_text = page.locator("body").inner_text()
                if "insuficientes" in body_text or "Não foi possível concluir" in body_text:
                    pass
                else:
                    raise
            
            # 1. Verifica erros por seletores de classes/containers
            elementos_erro = page.query_selector_all(erro_selector)
            for el in elementos_erro:
                if el.is_visible():
                    erro_msg = el.inner_text().strip()
                    if erro_msg:
                        raise Exception(f"Erro no portal da Receita Federal: {erro_msg}")
            
            # 2. Verifica erros por palavras-chave textuais na página inteira
            body_text = page.locator("body").inner_text()
            if "insuficientes" in body_text:
                # Tenta obter o texto específico do elemento que contém a mensagem
                msg_el = page.query_selector("div:has-text('insuficientes'), p:has-text('insuficientes'), span:has-text('insuficientes')")
                erro_msg = msg_el.inner_text().strip() if msg_el else "As informações disponíveis na Receita Federal sobre o contribuinte são insuficientes para emitir a certidão pela Internet."
                if len(erro_msg) > 300:
                    erro_msg = "As informações disponíveis na Receita Federal sobre o contribuinte são insuficientes para emitir a certidão pela Internet."
                
                print(f"\n[AVISO]: {erro_msg}")
                # Salva a tela em PDF para verificação do teste
                img_path = "resultado_federal_insuficiente.png"
                pdf_path = f"temp_federal_{cnpj}_insuficiente.pdf"
                page.screenshot(path=img_path, full_page=True)
                try:
                    from PIL import Image
                    img = Image.open(img_path).convert("RGB")
                    img.save(pdf_path, "PDF")
                    print(f"Tela de aviso salva em PDF: {pdf_path}")
                except Exception as pdf_err:
                    print(f"Erro ao converter screenshot para PDF: {pdf_err}")
                
                raise Exception(erro_msg)
                
            if "Não foi possível concluir" in body_text:
                raise Exception("Erro no portal da Receita Federal: Não foi possível concluir a ação para o contribuinte informado. Por favor, tente novamente dentro de alguns minutos.")
            
            if page.query_selector(sucesso_selector):
                print("Certidão emitida com sucesso!")
                page.screenshot(path="resultado_federal.png", full_page=True)
                print("Print screen salvo como 'resultado_federal.png'")
            else:
                raise Exception("Resultado desconhecido após clique de emissão.")
            
        except Exception as e:
            print(f"Erro no teste Federal: {e}")
            try:
                page.screenshot(path="federal_error.png")
                print("Screenshot do erro salvo em 'federal_error.png'")
            except:
                pass
        finally:
            if 'page' in locals():
                try:
                    # Envia comando CDP para fechar toda a instância do navegador
                    client = page.context.new_cdp_session(page)
                    client.send("Browser.close")
                except:
                    pass
                page.close()
            
            if 'context' in locals():
                try: context.close()
                except: pass
                
            if 'browser' in locals():
                try: browser.close()
                except: pass
                
            print("Instância do navegador fechada.")

def testar_fgts(cnpj, uf="SP"):
    print("\n--- TESTANDO CND FGTS (Caixa CRF) ---")
    url = "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"
    print(f"Acessando: {url}")
    
    with sync_playwright() as p:
        # Iniciamos em modo headful (com janela) conforme esperado para testes interativos
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto(url)
            cnpj_selector = 'xpath=//*[@id="mainForm:txtInscricao1"]'
            uf_selector = 'xpath=//*[@id="mainForm:uf"]'
            btn_selector = 'xpath=//*[@id="mainForm:btnConsultar"]'
            
            page.wait_for_selector(cnpj_selector, timeout=20000)
            
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            page.fill(cnpj_selector, cnpj_limpo)
            print("CNPJ preenchido.")
            
            page.wait_for_selector(uf_selector, timeout=10000)
            page.select_option(uf_selector, value=uf)
            print(f"UF '{uf}' selecionada.")
            
            print("Clicando em Consultar...")
            page.wait_for_selector(btn_selector, timeout=10000)
            page.click(btn_selector)
            
            # Tratamento de Erros / Verificação do Documento
            sucesso_selector = '[id="mainForm:j_id76"]'
            erro_selector = ".msgErro, .erro, [id='mainForm:mensagens']"
            
            page.wait_for_selector(f"{sucesso_selector}, {erro_selector}", timeout=20000)
            
            # Verifica se houve algum erro reportado na tela
            elementos_erro = page.query_selector_all(erro_selector)
            for el in elementos_erro:
                if el.is_visible():
                    erro_msg = el.inner_text().strip()
                    if erro_msg:
                        raise Exception(f"Erro no portal da Caixa (FGTS): {erro_msg}")
            
            # Se a empresa estiver regular, segue o fluxo de telas até a certidão
            if page.query_selector(sucesso_selector):
                print("Empresa regular no FGTS. Navegando para o certificado...")
                page.click(sucesso_selector)
                
                # 2. Clica em 'Visualizar'
                btn_visualizar = '[id="mainForm:btnVisualizar"]'
                page.wait_for_selector(btn_visualizar, timeout=15000)
                page.click(btn_visualizar)
                print("Visualizar clicado.")
                
                # 3. Aguarda o botão 'Imprimir' aparecer e clica nele
                btn_imprimir = '[id="mainForm:btImprimir4"]'
                page.wait_for_selector(btn_imprimir, timeout=15000)
                print("Certidão carregada na tela.")
                
                # Mock window.print para evitar bloquear a thread com a janela nativa do Chrome
                page.evaluate("window.print = () => { console.log('window.print simulado com sucesso'); }")
                page.click(btn_imprimir)
                print("Botão Imprimir clicado (diálogo nativo contornado).")
                
                # Emula mídia de impressão para aplicar estilos de impressão (@media print) que escondem os botões nativamente
                page.emulate_media(media="print")
                
                # Esconde manualmente quaisquer botões ou elementos indesejados (como "Voltar" e "Imprimir") para garantir um PDF 100% limpo
                page.evaluate("""
                    document.querySelectorAll('input[type="submit"], input[type="button"], button, .no-print, [id*="btnVoltar"], [id*="btImprimir"]').forEach(el => el.style.display = 'none');
                """)
                
                # 4. Tira um print screen do certificado formatado para impressão
                page.screenshot(path="resultado_fgts.png", full_page=True)
                print("Print screen salvo como 'resultado_fgts.png'")
                
                # Restaura a visualização de tela
                page.emulate_media(media="screen")
                
                # 5. Gera o PDF real utilizando a biblioteca Pillow a partir do screenshot
                temp_pdf_path = f"temp_fgts_{cnpj}.pdf"
                try:
                    from PIL import Image
                    img = Image.open("resultado_fgts.png").convert("RGB")
                    img.save(temp_pdf_path, "PDF")
                    print(f"PDF real gerado e salvo com sucesso em {temp_pdf_path}")
                except Exception as pdf_err:
                    print(f"Erro ao converter screenshot para PDF: {pdf_err}")
                    # Fallback para escrita de mock caso Pillow falhe
                    with open(temp_pdf_path, "wb") as f:
                        f.write(b"MOCK PDF CONTENT - ERROR CONVERTING")
            else:
                raise Exception("Não foi possível localizar o link do CRF após a consulta.")
            
        except Exception as e:
            print(f"Erro no teste FGTS: {e}")
        finally:
            browser.close()

def testar_cndt(cnpj):
    print("\n--- TESTANDO CNDT (Trabalhista - TST) ---")
    url = "https://cndt-certidao.tst.jus.br/inicio.faces"
    print(f"Acessando: {url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto(url)
            
            # Clica no botão inicial 'Emitir Certidão'
            btn_inicial = 'xpath=//*[@id="corpo"]/div/div[2]/input[1]'
            page.wait_for_selector(btn_inicial, timeout=20000)
            page.click(btn_inicial)
            print("Botão inicial de emissão clicado.")
            
            # Preenche o CNPJ
            cnpj_selector = 'xpath=//*[@id="gerarCertidaoForm:cpfCnpj"]'
            page.wait_for_selector(cnpj_selector, timeout=20000)
            page.fill(cnpj_selector, cnpj)
            print("CNPJ preenchido.")
            
            print("\n[AÇÃO MANUAL NECESSÁRIA]: Observe o CAPTCHA de 6 caracteres na tela do navegador.")
            # Aguarda 3 segundos para que a imagem do CAPTCHA base64 seja totalmente carregada na tela
            time.sleep(3)
            page.screenshot(path="captcha_cndt.png")
            print("Print screen do CAPTCHA salvo em 'captcha_cndt.png'")
            captcha_val = input("Digite o CAPTCHA aqui no terminal e pressione ENTER: ").strip()
            
            # Preenche o captcha diretamente
            captcha_selector = '[id="idCampoResposta"]'
            page.fill(captcha_selector, captcha_val, timeout=5000)
            print("CAPTCHA preenchido. Clicando em Emitir Certidão...")
            
            btn_emitir = '[id="gerarCertidaoForm:btnEmitirCertidao"]'
            page.wait_for_selector(btn_emitir, timeout=10000)
            
            # Tratamento de Erros / Verificação do Documento
            erro_selector = ".mensagem-erro, .erro, .alert, #messages, ul.erro, [id='gerarCertidaoForm:mensagens'], #mensagens, .erros, [id*='areaMensagemErro']"
            
            # Clica no botão de emitir e aguarda pelo download ou por um erro na página
            try:
                with page.expect_download(timeout=25000) as download_info:
                    page.click(btn_emitir)
                
                # Se o download iniciou com sucesso
                download = download_info.value
                temp_pdf_path = f"temp_cndt_{cnpj}.pdf"
                download.save_as(temp_pdf_path)
                print(f"PDF real da certidão CNDT salvo com sucesso em {temp_pdf_path}")
                
                # Captura de tela para confirmação
                page.screenshot(path="resultado_cndt.png")
                print("Print screen salvo como 'resultado_cndt.png'")
                
            except Exception as d_err:
                # Se der timeout ou erro no download, verifica se houve erro exibido na tela
                print("Download automático não iniciou. Verificando possíveis erros na página...")
                elementos_erro = page.query_selector_all(erro_selector)
                erro_msg = ""
                for el in elementos_erro:
                    if el.is_visible():
                        txt = el.inner_text().strip()
                        if txt:
                            erro_msg = txt
                            break
                if erro_msg:
                    raise Exception(f"Erro no portal CNDT: {erro_msg}")
                else:
                    raise Exception(f"Falha ao iniciar download ou erro não identificado: {d_err}")
            
        except Exception as e:
            print(f"Erro no teste CNDT: {e}")
            try:
                page.screenshot(path="cndt_error.png")
                print("Screenshot do erro CNDT salvo em 'cndt_error.png'")
            except:
                pass
        finally:
            browser.close()

def resolver_recaptcha(page):
    print("Iniciando resolução automática do reCAPTCHA...")
    
    # Adiciona a pasta bin do FFmpeg ao PATH para que o pydub a encontre
    import os
    ffmpeg_path = r"C:\Users\jackson.junior\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"
    if os.path.exists(ffmpeg_path) and ffmpeg_path not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + ffmpeg_path
        
    try:
        # 1. Encontra o iframe do checkbox do reCAPTCHA (usando apenas o src do anchor para evitar conflito com o bframe)
        frame_selector = 'iframe[src*="anchor"]'
        page.wait_for_selector(frame_selector, timeout=15000)
        frame = page.frame_locator(frame_selector)
        
        # 2. Clica no checkbox
        anchor = frame.locator('#recaptcha-anchor')
        anchor.click()
        print("Checkbox do reCAPTCHA clicado.")
        
        # 3. Aguarda um momento para ver se o CAPTCHA foi resolvido automaticamente
        time.sleep(3.0)
        if anchor.get_attribute('aria-checked') == 'true':
            print("reCAPTCHA resolvido automaticamente (sem desafio de imagem/áudio)!")
            return True
            
        print("Desafio de segurança apresentado. Iniciando bypass via áudio...")
        
        # 4. Localiza o iframe do desafio (bframe)
        bframe_selector = 'iframe[src*="bframe"]'
        page.wait_for_selector(bframe_selector, timeout=10000)
        bframe = page.frame_locator(bframe_selector)
        
        # 5. Clica no botão de áudio
        audio_btn = bframe.locator('#recaptcha-audio-button')
        audio_btn.wait_for(state="visible", timeout=5000)
        audio_btn.click()
        print("Botão de áudio clicado.")
        time.sleep(2.0)
        
        # 6. Tenta obter o link de download do áudio (usando tanto link de download quanto tag audio-source)
        audio_url = ""
        try:
            # Espera até que um dos seletores do áudio esteja disponível
            bframe.locator('.rc-audiochallenge-download-link, #audio-source').first.wait_for(state="attached", timeout=6000)
            
            download_link = bframe.locator('.rc-audiochallenge-download-link')
            audio_source = bframe.locator('#audio-source')
            
            if download_link.is_visible():
                audio_url = download_link.get_attribute('href')
            elif audio_source.count() > 0:
                audio_url = audio_source.get_attribute('src')
                
            if not audio_url:
                raise Exception("Não foi possível extrair a URL do áudio.")
        except Exception as sel_err:
            body_text = bframe.locator('body').inner_text()
            if "tente novamente mais tarde" in body_text.lower() or "blocked" in body_text.lower() or "solicitações automatizadas" in body_text.lower() or "automated queries" in body_text.lower():
                raise Exception("Bloqueio de reCAPTCHA detectado pelo Google (limite de requisições excedido). Tente novamente mais tarde.")
            raise Exception(f"Falha ao carregar desafio de áudio: {sel_err}")
            
        print(f"URL do áudio obtido: {audio_url}")
        
        # 7. Faz o download do áudio MP3 (desabilitando verificação de certificado SSL por conta de proxies corporativos)
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(audio_url, timeout=15, verify=False)
        mp3_path = "temp_captcha.mp3"
        wav_path = "temp_captcha.wav"
        
        with open(mp3_path, "wb") as f:
            f.write(response.content)
            
        # 8. Converte MP3 para WAV
        from pydub import AudioSegment
        sound = AudioSegment.from_mp3(mp3_path)
        sound.export(wav_path, format="wav")
        print("Áudio convertido para WAV.")
        
        # 9. Transcreve o áudio usando SpeechRecognition
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = r.record(source)
            
        text = r.recognize_google(audio_data, language="en-US")
        print(f"Texto transcrito pelo Google Speech API: '{text}'")
        
        # Limpa os arquivos temporários
        try:
            os.remove(mp3_path)
            os.remove(wav_path)
        except:
            pass
            
        # 10. Insere o texto transcrito
        response_input = bframe.locator('#audio-response')
        response_input.fill(text)
        time.sleep(0.5)
        
        # 11. Clica no botão de verificar
        verify_btn = bframe.locator('#recaptcha-verify-button')
        verify_btn.click()
        print("Botão de verificação clicado.")
        time.sleep(3.0)
        
        # 12. Verifica se funcionou
        if anchor.get_attribute('aria-checked') == 'true':
            print("reCAPTCHA resolvido com sucesso via áudio!")
            return True
        else:
            print("Falha na validação do áudio do reCAPTCHA.")
            return False
            
    except Exception as e:
        print(f"Erro ao resolver reCAPTCHA: {e}")
        return False

def testar_estadual_sp(cnpj):
    print("\n--- TESTANDO CND ESTADUAL SP ---")
    url = "https://www10.fazenda.sp.gov.br/CertidaoNegativaDeb/Pages/EmissaoCertidaoNegativa.aspx"
    print(f"Acessando: {url}")
    
    user_data_dir = os.path.abspath("./user_data_sp")
    
    with sync_playwright() as p:
        browser, context = iniciar_e_conectar_chrome(p, user_data_dir, headless=False)
        page = context.new_page()
        
        try:
            page.goto(url)
            
            # Selecionar o elemento xPath //*[@id="MainContent_cnpjradio"]
            cnpj_radio_xpath = 'xpath=//*[@id="MainContent_cnpjradio"]'
            page.wait_for_selector(cnpj_radio_xpath, timeout=20000)
            page.click(cnpj_radio_xpath)
            print("Opção CNPJ selecionada.")
            
            # Preencher o CNPJ no campo xPath //*[@id="MainContent_txtDocumento"]
            cnpj_input_xpath = 'xpath=//*[@id="MainContent_txtDocumento"]'
            page.wait_for_selector(cnpj_input_xpath, timeout=10000)
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            page.fill(cnpj_input_xpath, cnpj_limpo)
            print("CNPJ preenchido.")
            
            # Resolver o CAPTCHA
            recaptcha_resolvido = resolver_recaptcha(page)
            if not recaptcha_resolvido:
                print("\n[AVISO]: A resolução automática do reCAPTCHA falhou.")
                print("Por favor, resolva o reCAPTCHA manualmente na tela do navegador.")
                input("Pressione [ENTER] aqui no terminal depois de resolver o CAPTCHA para continuar... ")
            
            # Clicar no botão "EMITIR" cujo xPath é o //*[@id="MainContent_btnPesquisar"]
            btn_emitir_xpath = 'xpath=//*[@id="MainContent_btnPesquisar"]'
            page.wait_for_selector(btn_emitir_xpath, timeout=10000)
            page.click(btn_emitir_xpath)
            print("Botão EMITIR clicado. Aguardando a próxima página...")
            
            # Na tela seguinte, localizar o botão "IMPRIMIR" e salvar a certidão como PDF
            btn_imprimir_xpath = 'xpath=//*[@id="MainContent_btnImpressao"]'
            try:
                page.wait_for_selector(btn_imprimir_xpath, timeout=20000)
                print("Sucesso! Botão IMPRIMIR encontrado. Iniciando salvamento do PDF...")
                
                # Mock window.print para evitar bloquear a thread caso dispare o diálogo de impressão nativo
                page.evaluate("window.print = () => { console.log('window.print simulado com sucesso'); }")
                
                temp_pdf_path = f"temp_estadual_sp_{cnpj}.pdf"
                pdf_salvo = False
                
                try:
                    # Tenta capturar se o botão dispara um download de arquivo direto
                    with page.expect_download(timeout=5000) as download_info:
                        page.click(btn_imprimir_xpath)
                    download = download_info.value
                    download.save_as(temp_pdf_path)
                    print(f"PDF baixado com sucesso via download em: {temp_pdf_path}")
                    page.screenshot(path="resultado_estadual_sp.png")
                    pdf_salvo = True
                except Exception:
                    # Se não gerou um download direto, tiramos screenshot formatado para impressão
                    pass
                
                if not pdf_salvo:
                    # Emula mídia de impressão para carregar estilos de impressão da página
                    page.emulate_media(media="print")
                    
                    # Oculta os botões de controle na página para não saírem no PDF impresso
                    page.evaluate("""
                        document.querySelectorAll('input[type="submit"], input[type="button"], button, .no-print, [id*="btnImpressao"], [id*="btnVoltar"]').forEach(el => el.style.display = 'none');
                    """)
                    
                    # Clica no botão para disparar scripts internos (caso existam)
                    try:
                        page.click(btn_imprimir_xpath, timeout=2000)
                    except:
                        pass
                    
                    screenshot_path = "resultado_estadual_sp.png"
                    page.screenshot(path=screenshot_path, full_page=True)
                    print(f"Print screen do certificado salvo como '{screenshot_path}'")
                    
                    # Restaura a mídia para exibição em tela normal
                    page.emulate_media(media="screen")
                    
                    # Converte o screenshot para PDF real usando Pillow
                    try:
                        from PIL import Image
                        img = Image.open(screenshot_path).convert("RGB")
                        img.save(temp_pdf_path, "PDF")
                        print(f"PDF real gerado e salvo com sucesso em: {temp_pdf_path}")
                        pdf_salvo = True
                    except Exception as pdf_err:
                        print(f"Erro ao converter screenshot para PDF: {pdf_err}")
                
            except Exception as e:
                print(f"Erro: Botão IMPRIMIR não encontrado ou falha no salvamento. Detalhes: {e}")
                page.screenshot(path="sp_error.png")
                print("Screenshot da tela de erro salva em 'sp_error.png'")
                
            # Aguarde 1 segundo
            time.sleep(1)
            
        except Exception as e:
            print(f"Erro no teste Estadual SP: {e}")
            try:
                page.screenshot(path="sp_error.png")
                print("Screenshot do erro salvo em 'sp_error.png'")
            except:
                pass
        finally:
            if 'page' in locals():
                try:
                    client = page.context.new_cdp_session(page)
                    client.send("Browser.close")
                except:
                    pass
                try: page.close()
                except: pass
            if 'context' in locals():
                try: context.close()
                except: pass
            if 'browser' in locals():
                try: browser.close()
                except: pass
            print("Instância do navegador fechada.")


def obter_input_interativo(prompt, page, timeout_sec=120):
    if not sys.stdin.isatty():
        print(prompt, end="", flush=True)
        return sys.stdin.readline().strip()
        
    import msvcrt
    print(prompt, end="", flush=True)
    user_input = ""
    start_time = time.time()
    
    while time.time() - start_time < timeout_sec:
        # Mantém o event loop do Playwright rodando para não dar timeout no CDP
        page.wait_for_timeout(100)
        
        if msvcrt.kbhit():
            char = msvcrt.getwche()
            if char == '\r' or char == '\n':
                print()  # Quebra de linha
                break
            elif char == '\b' or ord(char) == 8:  # Backspace
                if len(user_input) > 0:
                    user_input = user_input[:-1]
                    # Limpa o caractere no console
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif ord(char) >= 32:  # Caracteres imprimíveis
                user_input += char
                
    return user_input.strip()

def tratar_desafio_prodam(page):
    try:
        # Check if the Prodam challenge field (#ans) is present
        page.wait_for_selector("#ans", timeout=3000)
    except:
        return
        
    print("\n[DESAFIO PRODAM DETECTADO] Capturando imagem...")
    captcha_img_path = "captcha_municipal_sp_prodam.png"
    try:
        page.locator("img").first.screenshot(path=captcha_img_path)
        print(f"Imagem do CAPTCHA Prodam salva como '{captcha_img_path}'.")
    except Exception as e:
        print(f"Erro ao capturar imagem do CAPTCHA Prodam: {e}")
        page.screenshot(path=captcha_img_path)
        print(f"Screenshot geral salvo como '{captcha_img_path}'.")
        
    captcha_val = obter_input_interativo("Digite o CAPTCHA do desafio Prodam no terminal: ", page)
    page.fill("#ans", captcha_val)
    
    # Click the submit button using a robust XPath selector
    submit_xpath = 'xpath=//input[@type="submit"] | //input[@value="submit"] | //button[text()="submit"] | //input[@value="Submit"]'
    page.click(submit_xpath)
    print("Desafio enviado. Aguardando recarregamento...")
    time.sleep(3)

def testar_municipal_sp(cnpj):
    print("\n--- TESTANDO CND MUNICIPAL SP (Prefeitura de São Paulo) ---")
    url = "https://duc.prefeitura.sp.gov.br/certidoes/forms_anonimo/frmConsultaEmissaoCertificado.aspx"
    print(f"Acessando: {url}")
    
    user_data_dir = os.path.abspath("./user_data_municipal_sp")
    
    with sync_playwright() as p:
        browser, context = iniciar_e_conectar_chrome(p, user_data_dir, headless=False)
        page = context.new_page()
        
        try:
            page.goto(url)
            time.sleep(3)
            
            # Dismiss cookies modal
            cookie_btn = page.locator('text="Sair sem autorizar"')
            if cookie_btn.count() > 0:
                cookie_btn.click()
                print("Modal de cookies fechado.")
            time.sleep(1)
            
            # Trata desafio prodam se aparecer inicialmente
            tratar_desafio_prodam(page)
            
            # Select "Certidão Tributária Mobiliária"
            dropdown_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_ddlTipoCertidao"]'
            page.wait_for_selector(dropdown_xpath, timeout=15000)
            page.select_option(dropdown_xpath, label="Certidão Tributária Mobiliária")
            print("Opção 'Certidão Tributária Mobiliária' selecionada.")
            
            # Trata desafio prodam se aparecer após a seleção (postback)
            tratar_desafio_prodam(page)
            
            # Aguarda o campo de CNPJ ficar visível
            cnpj_input_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_txtCNPJ"]'
            page.wait_for_selector(cnpj_input_xpath, timeout=15000)
            
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            page.click(cnpj_input_xpath)
            page.fill(cnpj_input_xpath, cnpj_limpo)
            print("CNPJ preenchido.")
            
            # Salva o CAPTCHA do formulário CND
            captcha_img_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_imgCaptcha"]'
            page.wait_for_selector(captcha_img_xpath, timeout=10000)
            
            captcha_img_path = "captcha_municipal_sp.png"
            page.locator(captcha_img_xpath).screenshot(path=captcha_img_path)
            print(f"Imagem do CAPTCHA Municipal SP salva como '{captcha_img_path}'.")
            
            # Pede para o usuário digitar o CAPTCHA
            captcha_val = obter_input_interativo("Digite o CAPTCHA de 4 ou 5 caracteres no terminal e pressione ENTER: ", page)
            
            captcha_input_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_txtValorCaptcha"]'
            page.fill(captcha_input_xpath, captcha_val)
            print("CAPTCHA preenchido. Clicando em Emitir...")
            
            emitir_btn_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_btnEmitir"]'
            page.wait_for_selector(emitir_btn_xpath, timeout=10000)
            
            # Clica em Emitir e intercepta o download do PDF
            try:
                with page.expect_download(timeout=25000) as download_info:
                    page.click(emitir_btn_xpath)
                
                download = download_info.value
                temp_pdf_path = f"temp_municipal_sp_{cnpj}.pdf"
                download.save_as(temp_pdf_path)
                print(f"PDF real da certidão Municipal SP salvo com sucesso em {temp_pdf_path}")
                
                # Screenshot de sucesso para controle
                page.screenshot(path="resultado_municipal_sp.png")
                print("Print screen salvo como 'resultado_municipal_sp.png'")
                
            except Exception as d_err:
                print(f"Erro ou timeout no download automático: {d_err}")
                # Captura erro para diagnóstico
                page.screenshot(path="municipal_sp_error.png")
                print("Screenshot do erro salvo como 'municipal_sp_error.png'")
                raise d_err
                
            # Aguarda 3 segundos e clica no botão Fechar Modal
            time.sleep(3)
            fechar_modal_xpath = 'xpath=//*[@id="btnFecharModalCertidoes"]'
            try:
                if page.locator(fechar_modal_xpath).is_visible():
                    page.click(fechar_modal_xpath)
                    print("Modal de encerramento fechado com sucesso.")
            except Exception as f_err:
                print(f"Aviso ao tentar fechar o modal: {f_err}")
                
        except Exception as e:
            print(f"Erro no teste Municipal SP: {e}")
            try:
                page.screenshot(path="municipal_sp_error.png")
                print("Screenshot do erro salvo em 'municipal_sp_error.png'")
            except:
                pass
        finally:
            if 'page' in locals():
                try:
                    # Envia comando CDP para fechar toda a instância do navegador
                    client = page.context.new_cdp_session(page)
                    client.send("Browser.close")
                except:
                    pass
                try: page.close()
                except: pass
            if 'context' in locals():
                try: context.close()
                except: pass
            if 'browser' in locals():
                try: browser.close()
                except: pass
            print("Instância do navegador fechada.")


def treinar_perfil_federal():
    print("\n--- TREINAMENTO MANUAL DO PERFIL CND FEDERAL ---")
    print("Vou abrir o Chrome com o perfil persistente dedicado.")
    print("Por favor, faça a consulta do CNPJ manualmente na tela.")
    print("Após a certidão carregar na tela com sucesso, feche a janela do Chrome.")
    print("-------------------------------------------------")
    
    user_data_dir = os.path.abspath("./user_data_receita")
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars"
            ],
            ignore_default_args=["--enable-automation"]
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj")
        
        while True:
            try:
                if page.is_closed():
                    break
                time.sleep(1.0)
            except:
                break
        
        print("\nNavegador fechado. Perfil treinado e salvo!")
        context.close()


def tratar_desafio_prodam_auto(page, ocr, max_tentativas=5):
    for tentativa in range(1, max_tentativas + 1):
        try:
            # Verifica se o campo do desafio (#ans) está na tela
            page.wait_for_selector("#ans", timeout=3000)
        except:
            return # Se não encontrar, o desafio não está presente
            
        print(f"    [DESAFIO PRODAM] Resolvendo automaticamente - tentativa {tentativa}/{max_tentativas}...")
        try:
            img_el = page.locator("img").first
            img_el.wait_for(state="visible", timeout=5000)
            img_bytes = img_el.screenshot()
            if not img_bytes:
                raise Exception("Screenshot de elemento vazio")
        except Exception:
            # Fallback tirando print da tela e lendo (caso o seletor da imagem falhe)
            temp_img_path = "temp_prodam.png"
            page.screenshot(path=temp_img_path)
            with open(temp_img_path, "rb") as f:
                img_bytes = f.read()
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)
                
        captcha_val = ocr.classification(img_bytes)
        captcha_val = "".join([c for c in captcha_val if c.isascii() and c.isalnum()])
        print(f"        ddddocr leu: '{captcha_val}'")
        
        page.fill("#ans", "")
        page.fill("#ans", captcha_val)
        
        submit_xpath = 'xpath=//input[@type="submit"] | //input[@value="submit"] | //button[text()="submit"] | //input[@value="Submit"]'
        page.click(submit_xpath)
        time.sleep(2)


def obter_fgts(cnpj, uf="SP", headless=True):
    print(f"[FGTS] Iniciando emissão para o CNPJ: {cnpj}...")
    url = "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"
    
    user_data_dir = os.path.abspath("./user_data_fgts")
    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
    temp_pdf_path = os.path.abspath(f"temp_fgts_{cnpj_limpo}.pdf")
    
    with sync_playwright() as p:
        browser, context = iniciar_e_conectar_chrome(p, user_data_dir, headless=headless)
        page = context.new_page()
        
        try:
            goto_with_retry(page, url)
            cnpj_selector = 'xpath=//*[@id="mainForm:txtInscricao1"]'
            uf_selector = 'xpath=//*[@id="mainForm:uf"]'
            btn_selector = 'xpath=//*[@id="mainForm:btnConsultar"]'
            
            page.wait_for_selector(cnpj_selector, timeout=20000)
            
            page.fill(cnpj_selector, cnpj_limpo)
            page.select_option(uf_selector, value=uf)
            page.click(btn_selector)
            
            sucesso_selector = '[id="mainForm:j_id76"]'
            erro_selector = ".msgErro, .erro, [id='mainForm:mensagens']"
            
            page.wait_for_selector(f"{sucesso_selector}, {erro_selector}", timeout=20000)
            
            elementos_erro = page.query_selector_all(erro_selector)
            for el in elementos_erro:
                if el.is_visible():
                    erro_msg = el.inner_text().strip()
                    if erro_msg:
                        return {"status": "erro", "mensagem": f"Erro no portal da Caixa: {erro_msg}"}
            
            if page.query_selector(sucesso_selector):
                page.click(sucesso_selector)
                
                btn_visualizar = '[id="mainForm:btnVisualizar"]'
                page.wait_for_selector(btn_visualizar, timeout=15000)
                page.click(btn_visualizar)
                
                btn_imprimir = '[id="mainForm:btImprimir4"]'
                page.wait_for_selector(btn_imprimir, timeout=15000)
                
                page.evaluate("window.print = () => {}")
                page.click(btn_imprimir)
                page.emulate_media(media="print")
                page.evaluate("""
                    document.querySelectorAll('input[type="submit"], input[type="button"], button, .no-print, [id*="btnVoltar"], [id*="btImprimir"]').forEach(el => el.style.display = 'none');
                """)
                
                screenshot_path = os.path.abspath(f"temp_screenshot_fgts_{cnpj_limpo}.png")
                page.screenshot(path=screenshot_path, full_page=True)
                page.emulate_media(media="screen")
                
                img = Image.open(screenshot_path).convert("RGB")
                img.save(temp_pdf_path, "PDF")
                
                if os.path.exists(screenshot_path):
                    os.remove(screenshot_path)
                    
                return {"status": "sucesso", "pdf_path": temp_pdf_path}
            else:
                return {"status": "erro", "mensagem": "Não foi possível localizar o link do CRF após a consulta."}
                
        except Exception as e:
            return {"status": "erro", "mensagem": str(e)}
        finally:
            if 'page' in locals():
                try:
                    client = page.context.new_cdp_session(page)
                    client.send("Browser.close")
                except:
                    pass
                try: page.close()
                except: pass
            if 'context' in locals():
                try: context.close()
                except: pass
            if 'browser' in locals():
                try: browser.close()
                except: pass


def obter_federal(cnpj, user_data_dir=None, headless=True):
    print(f"[FEDERAL] Iniciando emissão para o CNPJ: {cnpj}...")
    url = "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj"
    
    if not user_data_dir:
        user_data_dir = os.path.abspath("./user_data_receita")
        
    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
    temp_pdf_path = os.path.abspath(f"temp_federal_{cnpj_limpo}.pdf")
    
    with sync_playwright() as p:
        browser, context = iniciar_e_conectar_chrome(p, user_data_dir, headless=headless)
        page = context.new_page()
        
        try:
            goto_with_retry(page, url)
            
            cnpj_selector = 'input[name="niContribuinte"]'
            try:
                page.wait_for_selector(cnpj_selector, timeout=15000)
            except Exception:
                cnpj_selector = 'input[placeholder="Informe o CNPJ"]'
                try:
                    page.wait_for_selector(cnpj_selector, timeout=5000)
                except Exception:
                    cnpj_selector = 'xpath=//*[@id="id3f4c9ab5e7e9d4"]'
                    page.wait_for_selector(cnpj_selector, timeout=10000)
            
            time.sleep(1.0)
            page.focus(cnpj_selector)
            page.click(cnpj_selector)
            page.type(cnpj_selector, cnpj_limpo, delay=60)
            page.press(cnpj_selector, "Tab")
            time.sleep(1.0)
            
            try:
                btn_cookies = 'button:has-text("Aceitar")'
                if page.locator(btn_cookies).is_visible():
                    page.click(btn_cookies)
                    time.sleep(1.0)
            except:
                pass
                
            btn_selector = 'button:has-text("Emitir Certidão")'
            try:
                page.wait_for_selector(btn_selector, timeout=10000)
            except Exception:
                btn_selector = 'xpath=/html/body/app-root/mf-portal-layout/portal-main-layout/div/main/ng-component/ng-component/app-coleta-parametros-pj/app-coleta-parametros-template/form/div[2]/div[2]/button[2]'
                page.wait_for_selector(btn_selector, timeout=5000)
                
            page.click(btn_selector)
            time.sleep(1.0)
            
            try:
                btn_xpath = 'xpath=/html/body/modal-container/div[2]/div/div[3]/button[2]'
                btn_texto = 'button:has-text("Emitir Nova Certidão")'
                
                try:
                    page.wait_for_selector('modal-container', timeout=10000)
                except:
                    page.wait_for_selector(btn_xpath, timeout=3000)
                    
                time.sleep(1.0)
                if page.locator(btn_xpath).is_visible():
                    page.click(btn_xpath)
                elif page.locator(btn_texto).is_visible():
                    page.click(btn_texto)
                else:
                    page.click(btn_xpath, force=True, timeout=3000)
                time.sleep(1.0)
            except:
                pass
                
            sucesso_selector = "iframe:not([src*='hcaptcha']):not([src*='google']), embed, object, [href*='.pdf']"
            erro_selector = ".alert, .error, .message-error, .mensagem-erro, #mensagemErro, .br-message, .feedback, .invalid-feedback"
            
            link_download_alternativo = 'a:has-text("download do documento PDF da certidão")'
            if page.locator(link_download_alternativo).is_visible():
                try:
                    with page.expect_download(timeout=10000) as download_info:
                        page.click(link_download_alternativo)
                    download = download_info.value
                    download.save_as(temp_pdf_path)
                    return {"status": "sucesso", "pdf_path": temp_pdf_path}
                except Exception as d_err:
                    print(f"Erro ao baixar o PDF pelo link alternativo: {d_err}")
            
            try:
                page.wait_for_selector(f"{sucesso_selector}, {erro_selector}, div:has-text('insuficientes')", timeout=8000)
            except Exception:
                body_text = page.locator("body").inner_text()
                if "insuficientes" not in body_text and "Não foi possível concluir" not in body_text:
                    raise Exception("Timeout aguardando resultado do portal Federal.")
            
            elementos_erro = page.query_selector_all(erro_selector)
            for el in elementos_erro:
                if el.is_visible():
                    erro_msg = el.inner_text().strip()
                    if erro_msg:
                        return {"status": "erro", "mensagem": f"Erro no portal da Receita Federal: {erro_msg}"}
            
            body_text = page.locator("body").inner_text()
            if "insuficientes" in body_text:
                return {"status": "erro", "mensagem": "As informações disponíveis na Receita Federal sobre o contribuinte são insuficientes para emitir a certidão pela Internet."}
            if "Não foi possível concluir" in body_text:
                return {"status": "erro", "mensagem": "Não foi possível concluir a ação para o contribuinte informado. Tente novamente em alguns minutos."}
                
            if page.query_selector(sucesso_selector):
                print("PDF renderizado em tela. Gerando PDF...")
                try:
                    page.pdf(path=temp_pdf_path)
                except Exception as pdf_ex:
                    # Fallback para screenshot se não suportado (ex: modo headful)
                    screenshot_path = f"resultado_federal_{cnpj_limpo}.png"
                    page.screenshot(path=screenshot_path, full_page=True)
                    img = Image.open(screenshot_path).convert("RGB")
                    img.save(temp_pdf_path, "PDF")
                    if os.path.exists(screenshot_path):
                        os.remove(screenshot_path)
                return {"status": "sucesso", "pdf_path": temp_pdf_path}
            else:
                return {"status": "erro", "mensagem": "Resultado desconhecido após clique de emissão."}
                
        except Exception as e:
            return {"status": "erro", "mensagem": str(e)}
        finally:
            if 'page' in locals():
                try:
                    client = page.context.new_cdp_session(page)
                    client.send("Browser.close")
                except:
                    pass
                try: page.close()
                except: pass
            if 'context' in locals():
                try: context.close()
                except: pass
            if 'browser' in locals():
                try: browser.close()
                except: pass


def obter_cndt(cnpj, headless=True):
    print(f"[CNDT] Iniciando emissão para o CNPJ: {cnpj}...")
    url = "https://cndt-certidao.tst.jus.br/inicio.faces"
    
    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
    temp_pdf_path = os.path.abspath(f"temp_cndt_{cnpj_limpo}.pdf")
    user_data_dir = os.path.abspath("./user_data_cndt")
    
    ocr = ddddocr.DdddOcr(show_ad=False)
    
    with sync_playwright() as p:
        browser, context = iniciar_e_conectar_chrome(p, user_data_dir, headless=headless)
        page = context.new_page()
        
        try:
            goto_with_retry(page, url)
            btn_inicial = 'xpath=//*[@id="corpo"]/div/div[2]/input[1]'
            page.wait_for_selector(btn_inicial, timeout=20000)
            page.click(btn_inicial)
            
            cnpj_selector = 'xpath=//*[@id="gerarCertidaoForm:cpfCnpj"]'
            page.wait_for_selector(cnpj_selector, timeout=20000)
            page.fill(cnpj_selector, cnpj)
            
            captcha_img_sel = 'img[id*="captcha"], img[id*="Captcha"], img[src^="data:image"]'
            captcha_input_sel = '[id="idCampoResposta"]'
            btn_emitir = '[id="gerarCertidaoForm:btnEmitirCertidao"]'
            erro_selector = ".mensagem-erro, .erro, .alert, #messages, ul.erro, [id='gerarCertidaoForm:mensagens'], #mensagens, .erros, [id*='areaMensagemErro']"
            
            max_tentativas = 10
            for tentativa in range(1, max_tentativas + 1):
                print(f"    [CNDT CAPTCHA] Tentativa {tentativa}/{max_tentativas}...")
                
                img_el = page.locator(captcha_img_sel).first
                img_el.wait_for(state="attached", timeout=15000)
                
                img_bytes = None
                src = img_el.get_attribute("src")
                if src and src.startswith("data:image"):
                    import base64
                    try:
                        header, base64_data = src.split(",", 1)
                        img_bytes = base64.b64decode(base64_data)
                        print("    [CNDT CAPTCHA] Imagem extraída diretamente via Base64 do atributo 'src'.")
                    except Exception as b64_err:
                        print(f"    [CNDT CAPTCHA] Erro ao decodificar Base64: {b64_err}")
                
                if not img_bytes:
                    try:
                        img_el.wait_for(state="visible", timeout=5000)
                        img_bytes = img_el.screenshot()
                    except Exception as s_err:
                        print(f"    [CNDT CAPTCHA] Falha no screenshot do elemento: {s_err}. Capturando página inteira...")
                        temp_cndt_snap = f"temp_cndt_captcha_snap_{cnpj_limpo}.png"
                        page.screenshot(path=temp_cndt_snap)
                        with open(temp_cndt_snap, "rb") as f:
                            img_bytes = f.read()
                        if os.path.exists(temp_cndt_snap):
                            os.remove(temp_cndt_snap)
                
                captcha_val = ocr.classification(img_bytes)
                captcha_val = "".join([c for c in captcha_val if c.isascii() and c.isalnum()])
                print(f"    ddddocr leu: '{captcha_val}'")
                
                page.fill(captcha_input_sel, "")
                page.fill(captcha_input_sel, captcha_val)
                
                try:
                    with page.expect_download(timeout=10000) as download_info:
                        page.click(btn_emitir)
                    
                    download = download_info.value
                    download.save_as(temp_pdf_path)
                    print(f"    PDF CNDT baixado com sucesso na tentativa {tentativa}.")
                    return {"status": "sucesso", "pdf_path": temp_pdf_path}
                    
                except Exception as d_err:
                    time.sleep(1.0)
                    elementos_erro = page.query_selector_all(erro_selector)
                    erro_msg = ""
                    for el in elementos_erro:
                        if el.is_visible():
                            txt = el.inner_text().strip()
                            if txt:
                                erro_msg = txt
                                break
                    
                    # Se houve erro ou download falhou, vamos reiniciar a tela se o botão "Emitir Nova Certidão" estiver presente
                    btn_emitir_nova = 'input[value="Emitir Nova Certidão"]'
                    try:
                        if page.locator(btn_emitir_nova).count() > 0:
                            print("    [CNDT CAPTCHA] Botão 'Emitir Nova Certidão' detectado. Reiniciando formulário...")
                            page.click(btn_emitir_nova)
                            page.wait_for_selector(cnpj_selector, timeout=15000)
                            page.fill(cnpj_selector, cnpj)
                    except Exception as btn_err:
                        print(f"    Erro ao tentar voltar com 'Emitir Nova Certidão': {btn_err}")
                    
                    if erro_msg:
                        print(f"    Mensagem do portal: '{erro_msg}'")
                        if any(kwd in erro_msg.lower() for kwd in ["código", "segurança", "captcha", "inválido", "caracteres"]):
                            continue
                        else:
                            return {"status": "erro", "mensagem": f"Erro no portal CNDT: {erro_msg}"}
                    else:
                        continue
                        
            return {"status": "erro", "mensagem": f"Falha ao resolver o CAPTCHA da CNDT após {max_tentativas} tentativas."}
            
        except Exception as e:
            return {"status": "erro", "mensagem": str(e)}
        finally:
            if 'page' in locals():
                try:
                    client = page.context.new_cdp_session(page)
                    client.send("Browser.close")
                except:
                    pass
                try: page.close()
                except: pass
            if 'context' in locals():
                try: context.close()
                except: pass
            if 'browser' in locals():
                try: browser.close()
                except: pass


def obter_municipal_sp(cnpj, user_data_dir=None, headless=True):
    print(f"[MUNICIPAL SP] Iniciando emissão para o CNPJ: {cnpj}...")
    url = "https://duc.prefeitura.sp.gov.br/certidoes/forms_anonimo/frmConsultaEmissaoCertificado.aspx"
    
    if not user_data_dir:
        user_data_dir = os.path.abspath("./user_data_municipal_sp")
        
    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
    temp_pdf_path = os.path.abspath(f"temp_municipal_sp_{cnpj_limpo}.pdf")
    
    ocr = ddddocr.DdddOcr(show_ad=False)
    
    max_tentativas_globais = 3
    for tentativa_global in range(1, max_tentativas_globais + 1):
        print(f"    [MUNICIPAL SP] Tentativa global {tentativa_global}/{max_tentativas_globais}...")
        
        with sync_playwright() as p:
            browser, context = iniciar_e_conectar_chrome(p, user_data_dir, headless=headless)
            page = context.new_page()
            
            try:
                # 1. Acesso inicial com retries de rede
                goto_with_retry(page, url)
                time.sleep(2)
                
                cookie_btn = page.locator('text="Sair sem autorizar"')
                if cookie_btn.count() > 0:
                    cookie_btn.click()
                time.sleep(1)
                
                tratar_desafio_prodam_auto(page, ocr)
                verificar_erro_rede(page)
                
                dropdown_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_ddlTipoCertidao"]'
                page.wait_for_selector(dropdown_xpath, timeout=15000)
                page.select_option(dropdown_xpath, label="Certidão Tributária Mobiliária")
                time.sleep(2) # Aguarda postback
                
                tratar_desafio_prodam_auto(page, ocr)
                verificar_erro_rede(page)
                
                cnpj_input_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_txtCNPJ"]'
                page.wait_for_selector(cnpj_input_xpath, timeout=15000)
                page.fill(cnpj_input_xpath, cnpj_limpo)
                verificar_erro_rede(page)
                
                captcha_img_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_imgCaptcha"]'
                captcha_input_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_txtValorCaptcha"]'
                emitir_btn_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_btnEmitir"]'
                erro_selector = "#ctl00_ConteudoPrincipal_lblMensagem, .alert, .erro, .mensagem-erro"
                
                max_tentativas = 10
                captcha_resolvido = False
                for tentativa in range(1, max_tentativas + 1):
                    print(f"        [MUNICIPAL SP CAPTCHA] Tentativa {tentativa}/{max_tentativas}...")
                    verificar_erro_rede(page)
                    
                    img_el = page.locator(captcha_img_xpath)
                    img_el.wait_for(state="visible", timeout=10000)
                    time.sleep(0.5)
                    img_bytes = img_el.screenshot()
                    
                    captcha_val = ocr.classification(img_bytes)
                    captcha_val = "".join([c for c in captcha_val if c.isascii() and c.isalnum()])
                    print(f"        ddddocr leu: '{captcha_val}'")
                    
                    page.fill(captcha_input_xpath, "")
                    page.fill(captcha_input_xpath, captcha_val)
                    
                    try:
                        with page.expect_download(timeout=15000) as download_info:
                            page.click(emitir_btn_xpath)
                            
                        download = download_info.value
                        download.save_as(temp_pdf_path)
                        print(f"        PDF Municipal SP baixado com sucesso na tentativa {tentativa}.")
                        
                        time.sleep(2)
                        fechar_modal_xpath = 'xpath=//*[@id="btnFecharModalCertidoes"]'
                        if page.locator(fechar_modal_xpath).is_visible():
                            page.click(fechar_modal_xpath)
                            
                        captcha_resolvido = True
                        break
                        
                    except Exception as d_err:
                        time.sleep(1.0)
                        tratar_desafio_prodam_auto(page, ocr)
                        verificar_erro_rede(page)
                        
                        erro_msg = ""
                        elementos_erro = page.query_selector_all(erro_selector)
                        for el in elementos_erro:
                            if el.is_visible():
                                txt = el.inner_text().strip()
                                if txt:
                                    erro_msg = txt
                                    break
                                    
                        if erro_msg:
                            print(f"        Mensagem do portal: '{erro_msg}'")
                            if any(kwd in erro_msg.lower() for kwd in ["captcha", "imagem", "código", "segurança", "inválido"]):
                                continue
                            else:
                                return {"status": "erro", "mensagem": f"Erro no portal Municipal SP: {erro_msg}"}
                        else:
                            verificar_erro_rede(page)
                            continue
                            
                if captcha_resolvido:
                    return {"status": "sucesso", "pdf_path": temp_pdf_path}
                else:
                    raise Exception(f"Falha ao resolver o CAPTCHA Municipal SP após {max_tentativas} tentativas.")
                    
            except NetworkError as net_err:
                print(f"    [MUNICIPAL SP] Erro de rede na tentativa global {tentativa_global}: {net_err}")
                if tentativa_global == max_tentativas_globais:
                    return {"status": "erro", "mensagem": f"Erro de rede persistente no portal Municipal SP: {net_err}"}
                time.sleep(3)
            except Exception as e:
                print(f"    [MUNICIPAL SP] Erro geral na tentativa global {tentativa_global}: {e}")
                if tentativa_global == max_tentativas_globais:
                    return {"status": "erro", "mensagem": str(e)}
                time.sleep(3)
            finally:
                if 'page' in locals():
                    try:
                        client = page.context.new_cdp_session(page)
                        client.send("Browser.close")
                    except:
                        pass
                    try: page.close()
                    except: pass
                if 'context' in locals():
                    try: context.close()
                    except: pass
                if 'browser' in locals():
                    try: browser.close()
                    except: pass


def obter_estadual(cnpj, headless=True):
    print(f"[ESTADUAL] Iniciando emissão para o CNPJ: {cnpj}...")
    url = "https://www10.fazenda.sp.gov.br/CertidaoNegativaDeb/Pages/EmissaoCertidaoNegativa.aspx"
    
    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
    temp_pdf_path = os.path.abspath(f"temp_estadual_sp_{cnpj_limpo}.pdf")
    user_data_dir = os.path.abspath("./user_data_sp")
    
    with sync_playwright() as p:
        browser, context = iniciar_e_conectar_chrome(p, user_data_dir, headless=headless)
        page = context.new_page()
        
        try:
            goto_with_retry(page, url)
            
            cnpj_radio_xpath = 'xpath=//*[@id="MainContent_cnpjradio"]'
            page.wait_for_selector(cnpj_radio_xpath, timeout=20000)
            page.click(cnpj_radio_xpath)
            
            cnpj_input_xpath = 'xpath=//*[@id="MainContent_txtDocumento"]'
            page.wait_for_selector(cnpj_input_xpath, timeout=10000)
            page.fill(cnpj_input_xpath, cnpj_limpo)
            
            recaptcha_resolvido = resolver_recaptcha(page)
            if not recaptcha_resolvido:
                raise Exception("A resolução automática do reCAPTCHA falhou no modo headless.")
            
            btn_emitir_xpath = 'xpath=//*[@id="MainContent_btnPesquisar"]'
            page.wait_for_selector(btn_emitir_xpath, timeout=10000)
            page.click(btn_emitir_xpath)
            
            btn_imprimir_xpath = 'xpath=//*[@id="MainContent_btnImpressao"]'
            page.wait_for_selector(btn_imprimir_xpath, timeout=20000)
            
            page.evaluate("window.print = () => { console.log('window.print simulado com sucesso'); }")
            
            pdf_salvo = False
            
            try:
                with page.expect_download(timeout=5000) as download_info:
                    page.click(btn_imprimir_xpath)
                download = download_info.value
                download.save_as(temp_pdf_path)
                print(f"    [ESTADUAL-SP] PDF baixado com sucesso via download em: {temp_pdf_path}")
                pdf_salvo = True
            except Exception:
                pass
            
            if not pdf_salvo:
                page.emulate_media(media="print")
                
                page.evaluate("""
                    document.querySelectorAll('input[type="submit"], input[type="button"], button, .no-print, [id*="btnImpressao"], [id*="btnVoltar"]').forEach(el => el.style.display = 'none');
                """)
                
                try:
                    page.click(btn_imprimir_xpath, timeout=2000)
                except:
                    pass
                
                screenshot_path = os.path.abspath(f"temp_screenshot_estadual_{cnpj_limpo}.png")
                page.screenshot(path=screenshot_path, full_page=True)
                
                page.emulate_media(media="screen")
                
                try:
                    from PIL import Image
                    img = Image.open(screenshot_path).convert("RGB")
                    img.save(temp_pdf_path, "PDF")
                    print(f"    [ESTADUAL-SP] PDF real gerado via conversão de imagem em: {temp_pdf_path}")
                    pdf_salvo = True
                except Exception as pdf_err:
                    raise Exception(f"Erro ao converter screenshot para PDF: {pdf_err}")
                finally:
                    if os.path.exists(screenshot_path):
                        try: os.remove(screenshot_path)
                        except: pass
            
            return {"status": "sucesso", "pdf_path": temp_pdf_path}
            
        except Exception as e:
            return {"status": "erro", "mensagem": f"Falha no robô Estadual SP: {str(e)}"}
        finally:
            browser.close()


if __name__ == "__main__":
    print("=" * 60)
    print(" SCRIPT DE TESTE INTERATIVO DE WEBSCRAPING (MODO VISÍVEL) ")
    print("=" * 60)
    print("Escolha qual robô deseja testar:")
    print("1 - CND Federal (Receita)")
    print("2 - CND FGTS (Caixa)")
    print("3 - CNDT Trabalhista (TST)")
    print("4 - CND Estadual SP")
    print("5 - CND Municipal SP")
    print("6 - Testar Todos")
    print("7 - Treinar Perfil CND Federal (Manual)")
    
    opcao = input("\nDigite a opção desejada (1-7): ").strip()
    
    # Solicita o CNPJ (exceto para treinamento de perfil)
    if opcao in ["1", "2", "3", "4", "5", "6"]:
        cnpj_teste = input("Digite o CNPJ (apenas números): ").strip().replace(".", "").replace("/", "").replace("-", "")
        if len(cnpj_teste) != 14:
            print("CNPJ inválido! Deve conter 14 dígitos.")
            sys.exit(1)
    
    # Habilita SSL bypass para chamadas locais caso necessário (rede corporativa)
    os.environ["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
    
    if opcao == "1":
        testar_federal(cnpj_teste)
    elif opcao == "2":
        testar_fgts(cnpj_teste)
    elif opcao == "3":
        testar_cndt(cnpj_teste)
    elif opcao == "4":
        testar_estadual_sp(cnpj_teste)
    elif opcao == "5":
        testar_municipal_sp(cnpj_teste)
    elif opcao == "6":
        testar_federal(cnpj_teste)
        testar_fgts(cnpj_teste)
        testar_cndt(cnpj_teste)
        testar_estadual_sp(cnpj_teste)
        testar_municipal_sp(cnpj_teste)
    elif opcao == "7":
        treinar_perfil_federal()
    else:
        print("Opção inválida.")


