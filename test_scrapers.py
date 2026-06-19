import sys
import os
import time
import subprocess
import requests
from playwright.sync_api import sync_playwright
import speech_recognition as sr
from pydub import AudioSegment

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

def iniciar_e_conectar_chrome(p, user_data_dir, headless=False):
    chrome_running = False
    try:
        response = requests.get("http://127.0.0.1:9222/json/version", timeout=2)
        if response.status_code == 200:
            chrome_running = True
            print("Instância do Chrome na porta 9222 já está rodando. Conectando...")
    except Exception:
        pass
        
    if not chrome_running:
        chrome_path = get_chrome_path()
        print(f"Iniciando Chrome nativo em: {chrome_path} (headless={headless})")
        chrome_args = [
            chrome_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        if headless:
            chrome_args.append("--headless=new")
        subprocess.Popen(chrome_args)
        
        # Aguarda até 5 segundos ou até a porta 9222 responder
        for _ in range(10):
            time.sleep(0.5)
            try:
                response = requests.get("http://127.0.0.1:9222/json/version", timeout=1)
                if response.status_code == 200:
                    break
            except Exception:
                pass
        
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
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
            
            # Na tela seguinte, verificar se há o botão "IMPRIMIR" cujo xPath é o //*[@id="MainContent_btnImpressao"]
            btn_imprimir_xpath = 'xpath=//*[@id="MainContent_btnImpressao"]'
            try:
                page.wait_for_selector(btn_imprimir_xpath, timeout=20000)
                print("Sucesso! Botão IMPRIMIR encontrado na tela seguinte.")
                page.screenshot(path="resultado_estadual_sp.png")
                print("Print screen salvo como 'resultado_estadual_sp.png'")
            except Exception as e:
                print(f"Erro: Botão IMPRIMIR não encontrado ou houve erro na consulta. Detalhes: {e}")
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

if __name__ == "__main__":
    print("=" * 60)
    print(" SCRIPT DE TESTE INTERATIVO DE WEBSCRAPING (MODO VISÍVEL) ")
    print("=" * 60)
    print("Escolha qual robô deseja testar:")
    print("1 - CND Federal (Receita)")
    print("2 - CND FGTS (Caixa)")
    print("3 - CNDT Trabalhista (TST)")
    print("4 - CND Estadual SP")
    print("5 - Testar Todos")
    print("6 - Treinar Perfil CND Federal (Manual)")
    
    opcao = input("\nDigite a opção desejada (1-6): ").strip()
    
    # Solicita o CNPJ (exceto para treinamento de perfil)
    if opcao in ["1", "2", "3", "4", "5"]:
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
        testar_federal(cnpj_teste)
        testar_fgts(cnpj_teste)
        testar_cndt(cnpj_teste)
        testar_estadual_sp(cnpj_teste)
    elif opcao == "6":
        treinar_perfil_federal()
    else:
        print("Opção inválida.")


